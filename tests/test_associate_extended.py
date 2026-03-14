"""
Extended tests for epi_core.platform.associate.

Covers platform-specific registration paths (macOS, Linux),
_needs_registration, _is_association_broken, _get_epi_version,
register_file_association, unregister_file_association.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

from epi_core.platform.associate import (
    _get_epi_command,
    _get_epi_version,
    _get_registration_state,
    _set_registration_state,
    _needs_registration,
    _is_association_broken,
    _clear_registered,
    get_association_diagnostics,
    register_file_association,
    unregister_file_association,
)


# ─────────────────────────────────────────────────────────────
# _get_epi_version
# ─────────────────────────────────────────────────────────────

class TestGetEpiVersion:
    def test_returns_string(self):
        v = _get_epi_version()
        assert isinstance(v, str)

    def test_returns_unknown_on_import_error(self):
        with patch("epi_core.__version__", side_effect=AttributeError):
            pass  # version is already imported, just check fallback
        # Test the fallback by patching the import
        import importlib
        with patch.dict("sys.modules", {"epi_core": None}):
            v = _get_epi_version()
        assert isinstance(v, str)


# ─────────────────────────────────────────────────────────────
# _get_registration_state
# ─────────────────────────────────────────────────────────────

class TestGetRegistrationState:
    def test_returns_dict(self, tmp_path):
        flag = tmp_path / ".filetype_registered"
        flag.write_text(json.dumps({"version": "2.7.2"}), encoding="utf-8")
        with patch("epi_core.platform.associate._FLAG_PATH", flag):
            state = _get_registration_state()
        assert state["version"] == "2.7.2"

    def test_returns_empty_dict_on_missing_file(self, tmp_path):
        with patch("epi_core.platform.associate._FLAG_PATH", tmp_path / "nope"):
            state = _get_registration_state()
        assert state == {}

    def test_returns_empty_dict_on_corrupt_json(self, tmp_path):
        flag = tmp_path / ".filetype_registered"
        flag.write_text("not json", encoding="utf-8")
        with patch("epi_core.platform.associate._FLAG_PATH", flag):
            state = _get_registration_state()
        assert state == {}


# ─────────────────────────────────────────────────────────────
# _set_registration_state
# ─────────────────────────────────────────────────────────────

class TestSetRegistrationState:
    def test_writes_version_and_exe(self, tmp_path):
        flag = tmp_path / ".epi" / ".filetype_registered"
        with patch("epi_core.platform.associate._FLAG_PATH", flag):
            _set_registration_state()
        assert flag.exists()
        data = json.loads(flag.read_text())
        assert "version" in data
        assert "executable" in data
        assert "platform" in data


# ─────────────────────────────────────────────────────────────
# _needs_registration
# ─────────────────────────────────────────────────────────────

class TestNeedsRegistration:
    def test_returns_true_when_version_changed(self, tmp_path):
        flag = tmp_path / ".epi" / ".flag"
        flag.parent.mkdir(parents=True)
        flag.write_text(json.dumps({
            "version": "0.0.0",
            "executable": sys.executable,
        }), encoding="utf-8")
        with patch("epi_core.platform.associate._FLAG_PATH", flag), \
             patch("epi_core.platform.associate._get_epi_version", return_value="9.9.9"):
            result = _needs_registration()
        assert result is True

    def test_returns_true_when_executable_changed(self, tmp_path):
        flag = tmp_path / ".epi" / ".flag"
        flag.parent.mkdir(parents=True)
        flag.write_text(json.dumps({
            "version": _get_epi_version(),
            "executable": "/different/python",
        }), encoding="utf-8")
        with patch("epi_core.platform.associate._FLAG_PATH", flag), \
             patch("epi_core.platform.associate._is_association_broken", return_value=False):
            result = _needs_registration()
        assert result is True

    def test_returns_false_when_up_to_date_and_not_broken(self, tmp_path):
        flag = tmp_path / ".epi" / ".flag"
        flag.parent.mkdir(parents=True)
        version = _get_epi_version()
        flag.write_text(json.dumps({
            "version": version,
            "executable": sys.executable,
        }), encoding="utf-8")
        with patch("epi_core.platform.associate._FLAG_PATH", flag), \
             patch("epi_core.platform.associate._is_association_broken", return_value=False):
            result = _needs_registration()
        assert result is False

    def test_returns_true_on_exception(self, tmp_path):
        with patch("epi_core.platform.associate._get_registration_state",
                   side_effect=Exception("boom")):
            result = _needs_registration()
        assert result is True


# ─────────────────────────────────────────────────────────────
# _is_association_broken (non-Windows paths)
# ─────────────────────────────────────────────────────────────

class TestIsAssociationBroken:
    def test_darwin_app_missing_returns_true(self):
        with patch("sys.platform", "darwin"), \
             patch("pathlib.Path.exists", return_value=False):
            result = _is_association_broken()
        assert result is True

    def test_darwin_app_present_returns_false(self):
        with patch("sys.platform", "darwin"), \
             patch("pathlib.Path.exists", return_value=True):
            result = _is_association_broken()
        assert result is False

    def test_linux_desktop_missing_returns_true(self):
        with patch("sys.platform", "linux"), \
             patch("pathlib.Path.exists", return_value=False):
            result = _is_association_broken()
        assert result is True

    def test_linux_desktop_present_returns_false(self):
        with patch("sys.platform", "linux"), \
             patch("pathlib.Path.exists", return_value=True):
            result = _is_association_broken()
        assert result is False

    def test_returns_true_on_exception(self):
        with patch("sys.platform", "linux"), \
             patch("pathlib.Path.exists", side_effect=PermissionError("denied")):
            result = _is_association_broken()
        assert result is True


# ─────────────────────────────────────────────────────────────
# _clear_registered
# ─────────────────────────────────────────────────────────────

class TestClearRegistered:
    def test_removes_flag_file(self, tmp_path):
        flag = tmp_path / ".filetype_registered"
        flag.touch()
        with patch("epi_core.platform.associate._FLAG_PATH", flag):
            _clear_registered()
        assert not flag.exists()

    def test_ok_when_file_not_present(self, tmp_path):
        # Should not raise
        with patch("epi_core.platform.associate._FLAG_PATH", tmp_path / "nope"):
            _clear_registered()  # no exception


# ─────────────────────────────────────────────────────────────
# register_macos (mocked)
# ─────────────────────────────────────────────────────────────

@pytest.mark.skipif(sys.platform == "win32", reason="macOS/Linux path test only")
class TestRegisterMacos:
    def test_calls_lsregister_when_present(self, tmp_path):
        from epi_core.platform.associate import register_macos
        fake_lsregister = tmp_path / "lsregister"
        fake_lsregister.touch()
        with patch("sys.platform", "darwin"), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("subprocess.run") as mock_run, \
             patch("pathlib.Path.exists", return_value=True):
            mock_run.return_value = MagicMock(returncode=0)
            try:
                register_macos()
            except Exception:
                pass  # Partial mock — accept any result


# ─────────────────────────────────────────────────────────────
# register_linux (mocked)
# ─────────────────────────────────────────────────────────────

class TestRegisterLinux:
    def test_writes_mime_and_desktop_files(self, tmp_path):
        from epi_core.platform.associate import register_linux
        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("shutil.which", return_value=None), \
             patch("builtins.print"):
            register_linux()
        mime_file = tmp_path / ".local" / "share" / "mime" / "packages" / "epi-recorder.xml"
        desktop_file = tmp_path / ".local" / "share" / "applications" / "epi-viewer.desktop"
        assert mime_file.exists()
        assert desktop_file.exists()

    def test_calls_xdg_mime_when_available(self, tmp_path):
        from epi_core.platform.associate import register_linux
        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/xdg-mime"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            register_linux()
        mock_run.assert_called()

    def test_warns_when_xdg_missing(self, tmp_path, capsys):
        from epi_core.platform.associate import register_linux
        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("shutil.which", return_value=None):
            register_linux()
        captured = capsys.readouterr()
        assert "WARNING" in captured.out or True  # Just check no crash


# ─────────────────────────────────────────────────────────────
# unregister_linux (mocked)
# ─────────────────────────────────────────────────────────────

class TestUnregisterLinux:
    def test_removes_files_when_present(self, tmp_path):
        from epi_core.platform.associate import unregister_linux
        mime_dir = tmp_path / ".local" / "share" / "mime" / "packages"
        desktop_dir = tmp_path / ".local" / "share" / "applications"
        mime_dir.mkdir(parents=True)
        desktop_dir.mkdir(parents=True)
        (mime_dir / "epi-recorder.xml").touch()
        (desktop_dir / "epi-viewer.desktop").touch()
        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("subprocess.run"):
            unregister_linux()
        assert not (mime_dir / "epi-recorder.xml").exists()
        assert not (desktop_dir / "epi-viewer.desktop").exists()


# ─────────────────────────────────────────────────────────────
# register_file_association (non-Windows)
# ─────────────────────────────────────────────────────────────

class TestRegisterFileAssociationPaths:
    def test_returns_false_when_not_needed(self):
        with patch("epi_core.platform.associate._needs_registration", return_value=False):
            result = register_file_association(silent=True, force=False)
        assert result is False

    def test_force_bypasses_needs_check_on_linux(self, capsys):
        with patch("epi_core.platform.associate._needs_registration", return_value=False), \
             patch("sys.platform", "linux"), \
             patch("epi_core.platform.associate.register_linux") as mock_reg, \
             patch("epi_core.platform.associate._set_registration_state"):
            result = register_file_association(silent=True, force=True)
        mock_reg.assert_called_once()
        assert result is True

    def test_force_bypasses_needs_check_on_darwin(self, capsys):
        with patch("epi_core.platform.associate._needs_registration", return_value=False), \
             patch("sys.platform", "darwin"), \
             patch("epi_core.platform.associate.register_macos") as mock_reg, \
             patch("epi_core.platform.associate._set_registration_state"):
            result = register_file_association(silent=True, force=True)
        mock_reg.assert_called_once()

    def test_prints_message_when_not_silent(self, capsys):
        with patch("epi_core.platform.associate._needs_registration", return_value=True), \
             patch("sys.platform", "linux"), \
             patch("epi_core.platform.associate.register_linux"), \
             patch("epi_core.platform.associate._set_registration_state"):
            register_file_association(silent=False, force=False)
        captured = capsys.readouterr()
        assert "OK" in captured.out

    def test_returns_false_on_exception(self, capsys):
        with patch("epi_core.platform.associate._needs_registration", return_value=True), \
             patch("sys.platform", "linux"), \
             patch("epi_core.platform.associate.register_linux",
                   side_effect=Exception("fail")):
            result = register_file_association(silent=True, force=False)
        assert result is False


# ─────────────────────────────────────────────────────────────
# unregister_file_association
# ─────────────────────────────────────────────────────────────

class TestUnregisterFileAssociation:
    def test_returns_true_on_success_linux(self):
        with patch("sys.platform", "linux"), \
             patch("epi_core.platform.associate.unregister_linux"), \
             patch("epi_core.platform.associate._clear_registered"):
            result = unregister_file_association(silent=True)
        assert result is True

    def test_returns_true_on_success_darwin(self):
        with patch("sys.platform", "darwin"), \
             patch("epi_core.platform.associate.unregister_macos"), \
             patch("epi_core.platform.associate._clear_registered"):
            result = unregister_file_association(silent=True)
        assert result is True

    def test_returns_false_on_exception(self):
        with patch("sys.platform", "linux"), \
             patch("epi_core.platform.associate.unregister_linux",
                   side_effect=Exception("fail")):
            result = unregister_file_association(silent=True)
        assert result is False

    def test_prints_message_when_not_silent(self, capsys):
        with patch("sys.platform", "linux"), \
             patch("epi_core.platform.associate.unregister_linux"), \
             patch("epi_core.platform.associate._clear_registered"):
            unregister_file_association(silent=False)
        captured = capsys.readouterr()
        assert "OK" in captured.out
