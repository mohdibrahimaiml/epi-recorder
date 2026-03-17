"""
Tests for epi_cli.main — CLI commands via direct function calls.

Covers: version_callback, version, show_help, associate, unassociate,
keys (generate/list/export/unknown), init, doctor, cli_main.
"""

import sys
import json
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from uuid import uuid4
from datetime import datetime

import pytest
import click

from epi_core.schemas import ManifestModel


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

_DIAG_PATCH = patch("epi_cli.main._print_association_diagnostics")
_DIAG_STUB = {"status": "OK", "issues": [], "extension_progid": "EPIRecorder.File",
               "registered_command": '"epi.exe" view "%1"', "user_choice": None}


class TestAssociateCommand:
    def test_skips_when_not_needed(self):
        from epi_cli.main import associate
        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console), \
             patch("epi_core.platform.associate._needs_registration", return_value=False), \
             _DIAG_PATCH:
            code = _call(associate, force=False, system=False, elevated=False)
        assert code == 0

    def test_registers_when_needed(self):
        from epi_cli.main import associate
        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console), \
             patch("epi_core.platform.associate._needs_registration", return_value=True), \
             patch("epi_core.platform.associate.register_file_association", return_value=True), \
             _DIAG_PATCH:
            code = _call(associate, force=False, system=False, elevated=False)
        assert code == 0

    def test_exits_1_on_failure(self):
        from epi_cli.main import associate
        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console), \
             patch("epi_core.platform.associate._needs_registration", return_value=True), \
             patch("epi_core.platform.associate.register_file_association", return_value=False), \
             _DIAG_PATCH:
            code = _call(associate, force=False, system=False, elevated=False)
        assert code == 1

    def test_force_flag(self):
        from epi_cli.main import associate
        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console), \
             patch("epi_core.platform.associate.register_file_association", return_value=True), \
             _DIAG_PATCH:
            code = _call(associate, force=True, system=False, elevated=False)
        assert code == 0

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_system_flag_elevated_writes_hklm(self):
        """With --system --elevated (already admin), calls register_windows_system."""
        from epi_cli.main import associate
        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console), \
             patch("epi_core.platform.associate.register_windows_system") as mock_sys_reg, \
             patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=True), \
             _DIAG_PATCH:
            code = _call(associate, force=False, system=True, elevated=True)
        mock_sys_reg.assert_called_once()
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
        content = (tmp_path / "my_demo.py").read_text(encoding="utf-8")
        assert "from epi_recorder import record" in content
        assert 'record(str(output_file)' in content

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

    def test_init_runs_python_script_directly(self, tmp_path):
        from epi_cli.main import init
        import os
        original = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch("epi_cli.main.console", _mock_console()), \
                 patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
                 patch("subprocess.run") as mock_run:
                init(demo_filename="my_demo.py", no_open=True)
        finally:
            os.chdir(original)
        mock_run.assert_called_once()
        args = mock_run.call_args.args[0]
        assert args[0].endswith("python.exe") or args[0].endswith("python") or "python" in args[0].lower()
        assert args[1] == "my_demo.py"


def _write_analyzed_artifact(path: Path, steps_recorded: int) -> None:
    steps = "".join(f'{{"index":{i},"kind":"test","content":{{}}}}\n' for i in range(steps_recorded)).encode("utf-8")
    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=datetime.utcnow(),
        file_manifest={"steps.jsonl": "placeholder"},
    )
    analysis = {
        "fault_detected": False,
        "mode": "policy_grounded",
        "coverage": {
            "steps_recorded": steps_recorded,
            "coverage_percentage": 0 if steps_recorded == 0 else 100,
        },
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip")
        zf.writestr("manifest.json", manifest.model_dump_json())
        zf.writestr("steps.jsonl", steps)
        zf.writestr("analysis.json", json.dumps(analysis))
        zf.writestr("viewer.html", "<html></html>")


class TestAnalyzeCommand:
    def test_zero_step_artifact_reports_no_data(self, tmp_path):
        from epi_cli.main import analyze
        artifact = tmp_path / "empty.epi"
        _write_analyzed_artifact(artifact, steps_recorded=0)
        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console):
            code = _call(analyze, epi_file=str(artifact))
        assert code == 0
        printed = "\n".join(str(call.args[0]) for call in mock_console.print.call_args_list if call.args)
        assert "No data to analyze" in printed
        assert "No anomalies detected" not in printed

    def test_nonempty_artifact_keeps_clean_message(self, tmp_path):
        from epi_cli.main import analyze
        artifact = tmp_path / "normal.epi"
        _write_analyzed_artifact(artifact, steps_recorded=3)
        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console):
            code = _call(analyze, epi_file=str(artifact))
        assert code == 0
        printed = "\n".join(str(call.args[0]) for call in mock_console.print.call_args_list if call.args)
        assert "No anomalies detected" in printed

    def test_primary_fault_overrides_false_fault_detected_flag(self, tmp_path):
        from epi_cli.main import analyze
        artifact = tmp_path / "contradictory.epi"
        manifest = ManifestModel(
            workflow_id=uuid4(),
            created_at=datetime.utcnow(),
            file_manifest={"steps.jsonl": "placeholder"},
        )
        analysis = {
            "fault_detected": False,
            "mode": "policy_grounded",
            "coverage": {"steps_recorded": 3, "coverage_percentage": 100},
            "primary_fault": {
                "fault_type": "POLICY_VIOLATION",
                "severity": "critical",
                "step_number": 2,
                "rule_id": "R004",
                "rule_name": "Never Output Secrets",
                "plain_english": "A prohibited secret-like token was found in output.",
            },
        }
        with zipfile.ZipFile(artifact, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("manifest.json", manifest.model_dump_json())
            zf.writestr("steps.jsonl", '{"index":0,"kind":"test","content":{}}\n')
            zf.writestr("analysis.json", json.dumps(analysis))
            zf.writestr("viewer.html", "<html></html>")

        mock_console = _mock_console()
        with patch("epi_cli.main.console", mock_console):
            code = _call(analyze, epi_file=str(artifact))
        assert code == 0
        printed = "\n".join(str(call.args[0]) for call in mock_console.print.call_args_list if call.args)
        assert "FAULT DETECTED" in printed
        assert "No anomalies detected" not in printed


# ─────────────────────────────────────────────────────────────
# main_callback
# ─────────────────────────────────────────────────────────────

class TestMainCallback:
    def test_no_crash(self):
        from epi_cli.main import main_callback
        ctx = MagicMock(invoked_subcommand="run")
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
             patch("epi_cli.main._auto_repair_windows_association") as mock_repair:
            main_callback(ctx=ctx, version=False)
        mock_repair.assert_called_once()


class TestAutoRepairWindowsAssociation:
    def test_skips_non_windows(self):
        from epi_cli.main import _auto_repair_windows_association
        with patch("sys.platform", "linux"), \
             patch("epi_core.platform.associate.register_file_association") as mock_register:
            _auto_repair_windows_association(interactive=True, command_name="run")
        mock_register.assert_not_called()

    def test_skips_associate_command(self):
        from epi_cli.main import _auto_repair_windows_association
        with patch("sys.platform", "win32"), \
             patch("epi_core.platform.associate.register_file_association") as mock_register:
            _auto_repair_windows_association(interactive=True, command_name="associate")
        mock_register.assert_not_called()

    def test_warns_when_registration_still_broken(self):
        from epi_cli.main import _auto_repair_windows_association
        mock_console = _mock_console()
        diag = {"status": "BROKEN", "extension_progid": None, "issues": ["missing"]}
        with patch("epi_cli.main.console", mock_console), \
             patch("sys.platform", "win32"), \
             patch("epi_core.platform.associate.register_file_association", return_value=False), \
             patch("epi_core.platform.associate.get_association_diagnostics", return_value=diag):
            _auto_repair_windows_association(interactive=True, command_name="run")
        assert mock_console.print.call_count >= 3

    def test_prints_success_note_for_interactive_run_commands(self):
        from epi_cli.main import _auto_repair_windows_association
        mock_console = _mock_console()
        diag = {"status": "OK", "extension_progid": "EPIRecorder.File", "issues": []}
        with patch("epi_cli.main.console", mock_console), \
             patch("sys.platform", "win32"), \
             patch("epi_core.platform.associate.register_file_association", return_value=True), \
             patch("epi_core.platform.associate.get_association_diagnostics", return_value=diag):
            _auto_repair_windows_association(interactive=True, command_name="view")
        mock_console.print.assert_called_once()


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
