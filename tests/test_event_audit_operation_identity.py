"""Adversarial tests for the ``epi-operation/v1`` event audit.

The contract under test (docs/rfcs/operation-identity-and-event-completeness.md):

    No operation may be declared successfully paired because it happened to be
    the next event in the sequence. It must have a valid, unambiguous identity.
"""

from __future__ import annotations

import copy

from epi_cli.verify import _audit_step_sequence_completeness
from epi_core.operation_identity import (
    SCHEME,
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    STATUS_NO_EVENTS,
    STATUS_UNKNOWN,
    audit_event_sequence,
    make_correlation,
    validate_correlation,
)
from epi_core.schemas import ManifestModel
from epi_core.trust import VerificationPolicy, apply_policy, create_verification_report

# ---------------------------------------------------------------- helpers


def _corr(operation_id: str, group_id: str | None = None, attempt: int = 1) -> dict:
    return make_correlation(group_id or "opg_test", operation_id, attempt=attempt)


def _step(index: int, kind: str, content: dict | None = None, **top: object) -> dict:
    step = {"index": index, "kind": kind, "content": content or {}}
    step.update(top)
    return step


def _llm_req(index: int, op: str, group: str | None = None) -> dict:
    return _step(index, "llm.request", {"correlation": _corr(op, group)})


def _llm_res(index: int, op: str, group: str | None = None) -> dict:
    return _step(index, "llm.response", {"correlation": _corr(op, group)})


# ---------------------------------------------------------------- governed: happy path


def test_governed_sequence_complete():
    steps = [
        _llm_req(0, "op1"),
        _step(1, "llm.pre_commit", {"correlation": _corr("op1")}),
        _llm_res(2, "op1"),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_COMPLETE
    assert audit["basis"] == "operation_identity"
    assert audit["scheme"] == SCHEME
    assert audit["families"]["llm"]["status"] == STATUS_COMPLETE
    assert audit["counts"] == {"started": 1, "completed": 1, "orphaned": 0}
    assert audit["gaps"] == []


def test_governed_missing_terminal_is_incomplete():
    audit = audit_event_sequence([_llm_req(0, "op1")])
    assert audit["status"] == STATUS_INCOMPLETE
    assert len(audit["missing_terminals"]) == 1
    assert "missing a corresponding response or error" in audit["gaps"][0]


def test_governed_orphan_terminal_is_incomplete():
    audit = audit_event_sequence([_llm_res(0, "op1")])
    assert audit["status"] == STATUS_INCOMPLETE
    assert len(audit["orphan_terminals"]) == 1


def test_duplicate_operation_id_is_a_finding():
    audit = audit_event_sequence([_llm_req(0, "op1"), _llm_req(1, "op1"), _llm_res(2, "op1")])
    assert audit["status"] == STATUS_INCOMPLETE
    assert len(audit["duplicate_operations"]) == 1


def test_duplicate_terminal_is_a_finding():
    audit = audit_event_sequence([_llm_req(0, "op1"), _llm_res(1, "op1"), _llm_res(2, "op1")])
    assert audit["status"] == STATUS_INCOMPLETE
    assert len(audit["duplicate_terminals"]) == 1


def test_commitment_without_terminal_is_incomplete():
    steps = [
        _llm_req(0, "op1"),
        _step(1, "llm.pre_commit", {"correlation": _corr("op1")}),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_INCOMPLETE
    assert len(audit["unresolved_commitments"]) == 1
    assert any("committed but never executed" in g for g in audit["gaps"])


def test_commitment_without_start_is_incomplete():
    steps = [_step(0, "llm.pre_commit", {"correlation": _corr("op1")})]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_INCOMPLETE
    assert len(audit["unbound_commitments"]) == 1


def test_family_mismatch_is_incomplete():
    steps = [
        _llm_req(0, "shared"),
        _step(1, "tool.response", {"correlation": _corr("shared")}),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_INCOMPLETE
    assert len(audit["family_mismatches"]) == 1


def test_concurrent_reversed_responses_pair_by_identity():
    steps = [
        _llm_req(0, "op1"),
        _llm_req(1, "op2"),
        _llm_res(2, "op2"),  # op2 finishes first
        _llm_res(3, "op1"),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_COMPLETE
    assert audit["counts"] == {"started": 2, "completed": 2, "orphaned": 0}


def test_retry_group_connects_attempts_but_ids_stay_distinct():
    group = "opg_retry"
    steps = [
        _llm_req(0, "op1", group),
        _step(1, "llm.error", {"correlation": _corr("op1", group, attempt=1)}),
        _llm_req(2, "op2", group),
        _llm_res(3, "op2", group),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_COMPLETE
    attempts = {
        e["group_id"] for e in audit["missing_terminals"] + audit["orphan_terminals"]
    }
    assert attempts == set()
    assert audit["counts"]["completed"] == 2


# ---------------------------------------------------------------- governed: deformation


def test_uncorrelated_step_in_governed_family_fails_closed():
    """Migrating one producer must not let an unmigrated one slip through."""
    steps = [
        _llm_req(0, "op1"),
        _llm_res(1, "op1"),
        _step(2, "llm.response", {"provider": "langchain", "run_id": "r1"}),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_INCOMPLETE
    assert len(audit["ungoverned_steps"]) == 1


def test_malformed_correlation_is_treated_as_absent():
    assert validate_correlation({"scheme": SCHEME, "group_id": "", "operation_id": "x"}) is None
    assert (
        validate_correlation(
            {"scheme": "other/v9", "group_id": "g", "operation_id": "o"}
        )
        is None
    )
    assert (
        validate_correlation(
            {"scheme": SCHEME, "group_id": "g", "operation_id": "o", "attempt": 0}
        )
        is None
    )


# ---------------------------------------------------------------- cross-producer


def test_langchain_terminal_cannot_consume_openai_request_governed():
    """The defect: a foreign terminal discharging another producer's request."""
    steps = [
        _llm_req(0, "openai-op"),
        # LangChain terminal: no span_id, no correlation (unmigrated producer).
        _step(1, "llm.response", {"provider": "langchain", "run_id": "run-1"}),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_INCOMPLETE
    # The OpenAI request must still be reported missing...
    missing = [f for f in audit["missing_terminals"] if f["operation_id"] == "openai-op"]
    assert len(missing) == 1
    # ...and the LangChain event must be reported as ungoverned, not as its terminal.
    assert len(audit["ungoverned_steps"]) == 1


def test_langchain_terminal_cannot_consume_openai_request_legacy():
    """Same defect on the legacy path: ambiguity consumes nothing."""
    steps = [
        _step(0, "llm.request", {"model": "gpt-4"}, span_id="span-openai"),
        _step(1, "llm.response", {"provider": "langchain", "run_id": "run-1"}),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_UNKNOWN
    assert len(audit["ambiguous_correlations"]) == 1
    # The OpenAI request is reported only as an ambiguous-family warning.
    unpaired = [f for f in audit["missing_terminals"] if f.get("ambiguous_family")]
    assert len(unpaired) == 1
    assert audit["counts"]["completed"] == 0
    assert audit["gaps"] == []


# ---------------------------------------------------------------- legacy


def test_legacy_clean_is_never_complete():
    steps = [
        _step(0, "tool.call", {"call_id": "c1"}),
        _step(1, "tool.response", {"call_id": "c1"}),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_UNKNOWN
    assert audit["basis"] == "name_based"
    assert audit["families"]["tool"]["status"] == STATUS_UNKNOWN
    ok, gaps = _audit_step_sequence_completeness(steps)
    assert ok is True and gaps == []


def test_legacy_unambiguous_gap_still_fails():
    """Compatibility must not soften a gap the old auditor already caught."""
    steps = [
        _step(0, "tool.call", {"call_id": "c1"}),
        _step(1, "tool.call", {"call_id": "c2"}),
        _step(2, "tool.response", {"call_id": "c2"}),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_INCOMPLETE
    assert len(audit["missing_terminals"]) == 1
    ok, gaps = _audit_step_sequence_completeness(steps)
    assert ok is False
    assert len(gaps) == 1
    assert "tool.call at step 1 is missing a corresponding tool.response" == gaps[0]


def test_legacy_ambiguous_matches_are_not_resolved_by_order():
    steps = [
        _step(0, "tool.call", {"call_id": "dup"}),
        _step(1, "tool.call", {"call_id": "dup"}),
        _step(2, "tool.response", {"call_id": "dup"}),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_UNKNOWN
    assert len(audit["ambiguous_correlations"]) == 1
    assert audit["counts"]["completed"] == 0


def test_legacy_tool_name_is_a_valid_pairing_key():
    """Legacy tool records often carry no call_id; the analyzer pairs on name."""
    steps = [
        _step(0, "tool.call", {"tool": "camera.capture"}),
        _step(1, "tool.response", {"tool": "camera.capture", "status": "ok"}),
        _step(2, "tool.call", {"tool": "actuator.eject"}),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_INCOMPLETE
    assert audit["counts"] == {"started": 2, "completed": 1, "orphaned": 0}
    ok, gaps = _audit_step_sequence_completeness(steps)
    assert ok is False
    assert gaps == [
        "tool.call at step 3 is missing a corresponding tool.response"
    ]


def test_legacy_unrelated_terminal_does_not_discharge_pending():
    steps = [
        _step(0, "tool.call", {"call_id": "c1"}),
        _step(1, "tool.response", {"call_id": "zzz"}),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_INCOMPLETE
    assert len(audit["orphan_terminals"]) == 1
    assert len(audit["missing_terminals"]) == 1


def test_legacy_llm_call_alias_is_audited():
    """LangChain's ``llm.call`` used to be invisible to the auditor."""
    steps = [
        _step(0, "llm.call", {"run_id": "r1"}),
        _step(1, "llm.response", {"run_id": "r1"}),
    ]
    audit = audit_event_sequence(steps)
    assert audit["counts"]["started"] == 1
    assert "llm" in audit["families"]


def test_legacy_missing_llm_call_terminal_is_reported():
    steps = [_step(0, "llm.call", {"run_id": "r1"})]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_INCOMPLETE
    assert any("llm.call at step 1" in g for g in audit["gaps"])


def test_legacy_commitment_without_terminal_is_reported():
    steps = [
        _step(0, "llm.request", {"model": "m"}, span_id="s1"),
        _step(1, "llm.pre_commit", {"model": "m"}),
    ]
    audit = audit_event_sequence(steps)
    assert audit["status"] == STATUS_INCOMPLETE
    assert len(audit["unresolved_commitments"]) == 1
    assert any("committed but never executed" in g for g in audit["gaps"])


def test_answered_approval_is_not_a_gap_in_governed_mode():
    steps = [
        _step(
            0,
            "agent.approval.request",
            {"correlation": _corr("op1"), "action": "refund", "approval_id": "a1"},
        ),
    ]
    audit = audit_event_sequence(steps, answered_approval_ids={"a1"})
    assert audit["status"] == STATUS_COMPLETE
    assert audit["missing_terminals"] == []


# ---------------------------------------------------------------- empty / mixed


def test_empty_stream_is_not_complete():
    audit = audit_event_sequence([])
    assert audit["status"] == STATUS_NO_EVENTS
    assert audit["families"] == {}
    assert audit["gaps"] == []


def test_non_lifecycle_steps_only_is_not_complete():
    audit = audit_event_sequence([_step(0, "agent.decision", {"decision": "x"})])
    assert audit["status"] == STATUS_NO_EVENTS
    assert "agent.decision" in audit["ungoverned_kinds"]


def test_mixed_families_report_mixed_basis():
    steps = [
        _llm_req(0, "op1"),
        _llm_res(1, "op1"),
        _step(2, "tool.call", {"call_id": "c1"}),
        _step(3, "tool.response", {"call_id": "c1"}),
    ]
    audit = audit_event_sequence(steps)
    assert audit["scheme"] == "mixed"
    assert audit["basis"] == "mixed"
    assert audit["families"]["llm"]["basis"] == "operation_identity"
    assert audit["families"]["tool"]["basis"] == "name_based"
    # An unproven family never lets the artifact read as complete.
    assert audit["status"] == STATUS_UNKNOWN


def test_audit_is_deterministic():
    steps = [
        _llm_req(0, "op1"),
        _llm_req(1, "op2"),
        _llm_res(2, "op1"),
    ]
    first = audit_event_sequence(copy.deepcopy(steps))
    second = audit_event_sequence(copy.deepcopy(steps))
    assert first == second


# ---------------------------------------------------------------- policy


def _report(status: str, *, completeness_ok: bool = True, chain_present: bool = True) -> dict:
    manifest = ManifestModel(spec_version="4.12.0", file_manifest={})
    report = create_verification_report(
        integrity_ok=True,
        signature_valid=True,
        signer_name="k",
        mismatches={},
        manifest=manifest,
        completeness_ok=completeness_ok,
        chain_present=chain_present,
        event_audit={
            "status": status,
            "scheme": None,
            "basis": "name_based",
            "families": {},
            "counts": {"started": 0, "completed": 0, "orphaned": 0},
        },
    )
    report["identity"]["status"] = "KNOWN"
    return report


def test_strict_legacy_unknown_is_warn_not_pass():
    decision = apply_policy(_report(STATUS_UNKNOWN), VerificationPolicy.STRICT)["decision"]
    assert decision["status"] == "WARN"
    assert "operation identity" in decision["reason"]
    assert "scope was not checked" in decision["reason"]


def test_strict_incomplete_fails():
    report = _report(STATUS_INCOMPLETE, completeness_ok=False)
    decision = apply_policy(report, VerificationPolicy.STRICT)["decision"]
    assert decision["status"] == "FAIL"


def test_strict_no_events_passes_without_coverage_claim():
    decision = apply_policy(_report(STATUS_NO_EVENTS), VerificationPolicy.STRICT)["decision"]
    # Nothing was audited, so nothing failed; the reason disclaims coverage.
    assert decision["status"] == "PASS"
    assert "does not establish" in decision["reason"]


def test_strict_complete_passes_with_honest_wording():
    decision = apply_policy(_report(STATUS_COMPLETE), VerificationPolicy.STRICT)["decision"]
    assert decision["status"] == "PASS"
    assert "capture scope not declared" in decision["reason"]


def test_strict_chain_absence_outranks_correlation_warning():
    report = _report(STATUS_UNKNOWN, chain_present=False)
    decision = apply_policy(report, VerificationPolicy.STRICT)["decision"]
    assert decision["status"] == "FAIL"
    assert "chain absent" in decision["reason"]
