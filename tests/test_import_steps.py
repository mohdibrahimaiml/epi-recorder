"""`epi import steps` — seal a step log the customer already has.

This is the input path that makes "send us the export" true for JSONL/CSV
exports, so the packs do not depend on EPI's SDK being installed at the source.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.keys import KeyManager
from epi_cli.main import app
from epi_core.container import EPIContainer
from epi_core.schemas import StepModel
from epi_core.serialize import get_canonical_hash
from epi_core.trust import verify_embedded_manifest_signature

runner = CliRunner()


@pytest.fixture
def signing_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    monkeypatch.setenv("EPI_KEYS_DIR", str(keys_dir))
    KeyManager(keys_dir=keys_dir).generate_keypair("default")
    return keys_dir


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


STEPS_JSONL = "\n".join(
    [
        json.dumps({"timestamp": "2026-10-01T09:00:00Z", "kind": "agent.run.start",
                    "content": {"agent": "claims-bot"}}),
        json.dumps({"timestamp": "2026-10-01T09:00:01Z", "kind": "tool.call",
                    "content": {"tool": "lookup", "id": "CL-77"}}),
        json.dumps({"timestamp": "2026-10-01T09:00:02Z", "kind": "agent.decision",
                    "content": {"decision": "approve", "confidence": 0.91}}),
    ]
) + "\n"


def _steps(path: Path) -> list[StepModel]:
    data = path.read_bytes()
    marker = b"\n<!-- EPI_ZIP_PAYLOAD_START -->\n"
    payload = data[data.find(marker) + len(marker):] if data[:4] == b"<!--" else data
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        raw = zf.read("steps.jsonl").decode()
    return [StepModel.model_validate_json(line) for line in raw.splitlines() if line.strip()]


def test_jsonl_import_seals_a_verifiable_chained_artifact(tmp_path, signing_key):
    src = _write(tmp_path, "steps.jsonl", STEPS_JSONL)
    out = tmp_path / "case.epi"

    result = runner.invoke(
        app, ["import", "steps", str(src), "--out", str(out), "--goal", "claim CL-77"]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()

    ok, mismatches = EPIContainer.verify_integrity(out)
    assert ok is True, mismatches

    manifest = EPIContainer.read_manifest(out)
    valid, _fp, reason = verify_embedded_manifest_signature(manifest)
    assert valid is True, reason
    assert manifest.total_steps == 3
    assert manifest.goal == "claim CL-77"

    steps = _steps(out)
    assert [s.index for s in steps] == [0, 1, 2]
    assert steps[0].prev_hash == "CHAIN_START"
    for i in range(1, len(steps)):
        assert steps[i].prev_hash == get_canonical_hash(steps[i - 1], format="json")


def test_csv_import_merges_extra_columns_into_content(tmp_path, signing_key):
    src = _write(
        tmp_path,
        "steps.csv",
        'kind,content,timestamp,ticket\n'
        'agent.run.start,"{""agent"":""csv-bot""}",2026-10-02T10:00:00Z,T-9\n'
        'agent.decision,"{""decision"":""reject""}",2026-10-02T10:00:05Z,T-9\n',
    )
    out = tmp_path / "csv.epi"

    result = runner.invoke(app, ["import", "steps", str(src), "--out", str(out)])
    assert result.exit_code == 0, result.output

    steps = _steps(out)
    assert len(steps) == 2
    assert steps[0].content["agent"] == "csv-bot"
    assert steps[0].content["ticket"] == "T-9"
    assert steps[0].content["_epi_import"]["format"] == "csv"
    assert EPIContainer.verify_integrity(out)[0] is True


def test_missing_timestamp_is_declared_not_silent(tmp_path, signing_key):
    src = _write(
        tmp_path,
        "no-ts.jsonl",
        '{"kind":"agent.run.start","content":{"a":1}}\n{"kind":"agent.decision","content":{"d":"approve"}}\n',
    )
    out = tmp_path / "no-ts.epi"

    result = runner.invoke(app, ["import", "steps", str(src), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "Timestamps assumed" in result.output

    steps = _steps(out)
    assert all(s.content["_epi_import"]["timestamp_assumed"] is True for s in steps)
    assert "timestamp" in EPIContainer.read_manifest(out).notes.lower()


def test_missing_kind_fails_with_the_row_number(tmp_path, signing_key):
    src = _write(tmp_path, "bad.csv", 'content,timestamp\n"{""x"":1}",2026-10-01T09:00:00Z\n')

    result = runner.invoke(app, ["import", "steps", str(src), "--out", str(tmp_path / "bad.epi")])
    assert result.exit_code == 1
    assert "row 1" in result.output and "kind" in result.output


def test_invalid_json_line_points_at_the_line(tmp_path, signing_key):
    src = _write(tmp_path, "broken.jsonl", '{"kind":"a","content":{}}\n{not json}\n')

    result = runner.invoke(app, ["import", "steps", str(src), "--out", str(tmp_path / "b.epi")])
    assert result.exit_code == 1
    assert "line 2" in result.output


def test_unsupported_extension_is_refused(tmp_path, signing_key):
    src = _write(tmp_path, "steps.txt", '{"kind":"a"}')

    result = runner.invoke(app, ["import", "steps", str(src), "--out", str(tmp_path / "c.epi")])
    assert result.exit_code == 1
    assert "unsupported input" in result.output


def test_with_viewer_produces_a_self_opening_artifact(tmp_path, signing_key):
    src = _write(tmp_path, "steps.jsonl", STEPS_JSONL)
    out = tmp_path / "viewer.epi"

    result = runner.invoke(
        app, ["import", "steps", str(src), "--out", str(out), "--with-viewer"]
    )
    assert result.exit_code == 0, result.output
    assert out.read_bytes()[:4] == b"<!--"
    assert EPIContainer.detect_container_format(out) == "envelope-v2"


def test_no_sign_produces_an_unsigned_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "empty-keys"))
    src = _write(tmp_path, "steps.jsonl", STEPS_JSONL)
    out = tmp_path / "unsigned.epi"

    result = runner.invoke(
        app, ["import", "steps", str(src), "--out", str(out), "--no-sign"]
    )
    assert result.exit_code == 0, result.output
    manifest = EPIContainer.read_manifest(out)
    assert manifest.signature is None
    assert manifest.public_key is None
