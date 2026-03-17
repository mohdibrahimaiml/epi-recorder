"""
Extended tests for epi_cli.run — _verify_recording edge cases and run() function.
"""

import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY
from uuid import uuid4

import pytest
import click

from epi_core.schemas import ManifestModel


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_epi(tmp_path: Path, signed: bool = False, include_public_key: bool = True) -> Path:
    steps = b'{"index":0,"kind":"test","content":{}}\n'
    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=datetime.utcnow(),
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
            "created_at": datetime.utcnow().isoformat(),
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
        created_at=datetime.utcnow(),
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
