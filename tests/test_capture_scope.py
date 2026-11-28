"""Declared capture scope (P1): what the owner said, versus what was observed.

Scope is disclosure, not proof. A declared surface that was never observed means
the declaration was broader than the run; it is never a completeness failure.
The policy consequence is gated on ``SCOPE_ENFORCED_VERSION`` so artifacts sealed
today keep their verdict.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from epi_cli.main import app
from epi_core.capture_scope import (
    SCOPE_ENFORCED_VERSION,
    SCOPE_SCHEME,
    assess_capture_scope,
    is_scope_enforced,
    normalize_declaration,
    read_declaration,
    write_declaration,
)
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.trust import VerificationPolicy, apply_policy, create_verification_report
from epi_recorder.api import record

runner = CliRunner()


# ---------------------------------------------------------------- normalisation


def test_normalize_accepts_a_list_of_surfaces():
    decl = normalize_declaration(["openai.chat.completions", "langchain.tools"])
    assert decl["scheme"] == SCOPE_SCHEME
    assert decl["declaration_source"] == "caller"
    assert decl["declared"] == ["langchain.tools", "openai.chat.completions"]


def test_normalize_accepts_a_dict_with_exclusions():
    decl = normalize_declaration(
        {
            "surfaces": ["openai.chat.completions"],
            "exclusions": ["direct_http"],
            "enforcement": "gateway_fail_closed",
        }
    )
    assert decl["declared"] == ["openai.chat.completions"]
    assert decl["exclusions"] == ["direct_http"]
    assert decl["enforcement"] == "gateway_fail_closed"


@pytest.mark.parametrize("bad", [None, "", 42, [], {}, {"surfaces": []}, ["   "]])
def test_normalize_rejects_malformed(bad):
    assert normalize_declaration(bad) is None


def test_write_read_roundtrip(tmp_path):
    decl = normalize_declaration(["openai.chat.completions"])
    write_declaration(tmp_path, decl)
    assert read_declaration(tmp_path) == decl


def test_read_rejects_wrong_scheme(tmp_path):
    path = tmp_path / "artifacts" / "capture_scope.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"scheme": "other/v1", "declared": ["x"]}), encoding="utf-8")
    assert read_declaration(tmp_path) is None


# ---------------------------------------------------------------- enforcement gate


def test_scope_enforcement_is_version_gated():
    assert is_scope_enforced("4.11.2") is False
    assert is_scope_enforced(SCOPE_ENFORCED_VERSION) is True
    assert is_scope_enforced("4.12.1") is True
    assert is_scope_enforced("5.0.0") is True
    assert is_scope_enforced(None) is False
    assert is_scope_enforced("not-a-version") is False


# ---------------------------------------------------------------- assessment


def test_absent_manifest_is_unknown_not_a_failure():
    scope = assess_capture_scope(None, "4.12.0")
    assert scope["status"] == "unknown"
    assert scope["verdict"] == "unknown"
    assert scope["enforced"] is True


def test_no_declaration_is_unknown_even_with_observed_evidence():
    scope = assess_capture_scope(
        {"active_surfaces": ["sdk_wrapper:openai.chat.completions"],
         "declared_surfaces": []},
        "4.12.0",
    )
    assert scope["status"] == "unknown"
    assert scope["observed"] == ["sdk_wrapper:openai.chat.completions"]


def test_declared_and_observed_is_consistent():
    scope = assess_capture_scope(
        {
            "active_surfaces": ["sdk_wrapper:openai.chat.completions"],
            "declared_surfaces": ["openai.chat.completions"],
            "declaration_source": "caller",
            "enforcement": "self_attested",
        },
        "4.12.0",
    )
    assert scope["status"] == "declared"
    assert scope["verdict"] == "consistent_with_declaration"
    assert scope["declared_not_observed"] == []
    assert scope["observed_not_declared"] == []
    assert scope["enforced"] is True


def test_declared_but_not_observed_is_declaration_unmet():
    scope = assess_capture_scope(
        {
            "active_surfaces": ["sdk_wrapper:openai.chat.completions"],
            "declared_surfaces": ["openai.chat.completions", "langchain.tools"],
            "declaration_source": "caller",
        },
        "4.12.0",
    )
    assert scope["verdict"] == "declaration_unmet"
    assert scope["declared_not_observed"] == ["langchain.tools"]


def test_observed_but_not_declared_is_reported():
    scope = assess_capture_scope(
        {
            "active_surfaces": [
                "sdk_wrapper:openai.chat.completions",
                "sdk_wrapper:integration.langgraph",
            ],
            "declared_surfaces": ["openai.chat.completions"],
            "declaration_source": "caller",
        },
        "4.12.0",
    )
    assert scope["observed_not_declared"] == ["sdk_wrapper:integration.langgraph"]


# ---------------------------------------------------------------- policy dormancy


def _report(scope: dict) -> dict:
    report = create_verification_report(
        integrity_ok=True,
        signature_valid=True,
        signer_name="k",
        mismatches={},
        manifest=ManifestModel(spec_version="4.12.0", file_manifest={}),
        event_audit={
            "status": "complete",
            "scheme": "epi-operation/v1",
            "basis": "operation_identity",
            "families": {"llm": {"status": "complete", "basis": "operation_identity"}},
            "counts": {"started": 1, "completed": 1, "orphaned": 0},
        },
    )
    report["identity"]["status"] = "KNOWN"
    report["facts"]["capture_scope"] = scope
    return report


def test_strict_is_unchanged_before_the_gate():
    scope = assess_capture_scope(None, "4.11.2")
    decision = apply_policy(_report(scope), VerificationPolicy.STRICT)["decision"]
    assert decision["status"] == "PASS", decision


def test_strict_warns_on_missing_scope_after_the_gate():
    scope = assess_capture_scope(None, "4.12.0")
    decision = apply_policy(_report(scope), VerificationPolicy.STRICT)["decision"]
    assert decision["status"] == "WARN"
    assert "No declared capture scope" in decision["reason"]


def test_strict_warns_when_declaration_is_unmet():
    scope = assess_capture_scope(
        {
            "active_surfaces": ["sdk_wrapper:openai.chat.completions"],
            "declared_surfaces": ["langchain.tools"],
            "declaration_source": "caller",
        },
        "4.12.0",
    )
    decision = apply_policy(_report(scope), VerificationPolicy.STRICT)["decision"]
    assert decision["status"] == "WARN"
    assert "not fully observed" in decision["reason"]


def test_strict_passes_when_declaration_is_met():
    scope = assess_capture_scope(
        {
            "active_surfaces": ["sdk_wrapper:openai.chat.completions"],
            "declared_surfaces": ["openai.chat.completions"],
            "declaration_source": "caller",
        },
        "4.12.0",
    )
    decision = apply_policy(_report(scope), VerificationPolicy.STRICT)["decision"]
    assert decision["status"] == "PASS", decision


# ---------------------------------------------------------------- end to end


def _seal(tmp_path, monkeypatch, **record_kwargs):
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    path = tmp_path / "run.epi"
    with record(str(path), goal="scope", auto_sign=True, **record_kwargs) as epi:
        epi.log_step("tool.call", {"tool": "lookup", "call_id": "c1"})
        epi.log_step("tool.response", {"tool": "lookup", "call_id": "c1"})
    return path


def test_declaration_is_sealed_and_reported(tmp_path, monkeypatch):
    path = _seal(
        tmp_path, monkeypatch, capture_scope=["openai.chat.completions"]
    )
    capture = EPIContainer.read_member_json(path, "artifacts/manifest.json")
    assert capture["scope_scheme"] == SCOPE_SCHEME
    assert capture["declared_surfaces"] == ["openai.chat.completions"]
    assert capture["declaration_source"] == "caller"
    # The declaration is itself in the archive and hash-chained.
    assert EPIContainer.read_member_json(path, "artifacts/capture_scope.json")[
        "declared"
    ] == ["openai.chat.completions"]


def test_artifact_without_declaration_reports_unknown(tmp_path, monkeypatch):
    path = _seal(tmp_path, monkeypatch)
    capture = EPIContainer.read_member_json(path, "artifacts/manifest.json")
    assert capture["declared_surfaces"] == []
    assert capture["declaration_source"] == "none"


def test_verify_json_exposes_capture_scope(tmp_path, monkeypatch):
    path = _seal(tmp_path, monkeypatch, capture_scope=["openai.chat.completions"])
    result = runner.invoke(app, ["verify", str(path), "--offline", "--json"])
    report = json.loads(result.stdout)
    scope = report["facts"]["capture_scope"]
    assert scope["status"] == "declared"
    assert scope["declared"] == ["openai.chat.completions"]
    assert scope["enforced"] is False  # 4.11.2: data reported, policy dormant
