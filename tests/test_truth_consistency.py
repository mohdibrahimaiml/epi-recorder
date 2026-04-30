from __future__ import annotations

import json
import zipfile
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from epi_cli.main import app
from epi_cli.view import _build_viewer_context
from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now
from epi_core.trust import sign_manifest


runner = CliRunner()


def _make_epi(tmp_path: Path, *, signed: bool) -> Path:
    steps = b'{"index":0,"kind":"test","content":{"value":1}}\n'
    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=utc_now(),
        file_manifest={
            "steps.jsonl": __import__("hashlib").sha256(steps).hexdigest(),
        },
    )
    if signed:
        key = Ed25519PrivateKey.generate()
        manifest = sign_manifest(manifest, key, "default")

    artifact = tmp_path / ("signed.epi" if signed else "unsigned.epi")
    with zipfile.ZipFile(artifact, "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip")
        zf.writestr("manifest.json", manifest.model_dump_json())
        zf.writestr("steps.jsonl", steps)
        zf.writestr("viewer.html", "<html><head></head><body>viewer</body></html>")
    return artifact


def _tamper_steps(epi_path: Path) -> Path:
    tampered = epi_path.with_name("tampered.epi")
    with zipfile.ZipFile(epi_path, "r") as zf:
        files = {name: zf.read(name) for name in zf.namelist()}
    files["steps.jsonl"] = b'{"index":0,"kind":"test","content":{"value":999}}\n'
    with zipfile.ZipFile(tampered, "w") as zf:
        if "mimetype" in files:
            zf.writestr("mimetype", files.pop("mimetype"))
        for name, content in files.items():
            zf.writestr(name, content)
    return tampered


def _verify_json(epi_path: Path) -> dict:
    result = runner.invoke(app, ["verify", "--json", str(epi_path)])
    assert result.exit_code in (0, 1), result.stdout
    return json.loads(result.stdout)


def _assert_trust_consistent(epi_path: Path) -> None:
    verify_report = _verify_json(epi_path)
    view_report = _build_viewer_context(epi_path)

    keys = [
        "integrity_ok",
        "signature_valid",
        "trust_level",
    ]
    for key in keys:
        assert verify_report[key] == view_report[key], f"{key} mismatch"


def test_verify_and_viewer_reports_match_for_unsigned(tmp_path: Path):
    _assert_trust_consistent(_make_epi(tmp_path, signed=False))


def test_verify_and_viewer_reports_match_for_signed(tmp_path: Path):
    _assert_trust_consistent(_make_epi(tmp_path, signed=True))


def test_verify_and_viewer_reports_match_for_tampered(tmp_path: Path):
    signed = _make_epi(tmp_path, signed=True)
    _assert_trust_consistent(_tamper_steps(signed))


def test_manifest_signature_description_mentions_canonical_json() -> None:
    field = ManifestModel.model_fields["signature"]
    description = field.description or ""
    assert "canonical JSON hash" in description
    assert "spec v2+" in description
