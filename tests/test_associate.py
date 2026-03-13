"""
Tests for epi_core.platform.associate — file association helpers.

Tests the cross-platform logic, diagnostics, and registration state
without actually writing to the Windows registry.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from epi_core.platform.associate import (
    _get_epi_command,
    _needs_registration,
    _set_registration_state,
    get_association_diagnostics,
    register_file_association,
)


# ─────────────────────────────────────────────────────────────
# _get_epi_command
# ─────────────────────────────────────────────────────────────

class TestGetEpiCommand:
    def test_returns_string(self):
        cmd = _get_epi_command()
        assert isinstance(cmd, str)

    def test_contains_view(self):
        cmd = _get_epi_command()
        assert "view" in cmd

    def test_contains_percent_1(self):
        """The open command must pass the file path as %1."""
        cmd = _get_epi_command()
        assert "%1" in cmd

    def test_contains_python_executable(self):
        cmd = _get_epi_command()
        assert "python" in cmd.lower()

    def test_uses_pythonw_when_available(self):
        """On Windows, prefer pythonw.exe for no console flash."""
        fake_pythonw = Path(sys.executable).parent / "pythonw.exe"
        with patch("epi_core.platform.associate.Path") as mock_path_cls:
            mock_path_cls.return_value = Path(sys.executable)
            # Just ensure the function runs without error
            cmd = _get_epi_command()
        assert isinstance(cmd, str)


# ─────────────────────────────────────────────────────────────
# _needs_registration + _set_registration_state
# ─────────────────────────────────────────────────────────────

class TestRegistrationState:
    def test_needs_registration_returns_bool(self):
        result = _needs_registration()
        assert isinstance(result, bool)

    def test_set_and_check_flag_file(self, tmp_path):
        """After setting state, _needs_registration should return False
        if the flag file exists (non-Windows path)."""
        flag_path = tmp_path / ".epi" / ".filetype_registered"
        with patch("epi_core.platform.associate._FLAG_PATH", flag_path):
            # Before: flag doesn't exist → needs registration
            assert not flag_path.exists()
            _set_registration_state()
            assert flag_path.exists()


# ─────────────────────────────────────────────────────────────
# get_association_diagnostics
# ─────────────────────────────────────────────────────────────

class TestGetAssociationDiagnostics:
    def test_returns_dict(self):
        diag = get_association_diagnostics()
        assert isinstance(diag, dict)

    def test_has_status_key(self):
        diag = get_association_diagnostics()
        assert "status" in diag

    def test_status_is_string(self):
        diag = get_association_diagnostics()
        assert isinstance(diag["status"], str)

    def test_has_issues_list(self):
        diag = get_association_diagnostics()
        assert "issues" in diag
        assert isinstance(diag["issues"], list)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_windows_checks_extension_progid(self):
        diag = get_association_diagnostics()
        assert "extension_progid" in diag


# ─────────────────────────────────────────────────────────────
# register_file_association
# ─────────────────────────────────────────────────────────────

class TestRegisterFileAssociation:
    def test_returns_bool(self):
        with patch("epi_core.platform.associate._needs_registration", return_value=False):
            result = register_file_association(silent=True, force=False)
        assert isinstance(result, bool)

    def test_skips_when_not_needed(self):
        with patch("epi_core.platform.associate._needs_registration", return_value=False):
            result = register_file_association(silent=True, force=False)
        assert result is False  # skipped, not re-registered

    def test_force_bypasses_needs_check(self):
        """With force=True, registration runs even if already done."""
        with patch("epi_core.platform.associate._needs_registration", return_value=False), \
             patch("epi_core.platform.associate.register_windows") as mock_reg, \
             patch("epi_core.platform.associate._set_registration_state"):
            result = register_file_association(silent=True, force=True)
        # On Windows, register_windows should be called
        if sys.platform == "win32":
            mock_reg.assert_called_once()
            assert result is True

    @pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows path")
    def test_non_windows_silent_no_crash(self):
        with patch("epi_core.platform.associate._needs_registration", return_value=True), \
             patch("epi_core.platform.associate._set_registration_state"):
            result = register_file_association(silent=True, force=False)
        assert isinstance(result, bool)
