"""
Tests for epi_cli.record — record() function.
"""

import hashlib
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from uuid import uuid4

import click

from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _create_fake_epi(out_path: Path, workspace: Path):
    steps = b'{"index":0}\n'
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


def _call_record(tmp_path, command=None, out_name="out.epi",
                 no_sign=False, no_redact=False, include_all_env=False,
                 name=None, tag=None, proc_rc=0):
    """Call record() directly with mocked subprocess."""
    from epi_cli.record import record

    out = tmp_path / out_name
    cmd = command or ["python", "-c", "print('hello')"]

    mock_proc = MagicMock()
    mock_proc.wait.return_value = proc_rc

    code = None
    try:
        with patch("epi_cli.record.console", MagicMock()), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("epi_cli.record.save_environment_snapshot"), \
             patch("epi_cli.record.build_env_for_child", return_value={}), \
             patch("epi_cli.record.EPIContainer.pack",
                   side_effect=lambda ws, m, o, **kw: _create_fake_epi(o, ws)), \
             patch("epi_cli.record.KeyManager") as mock_km_cls:
            # Make KeyManager raise so no-sign path is tested (since keys may not exist)
            mock_km_cls.return_value.load_private_key.side_effect = Exception("no key")
            record(
                ctx=MagicMock(),
                out=out,
                name=name,
                tag=tag,
                no_sign=no_sign,
                no_redact=no_redact,
                include_all_env=include_all_env,
                command=cmd,
            )
    except (SystemExit, click.exceptions.Exit) as e:
        code = getattr(e, 'code', getattr(e, 'exit_code', None))

    return code


class TestRecordFunction:
    def test_basic_recording_exits_0(self, tmp_path):
        code = _call_record(tmp_path)
        assert code == 0

    def test_no_sign_flag(self, tmp_path):
        code = _call_record(tmp_path, no_sign=True)
        assert code == 0

    def test_no_redact_flag(self, tmp_path):
        code = _call_record(tmp_path, no_redact=True)
        assert code == 0

    def test_include_all_env(self, tmp_path):
        code = _call_record(tmp_path, include_all_env=True)
        assert code == 0

    def test_subprocess_failure_exits_with_rc(self, tmp_path):
        code = _call_record(tmp_path, proc_rc=1)
        assert code == 1

    def test_empty_command_exits_1(self, tmp_path):
        from epi_cli.record import record
        code = None
        try:
            with patch("epi_cli.record.console", MagicMock()):
                record(
                    ctx=MagicMock(),
                    out=tmp_path / "out.epi",
                    name=None, tag=None,
                    no_sign=False, no_redact=False,
                    include_all_env=False,
                    command=[],
                )
        except (SystemExit, click.exceptions.Exit) as e:
            code = getattr(e, 'code', getattr(e, 'exit_code', None))
        assert code == 1

    def test_output_adds_epi_extension(self, tmp_path):
        """out without .epi extension should still produce .epi file."""
        from epi_cli.record import record
        out_no_ext = tmp_path / "myoutput"  # no .epi
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        code = None
        try:
            with patch("epi_cli.record.console", MagicMock()), \
                 patch("subprocess.Popen", return_value=mock_proc), \
                 patch("epi_cli.record.save_environment_snapshot"), \
                 patch("epi_cli.record.build_env_for_child", return_value={}), \
                 patch("epi_cli.record.EPIContainer.pack",
                       side_effect=lambda ws, m, o, **kw: _create_fake_epi(o, ws)), \
                 patch("epi_cli.record.KeyManager") as mock_km:
                mock_km.return_value.load_private_key.side_effect = Exception("no key")
                record(
                    ctx=MagicMock(),
                    out=out_no_ext,
                    name=None, tag=None,
                    no_sign=True, no_redact=False,
                    include_all_env=False,
                    command=["python", "-c", "pass"],
                )
        except (SystemExit, click.exceptions.Exit) as e:
            code = getattr(e, 'code', getattr(e, 'exit_code', None))
        assert code == 0
        assert (tmp_path / "myoutput.epi").exists()

    def test_with_signing_succeeds(self, tmp_path):
        """Test record when signing actually works."""
        from epi_cli.record import record
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.generate()

        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        code = None
        try:
            with patch("epi_cli.record.console", MagicMock()), \
                 patch("subprocess.Popen", return_value=mock_proc), \
                 patch("epi_cli.record.save_environment_snapshot"), \
                 patch("epi_cli.record.build_env_for_child", return_value={}), \
                 patch("epi_cli.record.EPIContainer.pack",
                       side_effect=lambda ws, m, o, **kw: _create_fake_epi(o, ws)), \
                 patch("epi_cli.record.KeyManager") as mock_km:
                mock_km.return_value.load_private_key.return_value = key
                record(
                    ctx=MagicMock(),
                    out=tmp_path / "signed.epi",
                    name=None, tag=None,
                    no_sign=False, no_redact=False,
                    include_all_env=False,
                    command=["python", "-c", "pass"],
                )
        except (SystemExit, click.exceptions.Exit) as e:
            code = getattr(e, 'code', getattr(e, 'exit_code', None))
        assert code == 0
