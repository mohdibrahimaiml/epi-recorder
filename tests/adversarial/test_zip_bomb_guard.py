"""Adversarial: a .epi must not be able to expand without limit (F-22).

A ``.epi`` is a ZIP. A hostile one can declare a member that expands to orders
of magnitude more than the file occupies on disk. The red team measured
``epi verify`` expanding **524,637,162 bytes out of a 957,623-byte artifact**
(547x) with no limit of any kind — enough to exhaust the disk of any machine
that opens an untrusted file.

The guard reads the ZIP *central directory* (declared uncompressed sizes), so a
bomb is refused without spending the memory or disk needed to discover it.

These tests pin that:

* a bomb is refused by ``epi verify`` (and by ``epi_core`` directly),
* an ordinary artifact is unaffected,
* the limits are operator-overridable.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app
from epi_core.container import (
    EPI_CONTAINER_FORMAT_ENVELOPE,
    EPI_ZIP_MARKER,
    EPIContainer,
    _EPI_ENVELOPE_HEADER_STRUCT as HDR,
)
from epi_core.schemas import ManifestModel
from epi_core.trust import sign_manifest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

runner = CliRunner()

BOMB_NAME = "artifacts/bomb.bin"
BOMB_BYTES = 64 * 1024 * 1024  # 64 MiB of zeros -> ~64 KiB compressed


def _build_base(tmp_path: Path) -> tuple[Path, Ed25519PrivateKey]:
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "steps.jsonl").write_text(
        json.dumps({"index": 0, "timestamp": "2026-04-12T00:00:00Z",
                    "kind": "llm.request", "span_id": "s1",
                    "content": {"provider": "x", "model": "m", "messages": []}}) + "\n",
        encoding="utf-8",
    )
    (workspace / "environment.json").write_text(
        json.dumps({"python": "test"}), encoding="utf-8"
    )
    key = Ed25519PrivateKey.generate()
    out = tmp_path / "base.epi"
    EPIContainer.pack(
        workspace,
        ManifestModel(cli_command="pytest helper", goal="bomb fixture"),
        out,
        signer_function=lambda item: sign_manifest(item, key, "test"),
        preserve_generated=True,
        container_format=EPI_CONTAINER_FORMAT_ENVELOPE,
        generate_analysis=False,
    )
    return out, key


def _inject_bomb(base: Path, out: Path, bomb_bytes: int = BOMB_BYTES) -> Path:
    """Rebuild the artifact with a bomb member listed in file_manifest and
    the manifest re-signed, so the artifact is internally consistent."""
    data = bytearray(base.read_bytes())
    marker = data.find(EPI_ZIP_MARKER)
    marker_end = marker + len(EPI_ZIP_MARKER)
    payload = bytes(data[marker_end:])

    src = zipfile.ZipFile(io.BytesIO(payload))
    members = {i.filename: src.read(i.filename) for i in src.infolist()}
    manifest = json.loads(members["manifest.json"].decode("utf-8"))
    manifest["file_manifest"][BOMB_NAME] = hashlib.sha256(b"\0" * bomb_bytes).hexdigest()

    key = Ed25519PrivateKey.generate()
    signed = sign_manifest(ManifestModel.model_validate(manifest), key, "test")
    manifest_bytes = signed.model_dump_json(indent=2).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, member_bytes in members.items():
            if name == "manifest.json":
                continue
            compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            z.writestr(name, member_bytes, compress_type=compress_type)
        z.writestr("manifest.json", manifest_bytes, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr(BOMB_NAME, b"\0" * bomb_bytes, compress_type=zipfile.ZIP_DEFLATED)
    new_payload = buf.getvalue()

    rebuilt = bytearray(data[:marker_end]) + bytearray(new_payload)
    header = HDR.unpack(bytes(rebuilt[:128]))
    rebuilt[:128] = HDR.pack(
        header[0], header[1], header[2], header[3], len(new_payload),
        header[5], header[6],
        hashlib.sha256(new_payload).digest(), header[8],
    )
    out.write_bytes(bytes(rebuilt))
    return out


def test_bomb_member_is_refused_on_read(tmp_path: Path):
    base, _key = _build_base(tmp_path)
    bomb = _inject_bomb(base, tmp_path / "bomb.epi")

    with pytest.raises(ValueError, match="decompression-bomb guard"):
        EPIContainer.read_member_bytes(bomb, "manifest.json")


def test_bomb_member_is_refused_on_unpack(tmp_path: Path):
    base, _key = _build_base(tmp_path)
    bomb = _inject_bomb(base, tmp_path / "bomb.epi")

    with pytest.raises(ValueError, match="decompression-bomb guard"):
        EPIContainer.unpack(bomb, tmp_path / "out")


def test_bomb_member_fails_cli_verify(tmp_path: Path):
    base, _key = _build_base(tmp_path)
    bomb = _inject_bomb(base, tmp_path / "bomb.epi")

    result = runner.invoke(app, ["verify", str(bomb), "--json"])
    assert result.exit_code != 0, result.output

    report = json.loads(result.stdout)
    assert report["decision"]["status"] == "FAIL"
    blob = json.dumps(report).lower()
    assert "bomb" in blob or "refusing to expand" in blob, report


def test_ordinary_artifact_is_unaffected(tmp_path: Path):
    base, _key = _build_base(tmp_path)

    ok, mismatches = EPIContainer.verify_integrity(base)
    assert ok is True, mismatches

    unpacked = EPIContainer.unpack(base, tmp_path / "out")
    assert (unpacked / "steps.jsonl").exists()


def test_limits_are_operator_overridable(tmp_path: Path, monkeypatch):
    """An operator who legitimately stores very large artifacts can raise the caps."""
    base, _key = _build_base(tmp_path)
    bomb = _inject_bomb(base, tmp_path / "bomb.epi")

    monkeypatch.setenv("EPI_MAX_MEMBER_BYTES", str(4 * 1024 * 1024 * 1024))
    monkeypatch.setenv("EPI_MAX_EXPANDED_BYTES", str(4 * 1024 * 1024 * 1024))
    monkeypatch.setenv("EPI_MAX_EXPANSION_RATIO", "100000")

    # With the caps raised the member is readable again — the guard is a
    # policy decision, not a hard format limit.
    assert EPIContainer.read_member_bytes(bomb, "manifest.json")
