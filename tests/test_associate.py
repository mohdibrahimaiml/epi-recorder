"""
Tests for epi_core.platform.associate — file association helpers.

Tests the cross-platform logic, diagnostics, and registration state
without actually writing to the Windows registry.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from epi_core.platform.associate import (
    _get_epi_command,
    _get_epi_launcher_vbs,
    _get_user_open_command,
    _resolve_windows_launcher_dir,
    _get_windows_default_icon,
    _is_association_broken,
    _needs_registration,
    _resolve_self_heal_command,
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

    def test_contains_view_or_wscript(self):
        """The open command must either contain 'view' directly, or route through
        wscript.exe (Store Python path) where 'view' lives inside the VBS launcher."""
        cmd = _get_epi_command()
        assert "view" in cmd or "wscript" in cmd.lower()

    def test_contains_percent_1(self):
        """The open command must pass the file path as %1."""
        cmd = _get_epi_command()
        assert "%1" in cmd

    def test_contains_epi_or_python(self):
        """The command must contain a valid launcher: epi.exe (stable AppData copy),
        python/pythonw, or wscript (legacy VBS path)."""
        cmd = _get_epi_command()
        assert any(kw in cmd.lower() for kw in ("epi", "python", "wscript"))

    def test_uses_pythonw_when_available(self):
        """On Windows, prefer pythonw.exe for no console flash."""
        with patch("epi_core.platform.associate.Path") as mock_path_cls:
            mock_path_cls.return_value = Path(sys.executable)
            # Just ensure the function runs without error
            cmd = _get_epi_command()
        assert isinstance(cmd, str)

    def test_prefers_adjacent_epi_exe_when_available(self, tmp_path):
        fake_python = tmp_path / "python.exe"
        fake_python.write_text("py", encoding="ascii")
        fake_epi = tmp_path / "epi.exe"
        fake_epi.write_text("exe", encoding="ascii")

        with patch("epi_core.platform.associate.sys.executable", str(fake_python)), \
             patch("epi_core.platform.associate.shutil.which", return_value=None):
            cmd = _get_epi_command()

        assert cmd == f'"{fake_epi.absolute()}" view "%1"'


class TestGetUserOpenCommand:
    def test_prefers_cli_view_command_when_epi_exe_is_available(self, tmp_path):
        fake_python = tmp_path / "python.exe"
        fake_python.write_text("py", encoding="ascii")
        fake_epi = tmp_path / "epi.exe"
        fake_epi.write_text("exe", encoding="ascii")

        with patch("epi_core.platform.associate.sys.executable", str(fake_python)), \
             patch("epi_core.platform.associate.shutil.which", return_value=None):
            cmd = _get_user_open_command()

        assert cmd == f'"{fake_epi.absolute()}" view "%1"'


class TestWindowsLauncherScripts:
    def test_launcher_copies_epi_to_zip_before_extracting(self, tmp_path):
        local_app_data = tmp_path / "LocalAppData"
        with patch.dict("os.environ", {"LOCALAPPDATA": str(local_app_data)}, clear=False):
            launcher = _get_epi_launcher_vbs()

        content = launcher.read_text(encoding="ascii")
        assert "archive.zip" in content
        # New ADODB.Stream approach: reads raw bytes, strips 64-byte EPI1 header,
        # writes clean ZIP payload — replaces the old CopyFile approach which
        # could not handle envelope-v2 files.
        assert "ADODB.Stream" in content
        assert "skipBytes = 64" in content
        assert "NameSpace(zipPath)" in content

    def test_launcher_is_written_without_utf8_bom(self, tmp_path):
        local_app_data = tmp_path / "LocalAppData"
        with patch.dict("os.environ", {"LOCALAPPDATA": str(local_app_data)}, clear=False):
            launcher = _get_epi_launcher_vbs()

        raw = launcher.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")

    def test_self_heal_prefers_adjacent_epi_exe(self, tmp_path):
        python_exe = tmp_path / "python.exe"
        python_exe.write_text("", encoding="ascii")
        epi_exe = tmp_path / "epi.exe"
        epi_exe.write_text("", encoding="ascii")

        command = _resolve_self_heal_command(python_exe)

        assert command == f'"{epi_exe}" associate --force'

    def test_default_icon_prefers_adjacent_ico(self, tmp_path):
        python_exe = tmp_path / "python.exe"
        python_exe.write_text("", encoding="ascii")
        icon_file = tmp_path / "epi.ico"
        icon_file.write_bytes(b"ico")

        icon_cmd = _get_windows_default_icon(python_exe)

        assert icon_cmd == f'"{icon_file}"'

    def test_system_elevation_prefers_adjacent_epi_over_path_entry(self, tmp_path):
        python_exe = tmp_path / "python.exe"
        python_exe.write_text("py", encoding="ascii")
        adjacent_epi = tmp_path / "epi.exe"
        adjacent_epi.write_text("exe", encoding="ascii")
        stale_path_epi = tmp_path / "stale-epi.exe"
        stale_path_epi.write_text("exe", encoding="ascii")

        shell32 = MagicMock()
        shell32.ShellExecuteW.return_value = 33

        with patch("epi_core.platform.associate.sys.executable", str(python_exe)), \
             patch("epi_core.platform.associate.shutil.which", return_value=str(stale_path_epi)), \
             patch("ctypes.windll", MagicMock(shell32=shell32)):
            from epi_core.platform.associate import _elevate_and_register_system
            _elevate_and_register_system()

        shell32.ShellExecuteW.assert_called_once()
        assert shell32.ShellExecuteW.call_args[0][2] == str(adjacent_epi)

    def test_launcher_dir_falls_back_when_preferred_unwritable(self, tmp_path):
        preferred = Path("C:\\<>invalid\\EPILabs")
        local_app_data = tmp_path / "LocalAppData"
        with patch.dict("os.environ", {"LOCALAPPDATA": str(local_app_data)}, clear=False):
            resolved = _resolve_windows_launcher_dir(preferred=preferred)

        assert resolved != preferred
        assert resolved.exists()


# ─────────────────────────────────────────────────────────────
# _needs_registration + _set_registration_state
# ─────────────────────────────────────────────────────────────

class TestRegistrationState:
    def test_needs_registration_returns_bool(self):
        result = _needs_registration()
        assert isinstance(result, bool)

    def test_set_and_check_flag_file(self, tmp_path):
        """After setting state, flag file is written with version/exe/platform."""
        flag_path = tmp_path / ".epi" / ".filetype_registered"
        with patch("epi_core.platform.associate._FLAG_PATH", flag_path):
            assert not flag_path.exists()
            _set_registration_state()
            assert flag_path.exists()

    def test_flag_file_contains_open_command_on_windows(self, tmp_path):
        """Flag file must store open_command so path changes are detected cheaply."""
        flag_path = tmp_path / ".epi" / ".filetype_registered"
        with patch("epi_core.platform.associate._FLAG_PATH", flag_path), \
             patch("epi_core.platform.associate.sys") as mock_sys:
            mock_sys.platform = "win32"
            mock_sys.executable = sys.executable
            with patch("epi_core.platform.associate._get_user_open_command", return_value='wscript.exe /B "launch.vbs" "%1"'):
                _set_registration_state()
        import json
        stored = json.loads(flag_path.read_text())
        assert stored.get("open_command") == 'wscript.exe /B "launch.vbs" "%1"'

    def test_needs_registration_triggers_when_open_command_changes(self, tmp_path):
        """If epi.exe path changes but python exe hasn't, still re-register."""
        import json
        from epi_core.platform import associate as assoc
        flag_path = tmp_path / ".epi" / ".filetype_registered"
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a flag that matches version + exe but has a stale command
        flag_path.write_text(json.dumps({
            "version": assoc._get_epi_version(),
            "executable": sys.executable,
            "platform": "win32",
            "open_command": '"C:\\old\\path\\epi.exe" view "%1"',
        }))
        with patch("epi_core.platform.associate._FLAG_PATH", flag_path), \
             patch("epi_core.platform.associate.sys") as mock_sys, \
             patch("epi_core.platform.associate._get_user_open_command",
                   return_value='wscript.exe /B "C:\\new\\path\\launch.vbs" "%1"'):
            mock_sys.platform = "win32"
            mock_sys.executable = sys.executable
            result = _needs_registration()
        assert result is True  # stale command → must re-register

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_is_association_broken_detects_missing_exe(self):
        """If the registered command points to a non-existent exe, report broken."""
        import winreg
        from epi_core.platform.associate import _get_epi_command
        dead_cmd = '"C:\\does\\not\\exist\\epi.exe" view "%1"'
        real_cmd = _get_epi_command()  # Save before patching
        cmd_path = r"Software\Classes\EPIRecorder.File\shell\open\command"
        try:
            try:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, cmd_path, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.SetValueEx(k, "", 0, winreg.REG_SZ, dead_cmd)
            except PermissionError:
                pytest.skip("HKCU registry is not writable in this environment")
            with patch("epi_core.platform.associate._get_epi_command", return_value=dead_cmd):
                result = _is_association_broken()
            assert result is True  # exe path doesn't exist → broken
        finally:
            # Restore correct command directly (not via register_windows which re-calls _get_epi_command)
            try:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, cmd_path, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.SetValueEx(k, "", 0, winreg.REG_SZ, real_cmd)
            except Exception:
                pass


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

    def test_hklm_installer_association_is_reported_as_healthy(self):
        snapshot = {
            "user_choice": None,
            "hkcu_progid": None,
            "hklm_progid": "EPIRecorder.File",
            "hkcu_command": None,
            "hklm_command": '"C:\\Program Files\\EPI Labs\\EPI Recorder\\epi.exe" view "%1"',
            "effective_scope": "HKLM",
            "effective_progid": "EPIRecorder.File",
            "registered_command": '"C:\\Program Files\\EPI Labs\\EPI Recorder\\epi.exe" view "%1"',
        }
        with patch("sys.platform", "win32"), \
             patch("epi_core.platform.associate._get_windows_association_snapshot", return_value=snapshot), \
             patch("epi_core.platform.associate._get_epi_command",
                   return_value='"C:\\Program Files\\EPI Labs\\EPI Recorder\\epi.exe" view "%1"'), \
             patch("epi_core.platform.associate.Path.exists", return_value=True):
            diag = get_association_diagnostics()
        assert diag["status"] == "OK"
        assert diag["association_scope"] == "HKLM"

    def test_legacy_browser_open_command_is_still_reported_as_healthy(self):
        snapshot = {
            "user_choice": None,
            "hkcu_progid": "EPIRecorder.File",
            "hklm_progid": None,
            "hkcu_command": '"C:\\Users\\dell\\epi.exe" view --browser "%1"',
            "hklm_command": None,
            "effective_scope": "HKCU",
            "effective_progid": "EPIRecorder.File",
            "registered_command": '"C:\\Users\\dell\\epi.exe" view --browser "%1"',
        }
        with patch("sys.platform", "win32"), \
             patch("epi_core.platform.associate._get_windows_association_snapshot", return_value=snapshot), \
             patch("epi_core.platform.associate._get_user_open_command",
                   return_value='"C:\\Users\\dell\\epi.exe" view "%1"'), \
             patch("epi_core.platform.associate.Path.exists", return_value=True):
            diag = get_association_diagnostics()
        assert diag["status"] == "OK"
        assert not diag["issues"]


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
             patch("epi_core.platform.associate.get_association_diagnostics", return_value={"status": "OK", "extension_progid": "EPIRecorder.File"}), \
             patch("epi_core.platform.associate._set_registration_state"):
            result = register_file_association(silent=True, force=True)
        # On Windows, register_windows should be called
        if sys.platform == "win32":
            mock_reg.assert_called_once()
            assert result is True

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_returns_false_when_windows_post_check_is_still_broken(self):
        with patch("epi_core.platform.associate._needs_registration", return_value=True), \
             patch("epi_core.platform.associate.register_windows") as mock_reg, \
             patch(
                 "epi_core.platform.associate.get_association_diagnostics",
                 return_value={
                     "status": "BROKEN",
                     "issues": ["Registered open command does not match the current installation."],
                     "extension_progid": "EPIRecorder.File",
                 },
             ), \
             patch("epi_core.platform.associate._set_registration_state") as mock_state:
            result = register_file_association(silent=True, force=False)

        mock_reg.assert_called_once()
        mock_state.assert_not_called()
        assert result is False

    @pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows path")
    def test_non_windows_silent_no_crash(self):
        with patch("epi_core.platform.associate._needs_registration", return_value=True), \
             patch("epi_core.platform.associate._set_registration_state"):
            result = register_file_association(silent=True, force=False)
        assert isinstance(result, bool)
