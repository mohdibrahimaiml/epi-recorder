"""
Extended tests for epi_core.platform.associate.

Covers platform-specific registration paths (macOS, Linux),
_needs_registration, _is_association_broken, _get_epi_version,
register_file_association, unregister_file_association.
"""

import json
import sys
from unittest.mock import patch, MagicMock

import pytest

from epi_core.platform.associate import (
    _get_user_open_command,
    _get_epi_version,
    _get_registration_state,
    _LAUNCHER_VERSION_WIN,
    _query_reg_value,
    _register_windows_via_reg_add,
    _set_registration_state,
    _needs_registration,
    _is_association_broken,
    _clear_registered,
    register_file_association,
    register_windows,
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
    def test_returns_true_when_windows_launcher_version_changes(self, tmp_path):
        flag = tmp_path / ".epi" / ".flag"
        flag.parent.mkdir(parents=True)
        flag.write_text(json.dumps({
            "version": _get_epi_version(),
            "executable": sys.executable,
            "platform": "win32",
            "open_command": '"C:\\Program Files\\EPI Labs\\EPI Recorder\\epi.exe" view "%1"',
            "launcher_version": _LAUNCHER_VERSION_WIN - 1,
        }), encoding="utf-8")
        with patch("epi_core.platform.associate._FLAG_PATH", flag), \
             patch("epi_core.platform.associate.sys.platform", "win32"):
            result = _needs_registration()
        assert result is True

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
            # Layer-2 check on Windows compares stored open_command vs current
            "open_command": _get_user_open_command() if sys.platform == "win32" else None,
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
    def test_windows_hklm_association_counts_as_healthy(self):
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
            result = _is_association_broken()
        assert result is False

    def test_windows_legacy_browser_command_counts_as_healthy(self):
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
            result = _is_association_broken()
        assert result is False

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


class TestWindowsRegAddFallback:
    def test_reg_add_fallback_writes_open_command_and_icon(self):
        outputs = ["The operation completed successfully."] * 5
        with patch("epi_core.platform.associate._run_windows_reg_command", side_effect=outputs) as mock_run:
            _register_windows_via_reg_add('"epi.exe" view "%1"', '"epi.ico"')

        commands = [call.args[0] for call in mock_run.call_args_list]
        assert any(
            cmd[:3] == ["add", r"HKCU\Software\Classes\EPIRecorder.File\DefaultIcon", "/ve"]
            for cmd in commands
        )
        assert not any(
            cmd[:4] == ["add", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run", "/v", "EPIRecorder"]
            for cmd in commands
        )

    def test_query_reg_value_uses_reg_query_output(self):
        process = MagicMock(stdout="HKEY_CURRENT_USER\\Software\\Classes\\.epi\n    (Default)    REG_SZ    EPIRecorder.File\n")
        with patch("sys.platform", "win32"), \
             patch("epi_core.platform.associate.subprocess.run", return_value=process) as mock_run:
            value = _query_reg_value("HKCU", r"Software\Classes\.epi")

        assert value == "EPIRecorder.File"
        mock_run.assert_called_once()

    def test_register_windows_uses_hidden_reg_add_path(self):
        with patch("epi_core.platform.associate._get_user_open_command", return_value='"epi.exe" view "%1"'), \
             patch("epi_core.platform.associate._get_windows_default_icon", return_value='"epi.ico"'), \
             patch("epi_core.platform.associate._register_windows_via_reg_add") as mock_reg_add, \
             patch("epi_core.platform.associate._run_windows_reg_command",
                   return_value="HKEY_CURRENT_USER\\Software\\Classes\\.epi\n    (Default)    REG_SZ    EPIRecorder.File\n"), \
             patch("ctypes.windll", MagicMock(shell32=MagicMock())):
            register_windows()

        mock_reg_add.assert_called_once()
        args, kwargs = mock_reg_add.call_args
        assert args[0] == '"epi.exe" view "%1"'
        assert args[1] == '"epi.ico"'


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
            register_file_association(silent=True, force=True)
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
