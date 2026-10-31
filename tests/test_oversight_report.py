"""The oversight report answers the period-shaped question a bank actually asks.

Over three months: what did your AI decide, which model answered, who approved
it, which cases did the vendor report but never deliver, and which cases did you
expect that were never sealed at all.

Every number comes from files the customer holds plus their own witness log. The
tests build exactly that situation, including one case that exists only in the
log and one that exists only in the customer's expectations.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from epi_cli.main import app
from epi_core.approvers import ApproverRegistry
from epi_core.container import EPIContainer
from epi_core.review import ReviewRecord, add_review_to_artifact, make_approval_entry
from epi_core.schemas import ManifestModel
from epi_core.serialize import get_canonical_hash
from epi_core.trust import sign_manifest
from epi_core.webhook import build_witness_payload, witness_content_digest

runner = CliRunner()

SERVED = "gpt-4o-2024-08-06"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_TRUSTED_APPROVERS_DIR", str(tmp_path / "trusted_approvers"))
    monkeypatch.setenv("EPI_APPROVER_KEYS_DIR", str(tmp_path / "approver_keys"))
    monkeypatch.delenv("EPI_WITNESS_LOG", raising=False)


def _keypair():
    key = Ed25519PrivateKey.generate()
    public_hex = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    return key, public_hex


def _seal(
    tmp_path: Path,
    *,
    name: str,
    outcome: str,
    created_at: str,
    approval: str | None = None,  # "pinned" | "unpinned" | None
) -> Path:
    source = tmp_path / f"{name}.src"
    source.mkdir(parents=True, exist_ok=True)
    steps = [
        {
            "index": 0,
            "kind": "llm.response",
            "content": {"provider": "openai", "model": "gpt-4o", "served_model": SERVED},
        },
        {
            "index": 1,
            "kind": "agent.decision",
            "content": {
                "decision": outcome,
                "rationale": f"{outcome} for policy reasons.",
                "basis": {"policy": "HO3-4.2"},
            },
        },
        {
            "index": 2,
            "kind": "agent.approval.request",
            "content": {"action": "act on it", "approval_id": "approval-1"},
        },
    ]
    (source / "steps.jsonl").write_text(
        "\n".join(json.dumps(step) for step in steps) + "\n", encoding="utf-8"
    )
    sealing_key = Ed25519PrivateKey.generate()
    out = tmp_path / name
    EPIContainer.pack(
        source,
        ManifestModel(
            workflow_id=f"1f0f3c1e-0000-4000-8000-{abs(hash(name)) % 10**12:012d}",
            created_at=created_at,
            cli_command="pytest",
            goal=f"Adjudicate claim {name}",
        ),
        out,
        signer_function=lambda manifest: sign_manifest(manifest, sealing_key, "vendor"),
        preserve_generated=True,
        generate_analysis=False,
        notarize=False,
        embed_viewer=False,
    )
    if approval:
        approver_key, approver_public = _keypair()
        if approval == "pinned":
            ApproverRegistry().add("dana", approver_public)
        from epi_core.keys import key_fingerprint

        record = ReviewRecord(
            reviewed_by="dana@insurer.example",
            reviews=[
                make_approval_entry(
                    approval_id="approval-1",
                    decision="approve",
                    action="act on it",
                    reason="checked",
                    approver_name="dana@insurer.example",
                    key_fingerprint_hex=key_fingerprint(approver_public, grouped=False),
                )
            ],
        )
        add_review_to_artifact(out, record, private_key=approver_key)
    return out


def _witness_entry(epi: Path, *, case_id: str, received_at: str) -> dict:
    manifest = EPIContainer.read_manifest(epi)
    return build_witness_payload(
        workflow_id=str(manifest.workflow_id),
        manifest_hash=get_canonical_hash(manifest, exclude_fields=["signature"]),
        file_sha256=hashlib.sha256(epi.read_bytes()).hexdigest(),
        content_digest=witness_content_digest(manifest),
        public_key=getattr(manifest, "public_key", None),
        key_fingerprint=None,
        steps=len(EPIContainer.read_steps(epi)),
        sealed_at=received_at,
        seal_timestamp={"status": "none", "gen_time": None},
        goal=str(manifest.goal),
        case_id=case_id,
    ) | {"received_at": received_at}


def _write_log(tmp_path: Path, entries: list[dict]) -> Path:
    log = tmp_path / "received.jsonl"
    log.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8"
    )
    return log


@pytest.fixture
def case_set(tmp_path):
    """Two decisions in the period, one outside it, one reported-but-missing case."""
    pinned = _seal(
        tmp_path, name="clm-1.epi", outcome="Approved", created_at="2026-09-12T09:00:00Z", approval="pinned"
    )
    unpinned = _seal(
        tmp_path, name="clm-2.epi", outcome="Denied", created_at="2026-10-03T11:00:00Z", approval="unpinned"
    )
    old = _seal(
        tmp_path, name="clm-3.epi", outcome="Approved", created_at="2026-01-05T08:00:00Z"
    )
    log = _write_log(
        tmp_path,
        [
            _witness_entry(pinned, case_id="CLM-1", received_at="2026-09-12T09:01:00Z"),
            _witness_entry(unpinned, case_id="CLM-2", received_at="2026-10-03T11:01:00Z"),
            {
                "schema": "epi.witness.v1",
                "type": "epi.sealed",
                "workflow_id": "99999999-0000-4000-8000-000000000009",
                "manifest_hash": "0" * 64,
                "file_sha256": "1" * 64,
                "steps": 3,
                "sealed_at": "2026-10-10T10:00:00Z",
                "seal_timestamp": {"status": "none", "gen_time": None},
                "goal": "Adjudicate claim CLM-9",
                "case_id": "CLM-9",
                "received_at": "2026-10-10T10:00:05Z",
            },
        ],
    )
    expect = tmp_path / "cases.csv"
    expect.write_text("case_id\nCLM-1\nCLM-2\nCLM-7\n", encoding="utf-8")
    return {"dir": tmp_path, "log": log, "expect": expect, "files": [pinned, unpinned, old]}


def _run(case_set, *extra):
    return runner.invoke(
        app,
        [
            "oversight",
            "report",
            "--cases",
            str(case_set["dir"]),
            "--log",
            str(case_set["log"]),
            "--since",
            "2026-09-01",
            "--until",
            "2026-10-31",
            "--expect",
            str(case_set["expect"]),
            *extra,
        ],
    )


def test_the_period_selects_the_decisions(case_set):
    result = _run(case_set, "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)

    assert payload["sealed"]["files"] == 3
    assert payload["sealed"]["decisions_in_period"] == 2, "January is outside the window"
    assert payload["outcomes"] == {"Approved": 1, "Denied": 1}


def test_the_models_are_the_ones_that_answered(case_set):
    payload = json.loads(_run(case_set, "--json").stdout)
    assert list(payload["models"]) == [SERVED]
    assert payload["models"][SERVED]["count"] == 2


def test_pinned_and_unpinned_approvals_stay_distinct(case_set):
    payload = json.loads(_run(case_set, "--json").stdout)
    assert payload["approvals"]["pinned"] == 1
    assert payload["approvals"]["unpinned"] == 1
    assert payload["approvals"]["absent"] == 0

    by_case = {item["case"]: item for item in payload["decisions"]}
    assert by_case["CLM-1"]["approval"] == "pinned"
    assert by_case["CLM-2"]["approval"] == "unpinned"


def test_a_case_reported_but_never_delivered_is_named(case_set):
    payload = json.loads(_run(case_set, "--json").stdout)
    assert [item["case"] for item in payload["reported_not_delivered"]] == ["CLM-9"]
    assert payload["reported_not_delivered"][0]["reports"] == 1


def test_a_case_expected_but_never_sealed_is_named(case_set):
    payload = json.loads(_run(case_set, "--json").stdout)
    assert [item["case"] for item in payload["expected_never_sealed"]] == ["CLM-7"]
    assert payload["expected_total"] == 3


def test_files_are_matched_to_the_witness_log(case_set):
    payload = json.loads(_run(case_set, "--json").stdout)
    assert payload["witness"]["witnessed"] == 2


def test_the_html_is_one_page_a_customer_can_read(case_set, tmp_path):
    out = tmp_path / "oversight.html"
    result = _run(case_set, "--out", str(out))
    assert result.exit_code == 0, result.output
    html = out.read_text(encoding="utf-8")

    assert "Oversight Report" in html
    assert "Decisions by outcome" in html
    assert "Model versions" in html
    assert SERVED in html
    assert "Human approvals" in html
    assert "Reported to you, but no file delivered" in html
    assert "CLM-9" in html
    assert "CLM-7" in html
    assert "https://epilabs.org/verify" in html
    # the period is stated, not implied
    assert "2026-09-01" in html and "2026-10-31" in html


def test_gaps_can_fail_a_scripted_check(case_set):
    assert _run(case_set).exit_code == 0
    assert _run(case_set, "--fail-on-gaps").exit_code == 1


def test_a_bad_date_is_refused(case_set):
    result = runner.invoke(
        app,
        ["oversight", "report", "--cases", str(case_set["dir"]), "--since", "September"],
    )
    assert result.exit_code == 2
    assert "YYYY-MM-DD" in result.output
