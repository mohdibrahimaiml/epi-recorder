"""The readable Decision Record must answer "why did the AI decide this?".

Tested against the document a customer actually receives: outcome, principal
reasons, the data and rules relied on, the served model, the approver exactly as
`epi verify` classifies them, and the instructions to check it.
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
from epi_core.container import EPIContainer
from epi_core.keys import key_fingerprint
from epi_core.review import ReviewRecord, add_review_to_artifact, make_approval_entry
from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now
from epi_core.trust import sign_manifest

runner = CliRunner()

RATIONALE = "Flood exclusion HO3-4.2 applies; the peril is excluded under the policy."
SERVED_MODEL = "gpt-4o-2024-08-06"


def _seal(tmp_path: Path, *, with_approval: bool, name: str = "claim.epi") -> Path:
    source = tmp_path / "src"
    source.mkdir(parents=True, exist_ok=True)
    steps = [
        {
            "index": 0,
            "kind": "llm.request",
            "content": {"provider": "openai", "model": "gpt-4o", "messages": [{"role": "user", "content": "CLM-1001"}]},
        },
        {
            "index": 1,
            "kind": "llm.response",
            "content": {
                "provider": "openai",
                "model": "gpt-4o",
                "served_model": SERVED_MODEL,
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "deny_claim",
                                        "arguments": json.dumps(
                                            {"claim_id": "CLM-1001", "reason": "excluded peril"}
                                        ),
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            },
        },
        {
            "index": 2,
            "kind": "agent.decision",
            "content": {
                "decision": "deny_claim",
                "rationale": RATIONALE,
                "basis": {
                    "policy": "HO3-4.2",
                    "data": ["claim:CLM-1001", "policy:HO3"],
                },
            },
        },
        {
            "index": 3,
            "kind": "agent.approval.request",
            "content": {"action": "issue denial notice", "approval_id": "denial-1"},
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
            workflow_id="1f0f3c1e-0000-4000-8000-000000000001",
            created_at=utc_now(),
            cli_command="pytest",
            goal="Adjudicate claim CLM-1001",
        ),
        out,
        signer_function=lambda manifest: sign_manifest(manifest, sealing_key, "vendor"),
        preserve_generated=True,
        generate_analysis=False,
        notarize=False,
        embed_viewer=False,
    )
    if with_approval:
        approver = Ed25519PrivateKey.generate()
        record = ReviewRecord(
            reviewed_by="dana@insurer.example",
            reviews=[
                make_approval_entry(
                    approval_id="denial-1",
                    decision="approve",
                    action="issue denial notice",
                    reason="checked against the policy",
                    approver_name="dana@insurer.example",
                    key_fingerprint_hex=_fp(approver),
                )
            ],
        )
        add_review_to_artifact(out, record, private_key=approver)
    return out


def _fp(key) -> str:
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return key_fingerprint(public.hex(), grouped=False)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_TRUSTED_APPROVERS_DIR", str(tmp_path / "trusted_approvers"))
    monkeypatch.setenv("EPI_APPROVER_KEYS_DIR", str(tmp_path / "approver_keys"))


def _export(epi: Path, out: Path) -> str:
    result = runner.invoke(app, ["export-summary", "summary", str(epi), "--out", str(out)])
    assert result.exit_code == 0, result.output
    return out.read_text(encoding="utf-8")


def test_the_summary_explains_the_decision(tmp_path):
    epi = _seal(tmp_path, with_approval=True)
    html = _export(epi, tmp_path / "summary.html")

    assert "Decision and Reasons" in html
    assert RATIONALE in html, "the principal reason must be in the document"
    assert "HO3-4.2" in html, "the rule relied on must be in the document"
    assert "claim:CLM-1001" in html, "the data relied on must be in the document"
    assert SERVED_MODEL in html, "the served model version must be in the document"
    assert "deny_claim" in html


def test_a_verified_approval_is_never_called_unsigned(tmp_path):
    epi = _seal(tmp_path, with_approval=True)
    html = _export(epi, tmp_path / "summary.html")

    assert "Signed approval by dana@insurer.example" in html
    assert _fp(Ed25519PrivateKey.generate()) not in html  # sanity: no stray key
    assert "key not pinned by this verifier" in html, "an unpinned signature is still a signature"
    assert "No approval step recorded" not in html
    assert "Reviewer recorded (not a signed approval)" not in html


def test_the_document_says_how_to_check_it(tmp_path):
    epi = _seal(tmp_path, with_approval=True)
    html = _export(epi, tmp_path / "summary.html")

    digest = hashlib.sha256(epi.read_bytes()).hexdigest()
    assert digest in html
    assert "--require-human-approval" in html
    assert "https://epilabs.org/verify" in html


def test_without_an_approval_the_summary_says_so(tmp_path):
    epi = _seal(tmp_path, with_approval=False)
    html = _export(epi, tmp_path / "summary.html")

    assert "No signed approval attached" in html
    assert RATIONALE in html
    assert "Signed approval by" not in html
