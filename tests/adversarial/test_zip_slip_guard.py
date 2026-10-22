"""Adversarial: no path may escape the extraction directory (zip-slip).

`EPIContainer.unpack()` has always guarded member names against traversal.
`AutoSCITTAnchor._embed_receipt()` opened the artifact as a **bare ZIP** and
called `extractall()` with no such guard — bypassing the protection the rest
of the codebase relies on. A member named ``../../escape.txt`` would be
written outside the extraction directory.

The guard now lives in both places. These tests pin it.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from epi_core.schemas import ManifestModel
from epi_core.scitt import SCITTServiceInfo
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _write_zip_with_traversal_member(path: Path, member_name: str) -> Path:
    """A ZIP whose member name tries to escape the extraction directory.

    ``mimetype`` comes first and STORED, because the container reader rejects
    a re-packed archive as a forensic violation before it ever reaches the
    traversal guard — the guard must be reached, not short-circuited.
    """
    from epi_core.container import EPI_LEGACY_MIMETYPE

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", EPI_LEGACY_MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("manifest.json", json.dumps({"cli_command": "x", "goal": "y"}))
        zf.writestr("steps.jsonl", "{}\n")
        zf.writestr(member_name, "pwned")
    return path


def test_auto_scitt_embed_receipt_refuses_path_traversal(tmp_path: Path, monkeypatch):
    """The SCITT anchor path must refuse a member that escapes the target dir."""
    from epi_recorder.auto_scitt import AutoSCITTAnchor

    monkeypatch.chdir(tmp_path)
    evil = _write_zip_with_traversal_member(
        tmp_path / "evil.epi", "../../epi_zip_slip_probe.txt"
    )
    escape_target = (tmp_path / ".." / ".." / "epi_zip_slip_probe.txt").resolve()

    anchor = AutoSCITTAnchor(service_url="http://127.0.0.1:1")
    manifest = ManifestModel(cli_command="probe", goal="probe", governance={})
    info = SCITTServiceInfo(
        service_url="http://127.0.0.1:1",
        entry_id="probe",
        registered_at="2026-10-22T00:00:00Z",
    )
    key = Ed25519PrivateKey.generate()

    with pytest.raises(ValueError, match="Path traversal detected"):
        anchor._embed_receipt(
            evil, manifest, b"statement", b"receipt", info, key, "probe"
        )

    assert not escape_target.exists(), "a file escaped the extraction directory"


def test_container_unpack_still_refuses_path_traversal(tmp_path: Path):
    """The pre-existing guard in EPIContainer.unpack() must keep working."""
    from epi_core.container import EPIContainer

    evil = _write_zip_with_traversal_member(
        tmp_path / "evil2.epi", "../../epi_zip_slip_probe2.txt"
    )
    with pytest.raises(ValueError, match="Path traversal detected"):
        EPIContainer.unpack(evil, tmp_path / "out")
