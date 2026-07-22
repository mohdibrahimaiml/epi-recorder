"""
Model A review binding: JS helpers must match epi_core/review.py byte-for-byte.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from epi_core.container import EPIContainer
from epi_core.review import (
    REVIEW_VERSION,
    ReviewRecord,
    add_review_to_artifact,
    build_artifact_binding,
    make_review_entry,
    verify_review_trust,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "agicomply_demo.epi"
CHECK_SCRIPT = ROOT / "scripts" / "browser_review_binding_check.mjs"
PACK_SCRIPT = ROOT / "scripts" / "browser_additive_review_pack.mjs"


def _write_binding_fixture(epi_path: Path, out_json: Path) -> dict:
    binding = build_artifact_binding(epi_path)
    manifest = EPIContainer.read_manifest(epi_path)
    members: dict[str, str] = {}
    with EPIContainer._payload_zip_path(epi_path) as zip_path:
        import zipfile

        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in sorted(manifest.file_manifest.keys()):
                try:
                    members[name] = base64.b64encode(zf.read(name)).decode("ascii")
                except KeyError:
                    pass
            # always include raw manifest.json bytes
            members["manifest.json"] = base64.b64encode(zf.read("manifest.json")).decode("ascii")

    fixture = {
        "binding": binding,
        "members": members,
        "manifest_path": "manifest.json",
        "workflow_id": str(manifest.workflow_id),
        "manifest_signature": manifest.signature,
        "manifest_public_key": manifest.public_key,
        "container_format": EPIContainer.detect_container_format(epi_path),
        "file_manifest_paths": sorted(manifest.file_manifest.keys()),
    }
    out_json.write_text(json.dumps(fixture), encoding="utf-8")
    return fixture


@pytest.mark.skipif(shutil.which("node") is None, reason="node required")
@pytest.mark.skipif(not DEMO.exists(), reason="agicomply_demo.epi missing")
def test_js_artifact_binding_matches_python(tmp_path: Path):
    fixture_path = tmp_path / "binding_fixture.json"
    _write_binding_fixture(DEMO, fixture_path)
    proc = subprocess.run(
        [shutil.which("node"), str(CHECK_SCRIPT), "--fixture", str(fixture_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["ok"] is True
    assert result["binding"] == result["expected"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node required")
@pytest.mark.skipif(not DEMO.exists(), reason="agicomply_demo.epi missing")
def test_js_additive_review_preserves_manifest_sig_and_binds(tmp_path: Path):
    """
    Node packer builds Model A reviewed .epi:
    - original manifest signature still verifies
    - verify_review_trust binding_valid True
    """
    if not PACK_SCRIPT.exists():
        pytest.skip("browser_additive_review_pack.mjs not yet present")

    out = tmp_path / "reviewed_model_a.epi"
    seed = "22" * 32
    proc = subprocess.run(
        [
            shutil.which("node"),
            str(PACK_SCRIPT),
            "--in",
            str(DEMO),
            "--out",
            str(out),
            "--seed-hex",
            seed,
            "--reviewer",
            "afridi",
            "--status",
            "approved",
            "--notes",
            "Enterprise model A test",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out.exists()

    from epi_core.trust import verify_embedded_manifest_signature

    manifest = EPIContainer.read_manifest(out)
    sig_ok, _signer, msg = verify_embedded_manifest_signature(manifest)
    assert sig_ok is True, msg

    # Original demo signature must be unchanged (byte-identical signature string)
    orig = EPIContainer.read_manifest(DEMO)
    assert manifest.signature == orig.signature
    assert manifest.public_key == orig.public_key

    report = verify_review_trust(out, strict=False)
    assert report["binding_valid"] is True, report
    assert report["signature_valid"] is True, report
    assert report["status"] in ("verified", "warnings"), report
    assert not any("does not match this artifact binding" in f for f in report.get("failures") or [])

    integrity_ok, mismatches = EPIContainer.verify_integrity(out)
    assert integrity_ok, mismatches


def test_cli_additive_review_still_works(tmp_path: Path):
    """Sanity: Python gold path unchanged."""
    if not DEMO.exists():
        pytest.skip("agicomply_demo.epi missing")
    target = tmp_path / "cli_reviewed.epi"
    shutil.copyfile(DEMO, target)
    key = Ed25519PrivateKey.generate()
    record = ReviewRecord(
        reviewed_by="cli@example.com",
        reviews=[
            make_review_entry(
                fault={},
                outcome="dismissed",
                notes="cli path",
                reviewer="cli@example.com",
            )
        ],
        case_level_review=True,
    )
    add_review_to_artifact(target, record, private_key=key)
    report = verify_review_trust(target)
    assert report["binding_valid"] is True
    assert report["signature_valid"] is True
    from epi_core.trust import verify_embedded_manifest_signature

    m = EPIContainer.read_manifest(target)
    ok, _, msg = verify_embedded_manifest_signature(m)
    assert ok is True, msg
