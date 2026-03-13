"""
Extended tests for epi_core.container — pack, unpack, verify_integrity,
read_manifest, and embedded viewer generation.
"""

import json
import hashlib
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_source_dir(tmp_path: Path, steps: str = "") -> Path:
    """Create a minimal source directory for EPIContainer.pack()."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "steps.jsonl").write_text(steps or '{"index":0,"kind":"test","content":{}}\n', encoding="utf-8")
    (src / "environment.json").write_text('{"python": "3.11"}', encoding="utf-8")
    return src


# ─────────────────────────────────────────────────────────────
# read_manifest
# ─────────────────────────────────────────────────────────────

class TestReadManifest:
    def test_reads_valid_manifest(self, tmp_path):
        manifest = ManifestModel(
            workflow_id=uuid4(),
            created_at=datetime.utcnow(),
            cli_command="python test.py",
            file_manifest={"steps.jsonl": "abc123"},
        )
        epi = tmp_path / "test.epi"
        with zipfile.ZipFile(epi, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("manifest.json", manifest.model_dump_json())
            zf.writestr("steps.jsonl", "")

        result = EPIContainer.read_manifest(epi)
        assert result.workflow_id == manifest.workflow_id
        assert result.cli_command == "python test.py"

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            EPIContainer.read_manifest(tmp_path / "nonexistent.epi")

    def test_raises_on_bad_zip(self, tmp_path):
        bad = tmp_path / "bad.epi"
        bad.write_bytes(b"not a zip")
        with pytest.raises(Exception):
            EPIContainer.read_manifest(bad)

    def test_raises_on_missing_manifest_json(self, tmp_path):
        epi = tmp_path / "no_manifest.epi"
        with zipfile.ZipFile(epi, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("steps.jsonl", "")
        with pytest.raises(Exception):
            EPIContainer.read_manifest(epi)


# ─────────────────────────────────────────────────────────────
# verify_integrity
# ─────────────────────────────────────────────────────────────

class TestVerifyIntegrity:
    def _make_valid_epi(self, tmp_path: Path) -> Path:
        steps = b'{"index":0,"kind":"test","content":{}}\n'
        steps_hash = _sha256(steps)

        manifest = ManifestModel(
            workflow_id=uuid4(),
            created_at=datetime.utcnow(),
            cli_command="python test.py",
            file_manifest={"steps.jsonl": steps_hash},
        )
        epi = tmp_path / "valid.epi"
        with zipfile.ZipFile(epi, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("manifest.json", manifest.model_dump_json())
            zf.writestr("steps.jsonl", steps)
        return epi

    def test_valid_file_passes(self, tmp_path):
        epi = self._make_valid_epi(tmp_path)
        ok, mismatches = EPIContainer.verify_integrity(epi)
        assert ok
        assert mismatches == {}

    def test_tampered_file_fails(self, tmp_path):
        epi = self._make_valid_epi(tmp_path)

        # Tamper steps.jsonl
        with zipfile.ZipFile(epi, "r") as zin:
            files = {n: zin.read(n) for n in zin.namelist()}
        files["steps.jsonl"] = b'{"tampered": true}\n'
        tampered = tmp_path / "tampered.epi"
        with zipfile.ZipFile(tampered, "w") as zout:
            for name, data in files.items():
                zout.writestr(name, data)

        ok, mismatches = EPIContainer.verify_integrity(tampered)
        assert not ok
        assert "steps.jsonl" in mismatches

    def test_empty_file_manifest_passes(self, tmp_path):
        manifest = ManifestModel(
            workflow_id=uuid4(),
            created_at=datetime.utcnow(),
            file_manifest={},
        )
        epi = tmp_path / "empty.epi"
        with zipfile.ZipFile(epi, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("manifest.json", manifest.model_dump_json())
        ok, mismatches = EPIContainer.verify_integrity(epi)
        assert ok
        assert mismatches == {}

    def test_returns_mismatch_details(self, tmp_path):
        epi = self._make_valid_epi(tmp_path)
        with zipfile.ZipFile(epi, "r") as zin:
            files = {n: zin.read(n) for n in zin.namelist()}
        files["steps.jsonl"] = b"changed content\n"
        tampered = tmp_path / "t.epi"
        with zipfile.ZipFile(tampered, "w") as zout:
            for name, data in files.items():
                zout.writestr(name, data)

        ok, mismatches = EPIContainer.verify_integrity(tampered)
        assert "steps.jsonl" in mismatches
        assert "mismatch" in mismatches["steps.jsonl"].lower()


# ─────────────────────────────────────────────────────────────
# unpack
# ─────────────────────────────────────────────────────────────

class TestUnpack:
    def test_unpack_extracts_files(self, tmp_path):
        steps = b'{"index":0}\n'
        manifest = ManifestModel(
            file_manifest={"steps.jsonl": _sha256(steps)},
        )
        epi = tmp_path / "test.epi"
        with zipfile.ZipFile(epi, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("manifest.json", manifest.model_dump_json())
            zf.writestr("steps.jsonl", steps)

        out = tmp_path / "out"
        EPIContainer.unpack(epi, out)
        assert (out / "manifest.json").exists()
        assert (out / "steps.jsonl").exists()

    def test_unpack_nonexistent_raises(self, tmp_path):
        with pytest.raises(Exception):
            EPIContainer.unpack(tmp_path / "ghost.epi", tmp_path / "out")
