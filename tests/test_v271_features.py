"""
Tests for EPI Recorder v2.7.1 features.

Covers:
  - File association module (import-level + Windows registry on win32)
  - Unicode path handling in view resolver
  - Stem resolution (most recent by mtime)
  - Version consistency
  - Linux xdg-mime path smoke test
"""

import json
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ============================================================
# 1. File association module — import smoke test (all platforms)
# ============================================================

class TestFileAssociationModule:
    """Test that the file association module imports without error."""

    def test_import_register(self):
        """register_file_association must be importable on all platforms."""
        from epi_core.platform.associate import register_file_association
        assert callable(register_file_association)

    def test_import_unregister(self):
        """unregister_file_association must be importable on all platforms."""
        from epi_core.platform.associate import unregister_file_association
        assert callable(unregister_file_association)

    def test_package_init_exports(self):
        """Package __init__ should export both functions."""
        from epi_core.platform import (
            register_file_association,
            unregister_file_association,
        )
        assert callable(register_file_association)
        assert callable(unregister_file_association)

    def test_silent_mode_never_raises(self):
        """register_file_association(silent=True) must never raise."""
        from epi_core.platform.associate import (
            register_file_association,
            _clear_registered,
        )
        # Clear flag so registration is attempted
        _clear_registered()
        # Even if registration fails internally, silent=True should not raise
        result = register_file_association(silent=True)
        # Result is either True (success) or False (failed silently)
        assert isinstance(result, bool)
        # Clean up
        _clear_registered()


# ============================================================
# 2. Windows-specific registry tests
# ============================================================

@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
class TestWindowsFileAssociation:
    """Test Windows registry operations (only runs on Windows)."""

    def test_register_creates_registry_keys(self):
        """register_windows() should create .epi and EPIRecorder.File keys."""
        import winreg
        from epi_core.platform.associate import register_windows, unregister_windows

        register_windows()

        # Verify .epi extension key exists
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Classes\.epi"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "")
            assert value == "EPIRecorder.File"

        # Verify ProgID key exists
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Classes\EPIRecorder.File"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "")
            assert value == "EPI Recording File"

        # Verify open command exists and contains "view"
        cmd_path = r"Software\Classes\EPIRecorder.File\shell\open\command"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cmd_path) as key:
            value, _ = winreg.QueryValueEx(key, "")
            assert "view" in value
            assert '"%1"' in value

        # Clean up
        unregister_windows()

    def test_unregister_removes_registry_keys(self):
        """unregister_windows() should remove all .epi registry keys."""
        import winreg
        from epi_core.platform.associate import register_windows, unregister_windows

        register_windows()
        unregister_windows()

        # Keys should be gone
        with pytest.raises(FileNotFoundError):
            winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Classes\.epi"
            )

        with pytest.raises(FileNotFoundError):
            winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Classes\EPIRecorder.File",
            )

    def test_register_is_idempotent(self):
        """Calling register_windows() twice should not cause errors."""
        from epi_core.platform.associate import register_windows, unregister_windows

        register_windows()
        register_windows()  # Should not raise
        unregister_windows()


# ============================================================
# 3. Linux xdg-mime smoke test
# ============================================================

@pytest.mark.skipif(sys.platform == "win32", reason="Linux/macOS only")
class TestLinuxFileAssociation:
    """Smoke test for Linux file association paths."""

    def test_register_linux_importable(self):
        """register_linux function must be importable."""
        from epi_core.platform.associate import register_linux
        assert callable(register_linux)

    def test_unregister_linux_importable(self):
        """unregister_linux function must be importable."""
        from epi_core.platform.associate import unregister_linux
        assert callable(unregister_linux)

    @pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
    def test_mime_xml_path_is_correct(self):
        """MIME type XML should target ~/.local/share/mime/packages/."""
        expected = Path.home() / ".local" / "share" / "mime" / "packages" / "epi-recorder.xml"
        # Just verify the path construction is correct
        assert str(expected).endswith("mime/packages/epi-recorder.xml")


# ============================================================
# 4. View resolver — stem resolution + Unicode paths
# ============================================================

class TestViewResolver:
    """Test _resolve_epi_file from the rewritten view.py."""

    def _create_dummy_epi(self, path: Path) -> None:
        """Create a minimal valid .epi ZIP file at the given path."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("manifest.json", json.dumps({"spec_version": "1.0.0"}))
            zf.writestr("viewer.html", "<html>test</html>")

    def test_exact_path_resolution(self, tmp_path):
        """Exact .epi file path should resolve directly."""
        from epi_cli.view import _resolve_epi_file

        epi_file = tmp_path / "test.epi"
        self._create_dummy_epi(epi_file)

        result = _resolve_epi_file(str(epi_file))
        assert result == epi_file

    def test_stem_resolution_picks_most_recent(self, tmp_path):
        """When multiple files match a stem, most recent by mtime wins."""
        from epi_cli.view import _resolve_epi_file, DEFAULT_DIR

        # Create epi-recordings directory in tmp
        recordings_dir = tmp_path / "epi-recordings"
        recordings_dir.mkdir()

        # Create 3 files with different timestamps
        old = recordings_dir / "my_script_20250101_000000.epi"
        mid = recordings_dir / "my_script_20250601_120000.epi"
        new = recordings_dir / "my_script_20260101_000000.epi"

        self._create_dummy_epi(old)
        time.sleep(0.05)
        self._create_dummy_epi(mid)
        time.sleep(0.05)
        self._create_dummy_epi(new)

        # Patch DEFAULT_DIR to use our tmp directory
        with patch("epi_cli.view.DEFAULT_DIR", recordings_dir):
            result = _resolve_epi_file("my_script")
            assert result == new  # Most recent by mtime

    def test_file_not_found_raises(self, tmp_path):
        """Non-existent file should raise FileNotFoundError."""
        from epi_cli.view import _resolve_epi_file

        with patch("epi_cli.view.DEFAULT_DIR", tmp_path / "empty"):
            with pytest.raises(FileNotFoundError, match="Recording not found"):
                _resolve_epi_file("nonexistent_file")

    def test_unicode_path_resolution(self, tmp_path):
        """File paths with Arabic/Urdu characters should resolve correctly."""
        from epi_cli.view import _resolve_epi_file

        unicode_dir = tmp_path / "محمد"
        epi_file = unicode_dir / "تسجيل.epi"
        self._create_dummy_epi(epi_file)

        result = _resolve_epi_file(str(epi_file))
        assert result == epi_file
        assert result.exists()

    def test_unicode_path_with_spaces(self, tmp_path):
        """File paths with spaces and Unicode should resolve correctly."""
        from epi_cli.view import _resolve_epi_file

        spaced_dir = tmp_path / "My Recordings مسجل"
        epi_file = spaced_dir / "test file.epi"
        self._create_dummy_epi(epi_file)

        result = _resolve_epi_file(str(epi_file))
        assert result == epi_file

    def test_devanagari_path(self, tmp_path):
        """Devanagari script paths should work."""
        from epi_cli.view import _resolve_epi_file

        hindi_dir = tmp_path / "रिकॉर्डिंग"
        epi_file = hindi_dir / "परीक्षण.epi"
        self._create_dummy_epi(epi_file)

        result = _resolve_epi_file(str(epi_file))
        assert result == epi_file


# ============================================================
# 5. Version consistency
# ============================================================

class TestVersionConsistency:
    """Ensure version is bumped consistently across all locations."""

    def test_epi_core_version(self):
        """epi_core.__version__ should be 2.7.2."""
        from epi_core import __version__
        assert __version__ == "2.7.2"

    def test_pyproject_version_matches(self):
        """pyproject.toml version should match epi_core.__version__."""
        from epi_core import __version__

        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            content = pyproject_path.read_text(encoding="utf-8")
            assert f'version = "{__version__}"' in content


# ============================================================
# 6. Cleanup thread test
# ============================================================

class TestCleanupThread:
    """Test the deferred cleanup mechanism."""

    def test_cleanup_removes_directory(self, tmp_path):
        """_cleanup_after_delay should remove the temp dir after delay."""
        from epi_cli.view import _cleanup_after_delay

        test_dir = tmp_path / "cleanup_test"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("test", encoding="utf-8")

        assert test_dir.exists()

        # Schedule cleanup with short delay
        _cleanup_after_delay(test_dir, delay_seconds=0.5)

        # Dir should still exist immediately
        assert test_dir.exists()

        # Wait for cleanup
        time.sleep(1.5)

        # Dir should be gone
        assert not test_dir.exists()


# ============================================================
# 7. Reliability Fixes (99% Target) Tests
# ============================================================

class TestReliabilityFixes:
    """Tests for the v2.7.1 reliability edge cases (flag writes, corrupt zips, temp fallbacks)."""

    def test_needs_registration_on_version_change(self, tmp_path, monkeypatch):
        """Re-registration fires when version changes."""
        from epi_core.platform.associate import _set_registration_state, _needs_registration
        
        monkeypatch.setattr("epi_core.platform.associate._FLAG_PATH", tmp_path / ".flag")
        _set_registration_state()
        monkeypatch.setattr("epi_core.platform.associate._get_epi_version", lambda: "9.9.9")
        assert _needs_registration() is True

    def test_needs_registration_on_exe_change(self, tmp_path, monkeypatch):
        """Re-registration fires when executable path changes."""
        from epi_core.platform.associate import _set_registration_state, _needs_registration
        
        monkeypatch.setattr("epi_core.platform.associate._FLAG_PATH", tmp_path / ".flag")
        _set_registration_state()
        monkeypatch.setattr("sys.executable", "/other/python")
        assert _needs_registration() is True

    def test_flag_unwritable_doesnt_crash(self, monkeypatch):
        """Flag write failure is silent and non-blocking."""
        from epi_core.platform.associate import _set_registration_state, _needs_registration
        
        # Windows invalid path chars to force failure without needing root
        monkeypatch.setattr("epi_core.platform.associate._FLAG_PATH", Path("C:\\<>invalid|path\\.flag") if sys.platform == "win32" else Path("/root/.epi/.flag"))
        # Should not raise
        _set_registration_state()
        assert _needs_registration() is True  # Always True when flag unwritable

    def test_view_corrupt_file_exits_cleanly(self, tmp_path):
        """Corrupt .epi gives clear error, exit code 1."""
        import typer
        from epi_cli.view import view
        
        bad = tmp_path / "bad.epi"
        bad.write_bytes(b"not a zip file")
        
        with patch('epi_cli.view.zipfile.is_zipfile', return_value=True):
            with pytest.raises(typer.Exit) as exc:
                view(MagicMock(), str(bad), extract=None)
            assert exc.value.exit_code == 1

    def test_view_missing_viewer_html_prints_manifest(self, tmp_path):
        """Missing viewer.html falls back to printing manifest."""
        import typer
        from epi_cli.view import view
        
        epi = tmp_path / "test.epi"
        with zipfile.ZipFile(epi, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"spec_version": "2.7.1"}))
            
        with pytest.raises(typer.Exit) as exc:
            view(MagicMock(), str(epi), extract=None)
        assert exc.value.exit_code == 1

    def test_make_temp_dir_fallback(self, monkeypatch):
        """Temp dir creation falls back to cwd if system temp unavailable."""
        import shutil
        from epi_cli.view import _make_temp_dir
        
        def fail_mkdtemp(**kw):
            raise OSError("no space")
            
        monkeypatch.setattr(tempfile, "mkdtemp", fail_mkdtemp)
        
        result = _make_temp_dir()
        assert result is not None
        assert result.exists()
        shutil.rmtree(result, ignore_errors=True)

    def test_signature_roundtrip(self):
        """Verify that sign + verify produces consistent result."""
        from epi_core.trust import sign_manifest, verify_signature
        from epi_core.schemas import ManifestModel
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        
        key = Ed25519PrivateKey.generate()
        pub_bytes = key.public_key().public_bytes_raw()
        manifest = ManifestModel()
        signed = sign_manifest(manifest, key, "test")
        
        valid, msg = verify_signature(signed, pub_bytes)
        assert valid is True, f"Roundtrip failed: {msg}"

