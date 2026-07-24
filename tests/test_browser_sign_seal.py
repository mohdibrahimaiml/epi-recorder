"""
Regression tests for browser Sign & Seal (Item 1).

Historical bug: web_viewer/app.js buildReviewedArtifactBytes()
produced a bare unsigned ZIP (legacy-zip), deleting manifest.signature and never
wrapping envelope-v2. That fails enterprise evidence use.

These tests:
1. Assert source still implements envelope wrap + re-sign (static guard).
2. Build a sealed .epi via the same JS helpers the browser uses
   (scripts/browser_sign_seal_pack.mjs) and verify with the real Python CLI.
3. Prove the old bare-ZIP shape is legacy + unsigned (documents the bug).
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from epi_core.container import (
    EPI_CONTAINER_FORMAT_ENVELOPE,
    EPI_CONTAINER_FORMAT_LEGACY,
    EPI_ENVELOPE_HEADER_SIZE,
    EPI_ENVELOPE_MAGIC,
    EPI_ENVELOPE_VERSION,
    EPI_LEGACY_MIMETYPE,
    EPI_PAYLOAD_FORMAT_ZIP_V1,
    EPIContainer,
    _EPI_ENVELOPE_HEADER_STRUCT,
)
from epi_core.trust import verify_embedded_manifest_signature

ROOT = Path(__file__).resolve().parents[1]
PACK_SCRIPT = ROOT / "scripts" / "browser_sign_seal_pack.mjs"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_web_viewer_sign_seal_writes_human_status_not_only_dismissed_jargon():
    """normalizeReview must humanize ledger outcomes; Model A uses v1.1 builder."""
    js = _read("web_viewer/app.js")
    assert "function humanizeReviewOutcome" in js
    assert "humanizeReviewOutcome" in js
    assert "epiBuildSignedReviewRecord" in js
    crypto = _read("epi_viewer_static/crypto.js")
    assert "approved: 'dismissed'" in crypto or 'approved: "dismissed"' in crypto
    assert "case_level_review: true" in crypto or "case_level_review: true" in js


def test_web_viewer_sign_seal_is_model_a_additive():
    """Static guard: Model A — bound review, no full re-sign of manifest."""
    js = _read("web_viewer/app.js")
    assert "async function buildReviewedArtifactBytes" in js
    fn_body = js.split("async function buildReviewedArtifactBytes")[1].split(
        "async function downloadReviewedArtifact"
    )[0]
    assert "epiBuildSignedReviewRecord" in fn_body
    assert "epiBuildArtifactBinding" in fn_body
    assert "archive_base64" in fn_body or "archiveB64" in fn_body
    # Must not re-sign the execution manifest in this path
    assert "epiSignManifest" not in fn_body
    assert "A-additive" in fn_body or "model: 'A-additive'" in fn_body
    assert "epiWrapEnvelopeV2" in fn_body


def test_crypto_js_exports_sign_and_envelope_helpers():
    crypto = _read("epi_viewer_static/crypto.js")
    assert "signAsync" in crypto
    assert "function epiWrapEnvelopeV2" in crypto
    assert "function epiSignManifest" in crypto
    assert "function epiPackEnvelopeHeader" in crypto
    assert "function epiBuildArtifactBinding" in crypto
    assert "function epiBuildSignedReviewRecord" in crypto
    assert "function epiExtractInnerZipFromEpi" in crypto

def test_old_bare_zip_sign_seal_shape_is_legacy_and_unsigned(tmp_path: Path):
    """
    Documents the historical bug: bare ZIP with mimetype, no envelope, no signature.
    This is what old buildReviewedArtifactBytes produced.
    """
    bare = tmp_path / "old_style_reviewed.epi"
    with zipfile.ZipFile(bare, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", EPI_LEGACY_MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "spec_version": "4.0.1",
                    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
                    "created_at": "2026-01-15T12:00:00Z",
                    "file_manifest": {},
                    # signature intentionally absent (old code: delete manifest.signature)
                }
            ),
        )
        zf.writestr("steps.jsonl", "{}\n")

    assert EPIContainer.detect_container_format(bare) == EPI_CONTAINER_FORMAT_LEGACY
    assert bare.read_bytes()[:4] != EPI_ENVELOPE_MAGIC
    manifest = EPIContainer.read_manifest(bare)
    sig_valid, _signer, msg = verify_embedded_manifest_signature(manifest)
    assert sig_valid is None
    assert "No signature" in msg


@pytest.mark.skipif(shutil.which("node") is None, reason="node required for JS packer")
def test_js_sign_seal_produces_envelope_v2_signed_and_verifies(tmp_path: Path):
    """
    Build via browser helpers (Node) and verify with Python core + CLI.
    This is the functional regression that would have caught the bare-zip bug.
    """
    out = tmp_path / "js_sealed.epi"
    seed = "11" * 32  # fixed 32-byte seed for determinism
    proc = subprocess.run(
        [shutil.which("node"), str(PACK_SCRIPT), "--out", str(out), "--seed-hex", seed],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"packer failed:\n{proc.stdout}\n{proc.stderr}"
    meta = json.loads(proc.stdout)
    assert out.exists()
    assert meta["magic"] == "<!--"
    assert meta["has_signature"] is True

    # Container format
    assert EPIContainer.detect_container_format(out) == EPI_CONTAINER_FORMAT_ENVELOPE
    header = EPIContainer._read_envelope_header(out)
    assert header.magic == EPI_ENVELOPE_MAGIC
    assert header.version == EPI_ENVELOPE_VERSION
    assert header.payload_format == EPI_PAYLOAD_FORMAT_ZIP_V1
    assert header.reserved_flags == 0
    assert header.payload_length > 0
    assert len(header.payload_sha256) == 32

    # Header struct layout: first 128 bytes unpack cleanly
    raw_header = out.read_bytes()[:EPI_ENVELOPE_HEADER_SIZE]
    assert len(raw_header) == 128
    unpacked = _EPI_ENVELOPE_HEADER_STRUCT.unpack(raw_header)
    assert unpacked[0] == EPI_ENVELOPE_MAGIC
    assert unpacked[1] == EPI_ENVELOPE_VERSION

    # Signature verifies against embedded public key
    manifest = EPIContainer.read_manifest(out)
    assert manifest.signature
    assert manifest.public_key
    assert manifest.container_format == "envelope-v2"
    sig_valid, signer, msg = verify_embedded_manifest_signature(manifest)
    assert sig_valid is True, msg
    assert signer

    # Integrity of payload hash
    integrity_ok, mismatches = EPIContainer.verify_integrity(out)
    assert integrity_ok, mismatches

    # Real CLI verify — must report valid signature / verified integrity
    cli = subprocess.run(
        [sys.executable, "-m", "epi_cli.main", "verify", str(out), "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert cli.returncode == 0, cli.stdout + cli.stderr
    # JSON may be multi-line; find the report object
    report = json.loads(cli.stdout)
    assert report.get("integrity_ok") is True
    assert report.get("signature_valid") is True


@pytest.mark.skipif(shutil.which("node") is None, reason="node required for JS packer")
def test_js_envelope_header_matches_python_packer_for_same_zip_payload(tmp_path: Path):
    """
    Byte-for-byte header match when the ZIP payload bytes are identical:
    JS epiWrapEnvelopeV2 vs Python _write_envelope_from_payload.
    """
    # Build a fixed ZIP payload
    zip_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("mimetype", EPI_LEGACY_MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("steps.jsonl", '{"index":0}\n')
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "spec_version": "4.0.1",
                    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
                    "created_at": "2026-01-15T12:00:00Z",
                    "file_manifest": {},
                }
            ),
        )

    zip_bytes = zip_path.read_bytes()
    from epi_core.schemas import ManifestModel

    manifest = ManifestModel(
        spec_version="4.0.1",
        workflow_id="550e8400-e29b-41d4-a716-446655440000",
        created_at="2026-01-15T12:00:00Z",
        file_manifest={},
    )

    py_out = tmp_path / "python_wrapped.epi"
    EPIContainer._write_envelope_from_payload(zip_path, py_out, manifest=manifest, viewer_html=None)
    py_header = py_out.read_bytes()[:EPI_ENVELOPE_HEADER_SIZE]

    # JS wrap of the same ZIP
    js_zip = tmp_path / "same.zip"
    js_zip.write_bytes(zip_bytes)
    # Use a tiny inline node one-liner via packer path: write helper script
    wrap_script = tmp_path / "wrap_once.mjs"
    wrap_script.write_text(
        f"""
import {{ readFileSync, writeFileSync }} from 'node:fs';
import {{ webcrypto, createHash, randomBytes }} from 'node:crypto';
// Prefer Node's webcrypto; only polyfill if missing.
if (!globalThis.crypto) {{
  globalThis.crypto = webcrypto;
}}
if (!globalThis.crypto.subtle) {{
  Object.defineProperty(globalThis.crypto, 'subtle', {{
    value: {{
      digest: async (algo, data) => {{
        const name = String(algo).toUpperCase().includes('512') ? 'sha512' : 'sha256';
        return createHash(name).update(Buffer.from(data instanceof ArrayBuffer ? new Uint8Array(data) : data)).digest().buffer;
      }},
    }},
  }});
}}
if (!globalThis.crypto.getRandomValues) {{
  globalThis.crypto.getRandomValues = (a) => {{ a.set(randomBytes(a.length)); return a; }};
}}
const cryptoJs = readFileSync({json.dumps(str(ROOT / "epi_viewer_static/crypto.js"))}, 'utf8');
(0, eval)(cryptoJs);
const zip = new Uint8Array(readFileSync({json.dumps(str(js_zip))}));
const manifest = {{
  workflow_id: '550e8400-e29b-41d4-a716-446655440000',
  created_at: '2026-01-15T12:00:00Z',
}};
const env = await epiWrapEnvelopeV2(zip, manifest, null);
writeFileSync({json.dumps(str(tmp_path / "js_wrapped.epi"))}, Buffer.from(env));
console.log('ok');
""",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [shutil.which("node"), str(wrap_script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    js_header = (tmp_path / "js_wrapped.epi").read_bytes()[:EPI_ENVELOPE_HEADER_SIZE]
    assert js_header == py_header, (
        f"Header mismatch\nJS: {js_header.hex()}\nPY: {py_header.hex()}"
    )
