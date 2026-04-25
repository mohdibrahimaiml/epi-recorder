"""
Extended tests for epi_cli.run — _verify_recording edge cases and run() function.
"""

import base64
import hashlib
import json
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from uuid import uuid4

import click

from epi_core.schemas import ManifestModel
from epi_core.serialize import get_canonical_hash
from epi_core.time_utils import utc_now, utc_now_iso
from epi_core.workspace import RecordingWorkspaceError


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_epi(tmp_path: Path, signed: bool = False, include_public_key: bool = True) -> Path:
    steps = b'{"index":0,"kind":"test","content":{}}\n'
    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=utc_now(),
        cli_command="python test.py",
        file_manifest={"steps.jsonl": _sha256(steps)},
    )

    if signed:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from epi_core.trust import sign_manifest
        key = Ed25519PrivateKey.generate()
        manifest = sign_manifest(manifest, key, "default")
        if not include_public_key:
            # Strip the public key after signing
            d = manifest.model_dump()
            d["public_key"] = None
            manifest = ManifestModel(**d)

    epi = tmp_path / "test.epi"
    with zipfile.ZipFile(epi, "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip")
        zf.writestr("manifest.json", manifest.model_dump_json())
        zf.writestr("steps.jsonl", steps)
        zf.writestr("viewer.html", "<html></html>")
    return epi


def _make_legacy_base64_public_key_epi(tmp_path: Path) -> Path:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    steps = b'{"index":0,"kind":"test","content":{}}\n'
    key = Ed25519PrivateKey.generate()
    public_key_bytes = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=utc_now(),
        cli_command="python test.py",
        file_manifest={"steps.jsonl": _sha256(steps)},
        public_key=base64.b64encode(public_key_bytes).decode("utf-8"),
    )
    manifest_hash = get_canonical_hash(manifest, exclude_fields={"signature"})
    signature_hex = key.sign(bytes.fromhex(manifest_hash)).hex()
    manifest = ManifestModel(
        **{
            **manifest.model_dump(),
            "signature": f"ed25519:default:{signature_hex}",
        }
    )

    epi = tmp_path / "legacy_base64_pk.epi"
    with zipfile.ZipFile(epi, "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip")
        zf.writestr("manifest.json", manifest.model_dump_json())
        zf.writestr("steps.jsonl", steps)
        zf.writestr("viewer.html", "<html></html>")
    return epi


# ─────────────────────────────────────────────────────────────
# _verify_recording edge cases (uncovered paths)
# ─────────────────────────────────────────────────────────────

class TestVerifyRecordingEdgeCases:
    def test_signature_without_public_key_fails(self, tmp_path):
        from epi_cli.run import _verify_recording
        epi = _make_epi(tmp_path, signed=True, include_public_key=False)
        success, msg = _verify_recording(epi)
        assert not success
        assert "public key" in msg.lower() or "key" in msg.lower()

    def test_invalid_signature_returns_false(self, tmp_path):
        """Corrupt the public_key bytes to cause verification failure."""
        from epi_cli.run import _verify_recording
        steps = b'{"index":0}\n'
        manifest_data = {
            "workflow_id": str(uuid4()),
            "created_at": utc_now_iso(),
            "file_manifest": {"steps.jsonl": _sha256(steps)},
            "signature": "ed25519:default:" + "aa" * 64,  # invalid sig
            "public_key": "bb" * 32,  # valid hex but wrong key
        }
        epi = tmp_path / "bad_sig.epi"
        with zipfile.ZipFile(epi, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("manifest.json", json.dumps(manifest_data))
            zf.writestr("steps.jsonl", steps)
        success, msg = _verify_recording(epi)
        assert not success

    def test_legacy_base64_public_key_signature_verifies(self, tmp_path):
        from epi_cli.run import _verify_recording

        epi = _make_legacy_base64_public_key_epi(tmp_path)
        success, msg = _verify_recording(epi)
        assert success is True
        assert "signed" in msg.lower()


# ─────────────────────────────────────────────────────────────
# run() function tests
# ─────────────────────────────────────────────────────────────

def _call_run(tmp_path, script_name="test_script.py",
              no_verify=False, no_open=False, goal=None, notes=None,
              metric=None, approved_by=None, tag=None,
              verify_result=(True, "OK"), proc_rc=0, step_count=1):
    """Helper to call the run() function with mocked subprocess and packing."""
    from epi_cli.run import run
    script = tmp_path / script_name
    script.write_text("print('hello')", encoding="utf-8")

    recordings_dir = tmp_path / "epi-recordings"
    recordings_dir.mkdir(exist_ok=True)

    mock_proc = MagicMock()
    mock_proc.wait.return_value = proc_rc

    exit_code = None
    try:
        with patch("epi_cli.run.DEFAULT_DIR", recordings_dir), \
             patch("epi_cli.run.console", MagicMock()), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("epi_cli.run.save_environment_snapshot"), \
             patch("epi_cli.run.build_env_for_child", return_value={}), \
             patch("epi_cli.run.EPIContainer.pack",
                   side_effect=lambda ws, m, out, **kw: _create_fake_epi(out, ws, step_count=step_count)), \
             patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
             patch("epi_cli.run._verify_recording", return_value=verify_result), \
             patch("epi_cli.run._open_viewer", return_value=True):
            run(
                script=script,
                no_verify=no_verify,
                no_open=no_open,
                goal=goal,
                notes=notes,
                metric=metric,
                approved_by=approved_by,
                tag=tag,
            )
    except (SystemExit, click.exceptions.Exit) as e:
        exit_code = getattr(e, 'code', getattr(e, 'exit_code', None))

    return exit_code


def _create_fake_epi(out_path: Path, workspace: Path, step_count: int = 1):
    """Create a minimal .epi at out_path for testing."""
    steps = "".join(f'{{"index":{i}}}\n' for i in range(step_count)).encode("utf-8")
    if step_count > 0:
        (workspace / "steps.jsonl").write_bytes(steps)
    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=utc_now(),
        file_manifest={"steps.jsonl": _sha256(steps)},
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip")
        zf.writestr("manifest.json", manifest.model_dump_json())
        zf.writestr("steps.jsonl", steps)
        zf.writestr("viewer.html", "<html></html>")


class TestRunFunction:
    def test_successful_run_exits_0(self, tmp_path):
        code = _call_run(tmp_path)
        assert code == 0

    def test_zero_step_run_exits_1(self, tmp_path):
        code = _call_run(tmp_path, step_count=0)
        assert code == 1

    def test_no_verify_flag(self, tmp_path):
        code = _call_run(tmp_path, no_verify=True)
        assert code == 0

    def test_no_open_flag(self, tmp_path):
        code = _call_run(tmp_path, no_open=True)
        assert code == 0

    def test_with_goal_and_tags(self, tmp_path):
        code = _call_run(tmp_path, goal="Test accuracy", tag=["ml", "eval"])
        assert code == 0

    def test_with_metric_key_value(self, tmp_path):
        code = _call_run(tmp_path, metric=["accuracy=0.95", "loss=0.05"])
        assert code == 0

    def test_with_invalid_metric_format(self, tmp_path):
        """Metrics without = should warn but not crash."""
        code = _call_run(tmp_path, metric=["no_equals"])
        assert code == 0

    def test_script_not_found_no_matches_exits_1(self, tmp_path):
        from epi_cli.run import run
        import click
        script = tmp_path / "nonexistent.py"
        code = None
        try:
            with patch("epi_cli.run.console", MagicMock()), \
                 patch("pathlib.Path.cwd", return_value=tmp_path):
                run(script=script, no_verify=False, no_open=False,
                    goal=None, notes=None, metric=None, approved_by=None, tag=None)
        except (SystemExit, click.exceptions.Exit) as e:
            code = getattr(e, 'code', getattr(e, 'exit_code', 1))
        assert code == 1

    def test_subprocess_failure_exits_nonzero(self, tmp_path):
        code = _call_run(tmp_path, proc_rc=2)
        assert code == 2

    def test_interactive_mode_no_py_files_exits_1(self, tmp_path):
        from epi_cli.run import run
        import os
        code = None
        original = os.getcwd()
        try:
            os.chdir(tmp_path)  # empty dir
            try:
                with patch("epi_cli.run.console", MagicMock()):
                    run(script=None, no_verify=False, no_open=False,
                        goal=None, notes=None, metric=None, approved_by=None, tag=None)
            except (SystemExit, click.exceptions.Exit) as e:
                code = getattr(e, 'code', getattr(e, 'exit_code', 1))
        finally:
            os.chdir(original)
        assert code == 1

    def test_verify_fails_exits_1(self, tmp_path):
        code = _call_run(tmp_path, verify_result=(False, "Integrity fail"))
        assert code == 1

    def test_workspace_failure_exits_1(self, tmp_path):
        from epi_cli.run import run

        script = tmp_path / "test_script.py"
        script.write_text("print('hello')", encoding="utf-8")
        mock_console = MagicMock()

        code = None
        try:
            with patch("epi_cli.run.console", mock_console), \
                 patch("epi_cli.run.create_recording_workspace", side_effect=RecordingWorkspaceError("workspace blocked")):
                run(
                    script=script,
                    no_verify=False,
                    no_open=False,
                    goal=None,
                    notes=None,
                    metric=None,
                    approved_by=None,
                    tag=None,
                )
        except (SystemExit, click.exceptions.Exit) as e:
            code = getattr(e, "code", getattr(e, "exit_code", None))

        assert code == 1
        printed = "\n".join(str(call.args[0]) for call in mock_console.print.call_args_list if call.args)
        assert "could not start recording" in printed.lower()

    def test_run_writes_environment_json(self, tmp_path):
        from epi_cli.run import run

        script = tmp_path / "test_script.py"
        script.write_text("print('hello')", encoding="utf-8")
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0

        code = None
        try:
            with patch("epi_cli.run.console", MagicMock()), \
                 patch("subprocess.Popen", return_value=mock_proc), \
                 patch("epi_cli.run.create_recording_workspace", return_value=workspace), \
                 patch("epi_cli.run.build_env_for_child", return_value={}), \
                 patch("epi_cli.run.EPIContainer.pack",
                       side_effect=lambda ws, m, out, **kw: _create_fake_epi(out, ws, step_count=1)), \
                 patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
                 patch("epi_cli.run._verify_recording", return_value=(True, "OK")), \
                 patch("epi_cli.run._open_viewer", return_value=False):
                run(
                    script=script,
                    no_verify=False,
                    no_open=False,
                    goal=None,
                    notes=None,
                    metric=None,
                    approved_by=None,
                    tag=None,
                )
        except (SystemExit, click.exceptions.Exit) as e:
            code = getattr(e, "code", getattr(e, "exit_code", None))

        assert code == 0
        assert (workspace / "environment.json").exists()
        assert not (workspace / "env.json").exists()

    def test_open_viewer_injects_verification_context(self, tmp_path):
        from epi_cli.run import _open_viewer

        epi = _make_epi(tmp_path, signed=True)
        captured_html = {}

        def _capture_open(uri):
            from urllib.parse import urlparse, unquote
            parsed = urlparse(uri)
            opened_path = Path(unquote(parsed.path.lstrip("/")))
            if not opened_path.exists():
                opened_path = Path(unquote(parsed.path))
            captured_html["html"] = opened_path.read_text(encoding="utf-8")
            return True

        with patch("webbrowser.open", side_effect=_capture_open), \
             patch("threading.Thread.start", return_value=None):
            assert _open_viewer(epi) is True
        assert "Evidence Packaged Infrastructure" in captured_html["html"]
        assert 'id="epi-data"' in captured_html["html"]
        assert 'id="epi-view-context"' in captured_html["html"]

    def test_open_viewer_refreshes_html_from_append_only_review_data(self, tmp_path):
        from epi_cli.run import _open_viewer

        epi = _make_epi(tmp_path, signed=False)
        review_payload = {
            "review_version": "1.0.0",
            "reviewed_by": "reviewer@epilabs.org",
            "reviewed_at": utc_now_iso(),
            "reviews": [
                {
                    "fault_step": 1,
                    "rule_id": "R001",
                    "fault_type": "POLICY_VIOLATION",
                    "outcome": "confirmed_fault",
                    "notes": "Confirmed in review.",
                    "reviewer": "reviewer@epilabs.org",
                    "timestamp": utc_now_iso(),
                }
            ],
            "review_signature": None,
        }

        with zipfile.ZipFile(epi, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("review.json", json.dumps(review_payload))

        captured_html = {}

        def _capture_open(uri):
            from urllib.parse import urlparse, unquote
            parsed = urlparse(uri)
            opened_path = Path(unquote(parsed.path.lstrip("/")))
            if not opened_path.exists():
                opened_path = Path(unquote(parsed.path))
            captured_html["html"] = opened_path.read_text(encoding="utf-8")
            return True

        with patch("webbrowser.open", side_effect=_capture_open), \
             patch("threading.Thread.start", return_value=None):
            assert _open_viewer(epi) is True

        assert 'id="epi-data"' in captured_html["html"]
        assert "reviewer@epilabs.org" in captured_html["html"]
        assert "Confirmed in review." in captured_html["html"]

    def test_run_supports_manual_get_current_session_log_step(self, tmp_path):
        from epi_cli.run import run

        script = tmp_path / "manual_log.py"
        script.write_text(
            "from epi_recorder import get_current_session\n"
            "session = get_current_session()\n"
            "if session:\n"
            "    session.log_step('manual.event', {'ok': True})\n"
            "print('done')\n",
            encoding="utf-8",
        )
        recordings_dir = tmp_path / "epi-recordings"
        recordings_dir.mkdir()

        code = None
        try:
            with patch("epi_cli.run.DEFAULT_DIR", recordings_dir), \
                 patch("epi_cli.run.console", MagicMock()), \
                 patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
                run(
                    script=script,
                    no_verify=True,
                    no_open=True,
                    goal=None,
                    notes=None,
                    metric=None,
                    approved_by=None,
                    tag=None,
                )
        except (SystemExit, click.exceptions.Exit) as e:
            code = getattr(e, "code", getattr(e, "exit_code", None))

        assert code == 0
        artifacts = sorted(recordings_dir.glob("manual_log_*.epi"))
        assert artifacts
        with zipfile.ZipFile(artifacts[-1], "r") as zf:
            steps = zf.read("steps.jsonl").decode("utf-8")
        assert "manual.event" in steps

    def test_run_supports_manual_agent_run_helper_via_get_current_session(self, tmp_path):
        from epi_cli.run import run

        script = tmp_path / "manual_agent.py"
        script.write_text(
            "from epi_recorder import get_current_session\n"
            "session = get_current_session()\n"
            "if session:\n"
            "    with session.agent_run('refund-agent', user_input='Refund order 123', session_id='run-session-1', task_id='refund-task-1', attempt=2, resume_from='earlier-run') as agent:\n"
            "        agent.plan('Check order, request approval, then decide')\n"
            "        agent.message('user', 'Refund order 123')\n"
            "        agent.memory_read('order_history', query='123', result_count=1)\n"
            "        agent.tool_call('lookup_order', {'order_id': '123'})\n"
            "        agent.tool_result('lookup_order', {'status': 'paid'})\n"
            "        agent.approval_request('approve_refund', reason='Needs manager signoff', risk_level='high')\n"
            "        agent.approval_response('approve_refund', approved=True, reviewer='manager@example.com')\n"
            "        agent.decision('approve_refund', confidence=0.91)\n"
            "        agent.memory_write('refund_decision', {'approved': True})\n"
            "print('done')\n",
            encoding="utf-8",
        )
        recordings_dir = tmp_path / "epi-recordings"
        recordings_dir.mkdir()

        code = None
        try:
            with patch("epi_cli.run.DEFAULT_DIR", recordings_dir), \
                 patch("epi_cli.run.console", MagicMock()), \
                 patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
                run(
                    script=script,
                    no_verify=True,
                    no_open=True,
                    goal=None,
                    notes=None,
                    metric=None,
                    approved_by=None,
                    tag=None,
                )
        except (SystemExit, click.exceptions.Exit) as e:
            code = getattr(e, "code", getattr(e, "exit_code", None))

        assert code == 0
        artifacts = sorted(recordings_dir.glob("manual_agent_*.epi"))
        assert artifacts
        with zipfile.ZipFile(artifacts[-1], "r") as zf:
            steps = [
                json.loads(line)
                for line in zf.read("steps.jsonl").decode("utf-8").splitlines()
                if line.strip()
            ]
        kinds = [step["kind"] for step in steps]
        assert "agent.run.start" in kinds
        assert "agent.plan" in kinds
        assert "agent.message" in kinds
        assert "agent.memory.read" in kinds
        assert "tool.call" in kinds
        assert "tool.response" in kinds
        assert "agent.approval.request" in kinds
        assert "agent.approval.response" in kinds
        assert "agent.decision" in kinds
        assert "agent.memory.write" in kinds
        assert "agent.run.end" in kinds

        start = next(step for step in steps if step["kind"] == "agent.run.start")
        assert start["content"]["session_id"] == "run-session-1"
        assert start["content"]["task_id"] == "refund-task-1"
        assert start["content"]["attempt"] == 2
        assert start["content"]["resume_from"] == "earlier-run"

    def test_run_captures_plain_print_output_as_stdout_steps(self, tmp_path):
        from epi_cli.run import run

        script = tmp_path / "plain_print.py"
        script.write_text(
            "print('hello from plain script')\n"
            "print('{\"status\": \"ok\"}')\n",
            encoding="utf-8",
        )
        recordings_dir = tmp_path / "epi-recordings"
        recordings_dir.mkdir()

        code = None
        try:
            with patch("epi_cli.run.DEFAULT_DIR", recordings_dir), \
                 patch("epi_cli.run.console", MagicMock()), \
                 patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
                run(
                    script=script,
                    no_verify=True,
                    no_open=True,
                    goal=None,
                    notes=None,
                    metric=None,
                    approved_by=None,
                    tag=None,
                )
        except (SystemExit, click.exceptions.Exit) as e:
            code = getattr(e, "code", getattr(e, "exit_code", None))

        assert code == 0
        artifacts = sorted(recordings_dir.glob("plain_print_*.epi"))
        assert artifacts
        with zipfile.ZipFile(artifacts[-1], "r") as zf:
            steps = zf.read("steps.jsonl").decode("utf-8")
        assert "stdout.print" in steps
        assert "hello from plain script" in steps

    def test_run_prefers_script_created_artifact_over_empty_bootstrap_capture(self, tmp_path):
        from epi_cli.run import run

        script = tmp_path / "structured_script.py"
        script.write_text("print('hello')", encoding="utf-8")
        recordings_dir = tmp_path / "epi-recordings"
        recordings_dir.mkdir()
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        child_artifact = recordings_dir / "structured_demo.epi"

        mock_proc = MagicMock()

        def _wait_and_create_child_artifact():
            child_workspace = tmp_path / "child_workspace"
            child_workspace.mkdir(exist_ok=True)
            _create_fake_epi(child_artifact, child_workspace, step_count=3)
            return 0

        mock_proc.wait.side_effect = _wait_and_create_child_artifact
        verify_mock = MagicMock(return_value=(True, "OK"))

        code = None
        try:
            with patch("epi_cli.run.DEFAULT_DIR", recordings_dir), \
                 patch("epi_cli.run.console", MagicMock()), \
                 patch("subprocess.Popen", return_value=mock_proc), \
                 patch("epi_cli.run.create_recording_workspace", return_value=workspace), \
                 patch("epi_cli.run.save_environment_snapshot"), \
                 patch("epi_cli.run.build_env_for_child", return_value={}), \
                 patch("epi_cli.run.EPIContainer.pack",
                       side_effect=lambda ws, m, out, **kw: _create_fake_epi(out, ws, step_count=0)), \
                 patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
                 patch("epi_cli.run._verify_recording", verify_mock), \
                 patch("epi_cli.run._open_viewer", return_value=False):
                run(
                    script=script,
                    no_verify=False,
                    no_open=True,
                    goal=None,
                    notes=None,
                    metric=None,
                    approved_by=None,
                    tag=None,
                )
        except (SystemExit, click.exceptions.Exit) as e:
            code = getattr(e, "code", getattr(e, "exit_code", None))

        assert code == 0
        assert child_artifact.exists()
        generated = list(recordings_dir.glob("structured_script_*.epi"))
        assert generated == []
        verify_mock.assert_called_once_with(child_artifact)
