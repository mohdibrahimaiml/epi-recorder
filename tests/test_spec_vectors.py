"""Check the normative spec vectors against the code that implements them."""

from __future__ import annotations

import json
from pathlib import Path

from epi_core.container import (
    EPI_CONTAINER_FORMAT_ENVELOPE,
    EPI_CONTAINER_FORMAT_LEGACY,
    EPI_ENVELOPE_HEADER_SIZE,
    EPI_ENVELOPE_MAGIC,
    EPI_LEGACY_MIMETYPE,
    EPI_MIMETYPE,
    EPI_SUPPORTED_UPLOAD_MIMETYPES,
    EPI_ZIP_MARKER,
)
from epi_core.serialize import hash_normalized_dict

VECTORS = Path(__file__).resolve().parents[1] / "docs" / "spec" / "test-vectors" / "test-vectors.json"


def _load() -> dict[str, dict]:
    return {item["id"]: item for item in json.loads(VECTORS.read_text(encoding="utf-8"))}


def test_tv001_manifest_jcs_hash_matches_code() -> None:
    vector = _load()["tv-001"]
    assert hash_normalized_dict(vector["input"], "jcs") == vector["hash"]


def test_tv003_container_constants_match_code() -> None:
    vector = _load()["tv-003"]
    assert vector["header_size"] == EPI_ENVELOPE_HEADER_SIZE
    assert vector["zip_marker"].encode("utf-8") == EPI_ZIP_MARKER
    assert EPI_ENVELOPE_MAGIC == b"<!--"
    assert EPI_CONTAINER_FORMAT_ENVELOPE == "envelope-v2"
    assert EPI_CONTAINER_FORMAT_LEGACY == "legacy-zip"


def test_tv004_mime_constants_match_code() -> None:
    vector = _load()["tv-004"]
    # `application/vnd.epi` is the download Content-Type; the +zip identifier
    # is the ZIP member and the accepted upload type. Both are supported.
    assert vector["envelope_v2_mime"] in EPI_SUPPORTED_UPLOAD_MIMETYPES
    assert EPI_MIMETYPE in EPI_SUPPORTED_UPLOAD_MIMETYPES
    assert vector["legacy_zip_mime"] == EPI_LEGACY_MIMETYPE
    assert vector["mimetype_file"] == EPI_LEGACY_MIMETYPE


def test_tv005_signature_lengths_are_ed25519() -> None:
    vector = _load()["tv-005"]
    assert vector["algorithm"] == "ed25519"
    assert vector["sig_raw_len"] == 64
    assert vector["sig_hex_len"] == vector["sig_raw_len"] * 2
