"""Legacy EPI1 header probe — PK at 4/16/38/64 + garbage rejection.

Spec §2.2: magic `EPI1`, ZIP follows. Historical code cited header sizes
16/38/64 with no surviving writer, so the reader probes a bounded window
for the ZIP signature instead of trusting any single offset.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from epi_core.container import (
    EPI_CONTAINER_FORMAT_LEGACY,
    EPI_LEGACY_MIMETYPE,
    EPIContainer,
)

PROBE_OFFSETS = [4, 16, 38, 64]


def _minimal_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", EPI_LEGACY_MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("manifest.json", b"{}", compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


@pytest.mark.parametrize("zip_offset", PROBE_OFFSETS)
def test_epi1_detected_regardless_of_header_length(tmp_path: Path, zip_offset: int):
    blob = b"EPI1" + b"\x00" * (zip_offset - 4) + _minimal_zip_bytes()
    target = tmp_path / f"legacy_{zip_offset}.epi"
    target.write_bytes(blob)
    assert EPIContainer.detect_container_format(target) == EPI_CONTAINER_FORMAT_LEGACY
    assert EPIContainer.legacy_zip_offset(target) == zip_offset


@pytest.mark.parametrize("zip_offset", PROBE_OFFSETS)
def test_epi1_payload_strips_to_valid_zip(tmp_path: Path, zip_offset: int):
    blob = b"EPI1" + b"\x00" * (zip_offset - 4) + _minimal_zip_bytes()
    target = tmp_path / f"legacy_{zip_offset}.epi"
    target.write_bytes(blob)
    with EPIContainer._payload_zip_path(target) as payload:
        with zipfile.ZipFile(payload, "r") as zf:
            assert zf.read("mimetype").decode("utf-8") == EPI_LEGACY_MIMETYPE
            assert zf.read("manifest.json") == b"{}"


@pytest.mark.parametrize("zip_offset", PROBE_OFFSETS)
def test_epi1_extract_inner_payload_strips_header(tmp_path: Path, zip_offset: int):
    blob = b"EPI1" + b"\x00" * (zip_offset - 4) + _minimal_zip_bytes()
    target = tmp_path / f"legacy_{zip_offset}.epi"
    target.write_bytes(blob)
    out = tmp_path / "payload.zip"
    EPIContainer.extract_inner_payload(target, out)
    with zipfile.ZipFile(out, "r") as zf:
        assert zf.read("mimetype").decode("utf-8") == EPI_LEGACY_MIMETYPE


def test_epi1_without_zip_signature_rejected(tmp_path: Path):
    target = tmp_path / "garbage.epi"
    target.write_bytes(b"EPI1" + b"\x00" * 60)
    assert EPIContainer.legacy_zip_offset(target) is None
    with pytest.raises(ValueError, match="no ZIP payload"):
        EPIContainer.detect_container_format(target)


def test_non_epi1_returns_none_offset(tmp_path: Path):
    target = tmp_path / "plain.zip"
    target.write_bytes(_minimal_zip_bytes())
    assert EPIContainer.legacy_zip_offset(target) is None
    assert EPIContainer.detect_container_format(target) == EPI_CONTAINER_FORMAT_LEGACY
