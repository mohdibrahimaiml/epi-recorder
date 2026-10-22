"""Adversarial: the double-click display layer must be bound to the signature.

The outer polyglot region of an envelope-v2 ``.epi`` is byte-identical to the
ZIP member ``viewer.html``, whose SHA-256 sits in ``manifest.file_manifest`` —
i.e. inside the Ed25519-signed manifest.

The envelope header's ``reserved_tail[0:32]`` holds a *copy* of that hash, but
the header is unsigned and the copy is self-referential: an attacker who edits
the display layer can recompute it, and the file then looks self-consistent to
any verifier that only reads the header. The signed ``file_manifest`` entry is
the check that cannot be forged without breaking the signature.

These tests pin that behaviour:

* a legitimate artifact still verifies,
* a naive display-layer edit is detected (control),
* a *consistent* forgery — edit plus recomputed header copy — is detected.
  This is the case the header copy alone cannot catch.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app
from epi_core.container import (
    EPI_CONTAINER_FORMAT_ENVELOPE,
    EPI_ENVELOPE_HEADER_SIZE,
    EPI_VIEWER_HASH_SIZE,
    EPI_ZIP_MARKER,
    EPIContainer,
    _EPI_ENVELOPE_HEADER_STRUCT,
)
from tests.helpers.artifacts import make_decision_epi

runner = CliRunner()

_POLYGLOT_PREFIX = b" -->\n"  # closes the header comment before the viewer HTML


def _forge_display_layer(
    epi_path: Path,
    out_path: Path,
    *,
    recompute_header_hash: bool,
) -> Path:
    """Edit the outer double-click display layer the way an attacker would.

    The ZIP payload is left untouched, so ``payload_sha256`` still matches and
    the manifest signature is unaffected. Only the HTML region a human sees on
    double-click is rewritten.

    When ``recompute_header_hash`` is set, the envelope's unsigned
    ``reserved_tail[0:32]`` copy is recomputed too, which makes the file
    self-consistent from the verifier's point of view. That is the forgery the
    signed ``file_manifest`` entry has to catch.
    """
    data = bytearray(epi_path.read_bytes())
    header = _EPI_ENVELOPE_HEADER_STRUCT.unpack(bytes(data[:EPI_ENVELOPE_HEADER_SIZE]))
    marker_idx = data.find(EPI_ZIP_MARKER)
    assert marker_idx > EPI_ENVELOPE_HEADER_SIZE, "expected an envelope-v2 polyglot region"

    region = bytes(data[EPI_ENVELOPE_HEADER_SIZE:marker_idx])
    html = region[len(_POLYGLOT_PREFIX):] if region.startswith(_POLYGLOT_PREFIX) else region

    forged_html = html + b"<!-- forged display layer: paint whatever verdict you like -->"
    forged_hash = hashlib.sha256(forged_html).digest()

    tail = bytearray(header[8])  # reserved_tail, 56 bytes
    if recompute_header_hash:
        tail[:EPI_VIEWER_HASH_SIZE] = forged_hash

    new_data = (
        bytearray(data[:EPI_ENVELOPE_HEADER_SIZE])
        + bytearray(_POLYGLOT_PREFIX + forged_html)
        + bytearray(data[marker_idx:])
    )
    new_data[:EPI_ENVELOPE_HEADER_SIZE] = _EPI_ENVELOPE_HEADER_STRUCT.pack(
        header[0],  # magic
        header[1],  # version
        header[2],  # payload_format
        header[3],  # reserved_flags
        header[4],  # payload_length
        header[5],  # artifact_uuid
        header[6],  # created_at_micros
        header[7],  # payload_sha256 — ZIP payload untouched, so still valid
        bytes(tail),
    )
    out_path.write_bytes(bytes(new_data))
    return out_path


@pytest.fixture
def envelope_artifact(tmp_path: Path) -> Path:
    epi, _key = make_decision_epi(
        tmp_path, container_format=EPI_CONTAINER_FORMAT_ENVELOPE
    )
    return epi


def test_outer_display_layer_matches_signed_viewer_member(envelope_artifact: Path):
    """Precondition: the outer region is the signed ZIP member, byte for byte."""
    manifest = EPIContainer.read_manifest(envelope_artifact)
    signed_hex = manifest.file_manifest.get("viewer.html")
    assert signed_hex, "envelope artifacts must cover viewer.html in file_manifest"

    data = envelope_artifact.read_bytes()
    marker_idx = data.find(EPI_ZIP_MARKER)
    region = bytes(data[EPI_ENVELOPE_HEADER_SIZE:marker_idx])
    html = region[len(_POLYGLOT_PREFIX):] if region.startswith(_POLYGLOT_PREFIX) else region

    assert hashlib.sha256(html).hexdigest() == signed_hex


def test_legit_artifact_passes_integrity(envelope_artifact: Path):
    ok, mismatches = EPIContainer.verify_integrity(envelope_artifact)
    assert ok is True, mismatches


def test_naive_display_layer_edit_is_detected(envelope_artifact: Path, tmp_path: Path):
    """Control: edit the display layer, leave the header copy alone."""
    forged = _forge_display_layer(
        envelope_artifact,
        tmp_path / "naive_forgery.epi",
        recompute_header_hash=False,
    )

    ok, mismatches = EPIContainer.verify_integrity(forged)
    assert ok is False
    assert "__polyglot_viewer__" in mismatches


def test_consistent_display_layer_forgery_is_detected(envelope_artifact: Path, tmp_path: Path):
    """The forgery the unsigned header copy cannot catch on its own.

    Edit the display layer *and* recompute the envelope's ``reserved_tail``
    copy. Every hash that is not covered by the signature is now consistent,
    so only the signed ``file_manifest`` entry for ``viewer.html`` can detect
    this. Before the fix this file verified as PASS.
    """
    forged = _forge_display_layer(
        envelope_artifact,
        tmp_path / "consistent_forgery.epi",
        recompute_header_hash=True,
    )

    # The payload and the signature are untouched — only the display layer moved.
    manifest = EPIContainer.read_manifest(forged)
    assert manifest.signature, "precondition: artifact is still signed"

    ok, mismatches = EPIContainer.verify_integrity(forged)
    assert ok is False, f"consistent display-layer forgery must fail integrity: {mismatches}"
    assert "__polyglot_viewer__" in mismatches
    assert "signed" in mismatches["__polyglot_viewer__"].lower()


def test_consistent_display_layer_forgery_fails_cli_verify(envelope_artifact: Path, tmp_path: Path):
    """End-to-end: `epi verify` must not report a forged display layer as PASS."""
    forged = _forge_display_layer(
        envelope_artifact,
        tmp_path / "consistent_forgery.epi",
        recompute_header_hash=True,
    )

    result = runner.invoke(app, ["verify", str(forged), "--json"])
    assert result.exit_code != 0, result.output

    report = json.loads(result.stdout)
    assert report["facts"]["integrity_ok"] is False
    assert report["decision"]["status"] == "FAIL"
