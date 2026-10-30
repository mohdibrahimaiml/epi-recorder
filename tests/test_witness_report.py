"""`epi witness report --cases`: what the customer's own record says, per case.

A signature protects a file from edits. It cannot stop the vendor rebuilding the
file and signing it again - the signature is valid because the key is genuinely
theirs. Only the customer's log distinguishes "this is what was reported" from
"this is a different version of that case".
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from epi_cli.witness import app
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.serialize import get_canonical_hash

runner = CliRunner()


def _seal(
    tmp_path: Path, name: str, decision: str = "approve", goal: str | None = None
) -> Path:
    source = tmp_path / f"{name}.src"
    source.mkdir(parents=True, exist_ok=True)
    (source / "steps.jsonl").write_text(
        json.dumps(
            {"index": 0, "kind": "agent.decision", "content": {"decision": decision}}
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / name
    EPIContainer.pack(
        source,
        ManifestModel(cli_command="pytest", goal=goal),
        out,
        preserve_generated=True,
        generate_analysis=False,
        notarize=False,
        embed_viewer=False,
    )
    return out


def _report(epi: Path, received_at: str = "2026-10-30T10:00:00+00:00") -> dict:
    """The hash-only line a witness receiver would have written for this file."""
    manifest = EPIContainer.read_manifest(epi)
    report = {
        "schema": "epi-witness/v1",
        "type": "epi.sealed",
        "workflow_id": str(manifest.workflow_id),
        "manifest_hash": get_canonical_hash(manifest, exclude_fields=["signature"]),
        "file_sha256": hashlib.sha256(epi.read_bytes()).hexdigest(),
        "steps": 1,
        "sealed_at": "2026-10-30T09:59:00+00:00",
        "received_at": received_at,
    }
    if manifest.goal:
        report["goal"] = str(manifest.goal)
    return report


def _log(tmp_path: Path, entries: list[dict], name: str = "received.jsonl") -> Path:
    path = tmp_path / name
    path.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8"
    )
    return path


def test_report_without_cases_lists_cases_in_the_log(tmp_path):
    one = _seal(tmp_path, "one.epi")
    two = _seal(tmp_path, "two.epi")
    log = _log(tmp_path, [_report(one), _report(two)])

    result = runner.invoke(app, ["report", "--log", str(log)])
    assert result.exit_code == 0, result.output
    assert "Witness cases" in result.output
    assert "2 report(s) across 2 case(s)" in result.output


def test_cases_marks_the_witnessed_file_and_the_stranger(tmp_path):
    witnessed = _seal(tmp_path, "witnessed.epi")
    never_reported = _seal(tmp_path, "never.epi")
    log = _log(tmp_path, [_report(witnessed)])

    result = runner.invoke(
        app,
        [
            "report",
            "--log",
            str(log),
            "--cases",
            str(witnessed),
            "--cases",
            str(never_reported),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "WITNESSED" in result.output
    assert "NOT IN WITNESS LOG" in result.output
    assert "1 witnessed, 1 not" in result.output


def test_a_rebuilt_record_of_the_same_case_is_a_mismatch(tmp_path):
    """The forgery: same workflow id, different bytes."""
    original = _seal(tmp_path, "run.epi", decision="approve")
    rebuilt = _seal(tmp_path, "run-forged.epi", decision="deny")
    log = _log(tmp_path, [_report(original)])

    # The customer's log holds a different version of the same case: same
    # workflow id, not the bytes they were handed.
    entry = json.loads(log.read_text(encoding="utf-8"))
    forged_line = dict(entry)
    forged_line["file_sha256"] = hashlib.sha256(rebuilt.read_bytes()).hexdigest()
    forged_log = _log(tmp_path, [forged_line], name="forged.jsonl")

    # The original is witnessed; the rebuilt copy of the same case is not.
    witnessed = runner.invoke(app, ["report", "--log", str(log), "--cases", str(original)])
    assert "WITNESSED" in witnessed.output

    mismatch = runner.invoke(
        app, ["report", "--log", str(forged_log), "--cases", str(original)]
    )
    assert mismatch.exit_code == 0, mismatch.output
    assert "MISMATCH" in mismatch.output


def test_fail_on_unwitnessed_exits_one(tmp_path):
    known = _seal(tmp_path, "known.epi")
    stranger = _seal(tmp_path, "stranger.epi")
    log = _log(tmp_path, [_report(known)])

    ok = runner.invoke(
        app, ["report", "--log", str(log), "--cases", str(known), "--fail-on-unwitnessed"]
    )
    assert ok.exit_code == 0, ok.output

    bad = runner.invoke(
        app,
        ["report", "--log", str(log), "--cases", str(stranger), "--fail-on-unwitnessed"],
    )
    assert bad.exit_code == 1
    assert "NOT IN WITNESS LOG" in bad.output


def test_json_output_is_machine_readable(tmp_path):
    known = _seal(tmp_path, "known.epi")
    log = _log(tmp_path, [_report(known)])

    result = runner.invoke(app, ["report", "--log", str(log), "--cases", str(known), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["reports"] == 1
    assert payload["unwitnessed"] == 0
    assert payload["checked_files"][0]["status"] == "WITNESSED"


def test_a_directory_of_files_is_accepted(tmp_path):
    first = _seal(tmp_path, "first.epi")
    log = _log(tmp_path, [_report(first)])
    directory = tmp_path / "cases"
    directory.mkdir()
    first.rename(directory / first.name)

    result = runner.invoke(app, ["report", "--log", str(log), "--cases", str(directory)])
    assert result.exit_code == 0, result.output
    assert "WITNESSED" in result.output


def test_unreadable_log_is_an_error_not_a_verdict(tmp_path):
    result = runner.invoke(app, ["report", "--log", str(tmp_path / "missing.jsonl")])
    assert result.exit_code == 2
    assert "could not" in result.output and "read" in result.output


def test_the_report_names_the_case_the_customer_knows(tmp_path):
    """A claim number beats a workflow uuid for an insurer reading the report."""
    epi = _seal(tmp_path, "claim.epi", goal="Adjudicate claim CLM-1001")
    entry = _report(epi)
    entry["case_id"] = "CLM-1001"
    log = _log(tmp_path, [entry])

    result = runner.invoke(app, ["report", "--log", str(log), "--cases", str(epi)])
    assert result.exit_code == 0, result.output
    assert "CLM-1001" in result.output
    assert "WITNESSED" in result.output


def test_a_new_run_of_the_same_case_is_reported_as_a_different_version(tmp_path):
    """The vendor re-runs the agent: new workflow id, same claim.

    By id alone this is "never reported". The log still names the case, so the
    report can say the stronger thing: a different version of CLM-1001 exists.
    """
    original = _seal(tmp_path, "run.epi", decision="approve", goal="Adjudicate claim CLM-1001")
    rerun = _seal(tmp_path, "rerun.epi", decision="deny", goal="Adjudicate claim CLM-1001")
    log = _log(tmp_path, [_report(original)])

    result = runner.invoke(
        app, ["report", "--log", str(log), "--cases", str(rerun), "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    checked = payload["checked_files"][0]
    assert checked["status"] == "MISMATCH"
    assert checked["detail"].startswith("a different version of")
    assert "CLM-1001" in checked["detail"]
    assert checked["case_id"] == "Adjudicate claim CLM-1001"


def test_expect_csv_marks_claims_with_no_record_as_missing(tmp_path):
    known = _seal(tmp_path, "known.epi", goal="Adjudicate claim CLM-1001")
    entry = _report(known)
    entry["case_id"] = "CLM-1001"
    log = _log(tmp_path, [entry])
    cases = tmp_path / "cases.csv"
    cases.write_text("claim_id\nCLM-1001\nCLM-2002\n", encoding="utf-8")

    result = runner.invoke(
        app, ["report", "--log", str(log), "--expect", str(cases), "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    statuses = {item["case"]: item["status"] for item in payload["expected"]}
    assert statuses == {"CLM-1001": "FOUND", "CLM-2002": "MISSING"}
    assert payload["missing"] == 1

    strict = runner.invoke(
        app,
        ["report", "--log", str(log), "--expect", str(cases), "--fail-on-unwitnessed"],
    )
    assert strict.exit_code == 1, strict.output
