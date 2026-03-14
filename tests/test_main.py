"""
Tests for epi_cli.main — CLI commands via direct function calls.

Covers: version_callback, version, show_help, associate, unassociate,
keys (generate/list/export/unknown), init, doctor, cli_main.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import click


def _mock_console():
    return MagicMock()


def _call(func, **kwargs):
    """Call a CLI function, return exit code (0 = success)."""
    code = None
    try:
        func(**kwargs)
        code = 0
    except (SystemExit, click.exceptions.Exit) as e:
        code = getattr(e, 'code', getattr(e, 'exit_code', None))
    return code


# ─────────────────────────────────────────────────────────────
# version_callback
# ─────────────────────────────────────────────────────────────

class TestVersionCallback:
    def test_raises_exit_when_true(self):
        from epi_cli.main import version_callback
        with patch("epi_cli.main.console", _mock_console()):
            with pytest.raises((SystemExit, click.exceptions.Exit)):
                version_callback(True)

    def test_does_nothing_when_false(self):
        from epi_cli.main import version_callback
        # Should not raise
        version_callback(False)


# ─────────────────────────────────────────────────────────────
# version command
# ─────────────────────────────────────────────────────────────

class TestVersionCommand:
    def test_prints_version(self):
        from epi_cli.main import version
        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console):
            version()
        mock_console.print.assert_called()


# ─────────────────────────────────────────────────────────────
# show_help command
# ─────────────────────────────────────────────────────────────

class TestShowHelp:
    def test_prints_help(self):
        from epi_cli.main import show_help
        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console):
            show_help()
        mock_console.print.assert_called()


# ─────────────────────────────────────────────────────────────
# associate command
# ─────────────────────────────────────────────────────────────

class TestAssociateCommand:
    def test_skips_when_not_needed(self):
        from epi_cli.main import associate
        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console), \
             patch("epi_core.platform.associate._needs_registration", return_value=False):
            code = _call(associate, force=False)
        assert code == 0

    def test_registers_when_needed(self):
        from epi_cli.main import associate
        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console), \
             patch("epi_core.platform.associate._needs_registration", return_value=True), \
             patch("epi_core.platform.associate.register_file_association", return_value=True):
            code = _call(associate, force=False)
        assert code == 0

    def test_exits_1_on_failure(self):
        from epi_cli.main import associate
        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console), \
             patch("epi_core.platform.associate._needs_registration", return_value=True), \
             patch("epi_core.platform.associate.register_file_association", return_value=False):
            code = _call(associate, force=False)
        assert code == 1

    def test_force_flag(self):
        from epi_cli.main import associate
        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console), \
             patch("epi_core.platform.associate.register_file_association", return_value=True):
            code = _call(associate, force=True)
        assert code == 0


# ─────────────────────────────────────────────────────────────
# unassociate command
# ─────────────────────────────────────────────────────────────

class TestUnassociateCommand:
    def test_success(self):
        from epi_cli.main import unassociate
        with patch("epi_core.platform.associate.unregister_file_association", return_value=True):
            code = _call(unassociate)
        assert code == 0

    def test_failure_exits_1(self):
        from epi_cli.main import unassociate
        with patch("epi_core.platform.associate.unregister_file_association", return_value=False):
            code = _call(unassociate)
        assert code == 1


# ─────────────────────────────────────────────────────────────
# keys command
# ─────────────────────────────────────────────────────────────

class TestKeysCommand:
    def test_generate_succeeds(self, tmp_path):
        from epi_cli.main import keys
        mock_km = MagicMock()
        mock_km.generate_keypair.return_value = (tmp_path / "priv.pem", tmp_path / "pub.pem")
        with patch("epi_cli.main.console", _mock_console()), \
             patch("epi_cli.keys.KeyManager", return_value=mock_km):
            code = _call(keys, action="generate", name="mykey", overwrite=False)
        assert code == 0

    def test_generate_file_exists_exits_1(self, tmp_path):
        from epi_cli.main import keys
        mock_km = MagicMock()
        mock_km.generate_keypair.side_effect = FileExistsError("key exists")
        with patch("epi_cli.main.console", _mock_console()), \
             patch("epi_cli.keys.KeyManager", return_value=mock_km):
            code = _call(keys, action="generate", name="default", overwrite=False)
        assert code == 1

    def test_list_action(self):
        from epi_cli.main import keys
        mock_km = MagicMock()
        mock_km.list_keys.return_value = []
        with patch("epi_cli.main.console", _mock_console()), \
             patch("epi_cli.keys.KeyManager", return_value=mock_km), \
             patch("epi_cli.keys.print_keys_table"):
            code = _call(keys, action="list", name="default", overwrite=False)
        assert code == 0

    def test_export_succeeds(self):
        from epi_cli.main import keys
        mock_km = MagicMock()
        mock_km.export_public_key.return_value = "base64pubkey=="
        with patch("epi_cli.main.console", _mock_console()), \
             patch("epi_cli.keys.KeyManager", return_value=mock_km):
            code = _call(keys, action="export", name="default", overwrite=False)
        assert code == 0

    def test_export_not_found_exits_1(self):
        from epi_cli.main import keys
        mock_km = MagicMock()
        mock_km.export_public_key.side_effect = FileNotFoundError("not found")
        with patch("epi_cli.main.console", _mock_console()), \
             patch("epi_cli.keys.KeyManager", return_value=mock_km):
            code = _call(keys, action="export", name="default", overwrite=False)
        assert code == 1

    def test_unknown_action_exits_1(self):
        from epi_cli.main import keys
        mock_km = MagicMock()
        with patch("epi_cli.main.console", _mock_console()), \
             patch("epi_cli.keys.KeyManager", return_value=mock_km):
            code = _call(keys, action="invalid", name="default", overwrite=False)
        assert code == 1


# ─────────────────────────────────────────────────────────────
# doctor command
# ─────────────────────────────────────────────────────────────

class TestDoctorCommand:
    def test_healthy_system_no_crash(self):
        from epi_cli.main import doctor
        with patch("epi_cli.main.console", _mock_console()), \
             patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
             patch("shutil.which", return_value="/usr/bin/epi"), \
             patch("webbrowser.get"), \
             patch("epi_core.platform.associate.get_association_diagnostics",
                   return_value={"status": "OK", "extension_progid": "EPIRecorder.File", "issues": []}):
            code = _call(doctor)
        assert code == 0

    def test_epi_not_in_path(self):
        from epi_cli.main import doctor
        with patch("epi_cli.main.console", _mock_console()), \
             patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
             patch("shutil.which", return_value=None), \
             patch("sys.platform", "linux"), \
             patch("webbrowser.get"), \
             patch("epi_core.platform.associate.get_association_diagnostics",
                   return_value={"status": "OK", "extension_progid": "EPIRecorder.File", "issues": []}):
            code = _call(doctor)
        assert code == 0  # doctor doesn't exit 1 on issues

    def test_keys_generated(self):
        from epi_cli.main import doctor
        with patch("epi_cli.main.console", _mock_console()), \
             patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=True), \
             patch("shutil.which", return_value="/usr/bin/epi"), \
             patch("webbrowser.get"), \
             patch("epi_core.platform.associate.get_association_diagnostics",
                   return_value={"status": "OK", "extension_progid": "EPIRecorder.File", "issues": []}):
            code = _call(doctor)
        assert code == 0

    def test_file_association_not_registered(self):
        from epi_cli.main import doctor
        with patch("epi_cli.main.console", _mock_console()), \
             patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
             patch("shutil.which", return_value="/usr/bin/epi"), \
             patch("webbrowser.get"), \
             patch("epi_core.platform.associate.get_association_diagnostics",
                   return_value={"status": "OK", "extension_progid": None, "issues": []}):
            code = _call(doctor)
        assert code == 0

    def test_file_association_overridden(self):
        from epi_cli.main import doctor
        with patch("epi_cli.main.console", _mock_console()), \
             patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
             patch("shutil.which", return_value="/usr/bin/epi"), \
             patch("webbrowser.get"), \
             patch("epi_core.platform.associate.get_association_diagnostics",
                   return_value={"status": "OVERRIDDEN", "extension_progid": None,
                                 "issues": ["Windows is forcing '.epi' to open with 'SomeApp'"]}):
            code = _call(doctor)
        assert code == 0

    def test_browser_check_fails(self):
        from epi_cli.main import doctor
        with patch("epi_cli.main.console", _mock_console()), \
             patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
             patch("shutil.which", return_value="/usr/bin/epi"), \
             patch("webbrowser.get", side_effect=Exception("no browser")), \
             patch("epi_core.platform.associate.get_association_diagnostics",
                   return_value={"status": "OK", "extension_progid": "EPIRecorder.File", "issues": []}):
            code = _call(doctor)
        assert code == 0


# ─────────────────────────────────────────────────────────────
# init command
# ─────────────────────────────────────────────────────────────

class TestInitCommand:
    def test_init_no_crash(self, tmp_path):
        from epi_cli.main import init
        import os
        original = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch("epi_cli.main.console", _mock_console()), \
                 patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
                 patch("subprocess.run"):
                code = _call(init, demo_filename="test_demo.py", no_open=True)
        finally:
            os.chdir(original)
        assert code == 0

    def test_init_creates_demo_script(self, tmp_path):
        from epi_cli.main import init
        import os
        original = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch("epi_cli.main.console", _mock_console()), \
                 patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
                 patch("subprocess.run"):
                init(demo_filename="my_demo.py", no_open=True)
        finally:
            os.chdir(original)
        assert (tmp_path / "my_demo.py").exists()

    def test_init_skips_existing_script(self, tmp_path):
        from epi_cli.main import init
        import os
        original = os.getcwd()
        try:
            os.chdir(tmp_path)
            demo = tmp_path / "existing.py"
            demo.write_text("# existing", encoding="utf-8")
            with patch("epi_cli.main.console", _mock_console()), \
                 patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
                 patch("subprocess.run"):
                init(demo_filename="existing.py", no_open=True)
        finally:
            os.chdir(original)
        # File content unchanged
        assert demo.read_text() == "# existing"


# ─────────────────────────────────────────────────────────────
# main_callback
# ─────────────────────────────────────────────────────────────

class TestMainCallback:
    def test_no_crash(self):
        from epi_cli.main import main_callback
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
             patch("epi_core.platform.associate.register_file_association", return_value=False):
            main_callback(version=False)


# ─────────────────────────────────────────────────────────────
# cli_main
# ─────────────────────────────────────────────────────────────

class TestCliMain:
    def test_no_crash_when_called(self):
        from epi_cli.main import cli_main
        with patch("epi_cli.main.app") as mock_app, \
             patch("sys.platform", "linux"):  # skip Windows stdout rewrap
            cli_main()
        mock_app.assert_called_once()
