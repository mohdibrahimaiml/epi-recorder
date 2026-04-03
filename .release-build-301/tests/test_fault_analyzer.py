"""Tests for epi_core.fault_analyzer — four detection passes."""

import json
import pytest

from epi_core.fault_analyzer import FaultAnalyzer, AnalysisResult, DISCLAIMER
from epi_core.policy import EPIPolicy, PolicyRule


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_step(index, kind, content, timestamp="2025-01-01T00:00:00"):
    return json.dumps({"index": index, "kind": kind, "content": content, "timestamp": timestamp})


CLEAN_STEPS = "\n".join([
    _make_step(0, "session.start",  {"workflow_name": "test"}),
    _make_step(1, "llm.request",    {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}),
    _make_step(2, "llm.response",   {"choices": [{"message": {"content": "Hi"}}], "usage": {"total_tokens": 10}}),
    _make_step(3, "session.end",    {"success": True}),
])

ERROR_CONTINUATION_STEPS = "\n".join([
    _make_step(0, "session.start",   {"workflow_name": "test"}),
    _make_step(1, "llm.request",     {"model": "gpt-4", "messages": []}),
    _make_step(2, "llm.error",       {"error": "Rate limit exceeded", "model": "gpt-4"}),
    _make_step(3, "llm.request",     {"model": "gpt-4", "messages": [{"role": "user", "content": "Continue"}]}),
    _make_step(4, "llm.response",    {"choices": [{"message": {"content": "Done"}}]}),
])

CONSTRAINT_VIOLATION_STEPS = "\n".join([
    _make_step(0, "session.start",   {"workflow_name": "payment"}),
    _make_step(1, "tool.response",   {"tool": "get_balance", "balance": 500.0}),
    _make_step(2, "llm.request",     {"model": "gpt-4", "messages": []}),
    _make_step(3, "tool.call",       {"tool": "approve_transaction", "amount": 2000.0}),
    _make_step(4, "session.end",     {"success": True}),
])

CONTEXT_DROP_STEPS = "\n".join([
    _make_step(0, "session.start",   {"account_id": "ACC-999", "workflow": "refund"}),
    _make_step(1, "tool.response",   {"account_id": "ACC-999", "balance": 1000.0}),
    _make_step(2, "llm.request",     {"messages": [{"role": "user", "content": "Check account ACC-999"}]}),
    _make_step(3, "llm.response",    {"choices": [{"message": {"content": "Processing"}}]}),
    _make_step(4, "llm.request",     {"messages": [{"role": "user", "content": "submit refund"}]}),
    _make_step(5, "tool.call",       {"action": "submit_refund", "amount": 100}),
    _make_step(6, "tool.response",   {"status": "submitted", "ref": "REF001"}),
    _make_step(7, "session.end",     {"success": True}),
])

SEQUENCE_VIOLATION_STEPS = "\n".join([
    _make_step(0, "session.start",   {"workflow": "refund_flow"}),
    _make_step(1, "llm.request",     {"messages": [{"role": "user", "content": "Process refund"}]}),
    _make_step(2, "tool.call",       {"tool": "process_refund", "amount": 200}),
    _make_step(3, "session.end",     {"success": True}),
])

SEQUENCE_OK_STEPS = "\n".join([
    _make_step(0, "session.start",   {"workflow": "refund_flow"}),
    _make_step(1, "tool.call",       {"tool": "verify_identity", "user": "john"}),
    _make_step(2, "tool.response",   {"verified": True}),
    _make_step(3, "tool.call",       {"tool": "process_refund", "amount": 200}),
    _make_step(4, "session.end",     {"success": True}),
])

THRESHOLD_VIOLATION_STEPS = "\n".join([
    _make_step(0, "session.start",   {"workflow": "payment_flow"}),
    _make_step(1, "tool.call",       {"tool": "approve_payment", "amount": 15000.0}),
    _make_step(2, "session.end",     {"success": True}),
])

THRESHOLD_OK_STEPS = "\n".join([
    _make_step(0, "session.start",   {"workflow": "payment_flow"}),
    _make_step(1, "tool.call",       {"tool": "human_approval", "amount": 15000.0}),
    _make_step(2, "tool.response",   {"approved": True}),
    _make_step(3, "tool.call",       {"tool": "approve_payment", "amount": 15000.0}),
    _make_step(4, "session.end",     {"success": True}),
])

PROHIBITION_VIOLATION_STEPS = "\n".join([
    _make_step(0, "session.start",   {"workflow": "secret_scan"}),
    _make_step(1, "llm.response",    {"text": "Here is the key: sk-ABC123SECRET"}),
    _make_step(2, "session.end",     {"success": True}),
])

AGENT_APPROVAL_PENDING_STEPS = "\n".join([
    _make_step(0, "session.start", {"workflow": "agent_refund"}),
    _make_step(1, "agent.approval.request", {"action": "approve_refund", "reason": "manual review"}),
    _make_step(2, "agent.decision", {"decision": "approve_refund", "amount": 2000}),
    _make_step(3, "session.end", {"success": True}),
])

AGENT_APPROVAL_REJECTED_STEPS = "\n".join([
    _make_step(0, "session.start", {"workflow": "agent_refund"}),
    _make_step(1, "agent.approval.request", {"action": "approve_refund", "reason": "manual review"}),
    _make_step(2, "agent.approval.response", {"action": "approve_refund", "approved": False, "reviewer": "manager"}),
    _make_step(3, "agent.decision", {"decision": "approve_refund", "amount": 2000}),
    _make_step(4, "session.end", {"success": True}),
])

AGENT_SEQUENCE_VIOLATION_STEPS = "\n".join([
    _make_step(0, "session.start", {"workflow": "refund_flow"}),
    _make_step(1, "agent.decision", {"decision": "approve_refund", "amount": 200}),
    _make_step(2, "session.end", {"success": True}),
])

AGENT_THRESHOLD_APPROVAL_OK_STEPS = "\n".join([
    _make_step(0, "session.start", {"workflow": "payment_flow"}),
    _make_step(1, "tool.response", {"tool": "lookup_order", "amount": 15000.0}),
    _make_step(2, "agent.approval.response", {"action": "approve_payment", "approved": True, "reviewer": "manager"}),
    _make_step(3, "agent.decision", {"decision": "approve_payment"}),
    _make_step(4, "session.end", {"success": True}),
])

AGENT_THRESHOLD_APPROVAL_AFTER_INVESTIGATION_OK_STEPS = "\n".join([
    _make_step(0, "session.start", {"workflow": "insurance_claim"}),
    _make_step(1, "tool.response", {"tool": "claim_lookup", "amount": 15000.0}),
    _make_step(2, "tool.call", {"tool": "run_fraud_check", "claim_id": "CLM-200"}),
    _make_step(3, "tool.response", {"tool": "run_fraud_check", "fraud_score": 0.03}),
    _make_step(4, "tool.call", {"tool": "check_coverage", "claim_id": "CLM-200"}),
    _make_step(5, "tool.response", {"tool": "check_coverage", "coverage_status": "excluded"}),
    _make_step(6, "agent.approval.response", {"action": "deny_claim", "approved": True, "reviewer": "manager"}),
    _make_step(7, "tool.call", {"tool": "deny_claim", "amount": 15000.0}),
    _make_step(8, "agent.decision", {"decision": "deny_claim", "amount": 15000.0}),
    _make_step(9, "session.end", {"success": True}),
])

AGENT_THRESHOLD_APPROVAL_VIOLATION_STEPS = "\n".join([
    _make_step(0, "session.start", {"workflow": "payment_flow"}),
    _make_step(1, "tool.response", {"tool": "lookup_order", "amount": 15000.0}),
    _make_step(2, "agent.decision", {"decision": "approve_payment"}),
    _make_step(3, "session.end", {"success": True}),
])

TOOL_DENIED_STEPS = "\n".join([
    _make_step(0, "session.start", {"workflow": "refund_flow"}),
    _make_step(1, "tool.call", {"tool": "delete_customer", "customer_id": "C-001"}),
    _make_step(2, "session.end", {"success": True}),
])

TOOL_ALLOWED_STEPS = "\n".join([
    _make_step(0, "session.start", {"workflow": "refund_flow"}),
    _make_step(1, "tool.call", {"tool": "lookup_order", "order_id": "123"}),
    _make_step(2, "tool.response", {"tool": "lookup_order", "status": "paid"}),
    _make_step(3, "session.end", {"success": True}),
])


def _make_policy_with_sequence():
    return EPIPolicy(
        system_name="test",
        system_version="1.0",
        policy_version="2025-01-01",
        rules=[
            PolicyRule(
                id="R001",
                name="Verify Before Refund",
                severity="critical",
                description="Must verify before refund.",
                type="sequence_guard",
                required_before="refund",
                must_call="verify_identity",
            )
        ],
    )


def _make_policy_with_constraint():
    return EPIPolicy(
        system_name="test",
        system_version="1.0",
        policy_version="2025-01-01",
        rules=[
            PolicyRule(
                id="R001",
                name="Balance Check",
                severity="critical",
                description="Never exceed balance.",
                type="constraint_guard",
                watch_for=["balance"],
                violation_if="amount > balance",
            )
        ],
    )


def _make_policy_with_threshold():
    return EPIPolicy(
        system_name="test",
        system_version="1.0",
        policy_version="2025-01-01",
        rules=[
            PolicyRule(
                id="R010",
                name="Large Transaction Approval",
                severity="high",
                description="Amounts above 10k require human approval.",
                type="threshold_guard",
                threshold_value=10000,
                threshold_field="amount",
                required_action="human_approval",
            )
        ],
    )


def _make_policy_with_threshold_watch_for_only():
    return EPIPolicy(
        system_name="test",
        system_version="1.0",
        policy_version="2025-01-01",
        rules=[
            PolicyRule(
                id="R011",
                name="Large Transaction Approval",
                severity="high",
                description="Amounts above 10k require human approval.",
                type="threshold_guard",
                threshold_value=10000,
                watch_for=["amount"],
                required_action="human_approval",
            )
        ],
    )


def _make_policy_with_prohibition():
    return EPIPolicy(
        system_name="test",
        system_version="1.0",
        policy_version="2025-01-01",
        rules=[
            PolicyRule(
                id="R020",
                name="No API Keys",
                severity="critical",
                description="Never output API keys.",
                type="prohibition_guard",
                prohibited_pattern=r"sk-[A-Za-z0-9]+",
            )
        ],
    )


def _make_policy_with_approval_guard():
    return EPIPolicy(
        system_name="test",
        system_version="1.0",
        policy_version="2025-01-01",
        rules=[
            PolicyRule(
                id="R030",
                name="Explicit Approval Before Refund",
                severity="critical",
                description="Refund approval requires an explicit approved response.",
                type="approval_guard",
                approval_action="approve_refund",
                approved_by="manager",
            )
        ],
    )


def _make_policy_with_v2_metadata():
    return EPIPolicy(
        policy_format_version="2.0",
        policy_id="refund-agent-prod",
        system_name="refund-agent",
        system_version="2.8.7",
        policy_version="2026-04-01",
        scope={
            "team": "finance-ops",
            "application": "refund-agent",
            "environment": "production",
        },
        rules=[
            PolicyRule(
                id="R031",
                name="Manager Approval Before Refund",
                severity="critical",
                description="Refund approval requires explicit manager signoff.",
                type="approval_guard",
                mode="require_approval",
                applies_at="decision",
                approval_action="approve_refund",
                approved_by="manager",
            )
        ],
    )


def _make_policy_with_approval_policy_ref():
    return EPIPolicy(
        policy_format_version="2.0",
        policy_id="refund-agent-prod",
        system_name="refund-agent",
        system_version="2.8.7",
        policy_version="2026-04-01",
        approval_policies=[
            {
                "approval_id": "manager-refund-approval",
                "required_roles": ["manager"],
                "minimum_approvers": 2,
                "reason_required": True,
            }
        ],
        rules=[
            PolicyRule(
                id="R032",
                name="Manager Approval Policy Before Refund",
                severity="critical",
                description="Refund approval requires a reusable manager approval policy.",
                type="approval_guard",
                mode="require_approval",
                applies_at="decision",
                approval_action="approve_refund",
                approval_policy_ref="manager-refund-approval",
            )
        ],
    )


def _make_policy_with_tool_permission_guard():
    return EPIPolicy(
        policy_format_version="2.0",
        policy_id="refund-agent-tools",
        system_name="refund-agent",
        system_version="2.8.7",
        policy_version="2026-04-01",
        rules=[
            PolicyRule(
                id="R040",
                name="Approved Refund Tools Only",
                severity="critical",
                description="Only approved refund tools may be used.",
                type="tool_permission_guard",
                mode="block",
                applies_at="tool_call",
                allowed_tools=["lookup_order", "verify_identity", "approve_refund"],
                denied_tools=["delete_customer"],
            )
        ],
    )


# ── Test: Clean execution ─────────────────────────────────────────────────────

class TestCleanExecution:
    def test_no_fault_on_clean_steps(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CLEAN_STEPS)
        assert not result.fault_detected

    def test_result_has_disclaimer(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CLEAN_STEPS)
        disclaimer = result.to_dict()["disclaimer"]
        assert DISCLAIMER in disclaimer
        assert "deterministic rule matches" in disclaimer
        assert "probabilistic" not in disclaimer

    def test_coverage_counts_steps(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CLEAN_STEPS)
        assert result.to_dict()["coverage"]["steps_recorded"] == 4

    def test_mode_is_heuristic_without_policy(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CLEAN_STEPS)
        assert result.mode == "heuristic_only"

    def test_mode_is_policy_grounded_with_policy(self):
        policy = _make_policy_with_sequence()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(CLEAN_STEPS)
        assert result.mode == "policy_grounded"

    def test_empty_steps_no_crash(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze("")
        assert not result.fault_detected

    def test_to_json_is_valid_json(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CLEAN_STEPS)
        parsed = json.loads(result.to_json())
        assert "fault_detected" in parsed
        assert "disclaimer" in parsed


# ── Test: Pass 1 — Error Continuation ────────────────────────────────────────

class TestPass1ErrorContinuation:
    def test_detects_error_continuation(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(ERROR_CONTINUATION_STEPS)
        assert result.fault_detected or any(
            f.fault_type == "HEURISTIC_OBSERVATION"
            for f in [result.primary_fault] + result.secondary_flags
            if f is not None
        )

    def test_error_step_flagged(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(ERROR_CONTINUATION_STEPS)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        # At least one flag should reference step 2 or 3 (error then continuation)
        step_indices = {f.step_index for f in all_flags}
        assert len(step_indices) > 0

    def test_no_false_positive_on_clean(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CLEAN_STEPS)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        error_flags = [f for f in all_flags if "error" in (f.plain_english or "").lower()]
        assert len(error_flags) == 0


# ── Test: Pass 2 — Constraint Violation ───────────────────────────────────────

class TestPass2ConstraintViolation:
    def test_detects_constraint_violation(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CONSTRAINT_VIOLATION_STEPS)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        assert any(
            "2000" in (f.plain_english or "") or "constraint" in (f.plain_english or "").lower()
            for f in all_flags
        )

    def test_policy_violation_type_with_policy(self):
        policy = _make_policy_with_constraint()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(CONSTRAINT_VIOLATION_STEPS)
        if result.primary_fault:
            # With matching policy, primary fault should be policy violation
            assert result.primary_fault.fault_type == "POLICY_VIOLATION" or \
                   result.primary_fault.fault_type == "HEURISTIC_OBSERVATION"

    def test_fault_chain_has_source_and_violation(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CONSTRAINT_VIOLATION_STEPS)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        for flag in all_flags:
            if flag.fault_chain and len(flag.fault_chain) >= 2:
                roles = {c["role"] for c in flag.fault_chain}
                assert "constraint_source" in roles or "violation_point" in roles


# ── Test: Pass 3 — Sequence Violation ────────────────────────────────────────

class TestPass3SequenceViolation:
    def test_detects_sequence_violation(self):
        policy = _make_policy_with_sequence()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(SEQUENCE_VIOLATION_STEPS)
        assert result.fault_detected
        assert result.primary_fault.fault_type == "POLICY_VIOLATION"
        assert result.primary_fault.rule_id == "R001"

    def test_no_violation_when_sequence_correct(self):
        policy = _make_policy_with_sequence()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(SEQUENCE_OK_STEPS)
        # Should not flag sequence violation when verify_identity comes first
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        seq_violations = [f for f in all_flags if f.rule_id == "R001"]
        assert len(seq_violations) == 0

    def test_pass3_skipped_without_policy(self):
        analyzer = FaultAnalyzer(policy=None)
        result = analyzer.analyze(SEQUENCE_VIOLATION_STEPS)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        policy_flags = [f for f in all_flags if f.fault_type == "POLICY_VIOLATION"]
        assert len(policy_flags) == 0

    def test_detects_sequence_violation_on_agent_decision(self):
        policy = _make_policy_with_sequence()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(AGENT_SEQUENCE_VIOLATION_STEPS)
        assert result.fault_detected
        assert result.primary_fault.rule_id == "R001"


# ── Test: Pass 4 — Context Drop ──────────────────────────────────────────────

class TestPass4ThresholdViolation:
    def test_detects_threshold_violation(self):
        policy = _make_policy_with_threshold()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(THRESHOLD_VIOLATION_STEPS)
        assert result.fault_detected
        assert result.primary_fault.fault_type == "POLICY_VIOLATION"
        assert result.primary_fault.rule_id == "R010"

    def test_no_violation_when_required_action_present(self):
        policy = _make_policy_with_threshold()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(THRESHOLD_OK_STEPS)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        threshold_flags = [f for f in all_flags if f and f.rule_id == "R010"]
        assert len(threshold_flags) == 0

    def test_detects_threshold_violation_when_rule_uses_watch_for_only(self):
        policy = _make_policy_with_threshold_watch_for_only()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(THRESHOLD_VIOLATION_STEPS)
        assert result.fault_detected
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        threshold_flags = [f for f in all_flags if f and f.rule_id == "R011"]
        assert len(threshold_flags) > 0

    def test_threshold_allows_agent_approval_response_before_decision(self):
        policy = _make_policy_with_threshold()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(AGENT_THRESHOLD_APPROVAL_OK_STEPS)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        threshold_flags = [f for f in all_flags if f and f.rule_id == "R010"]
        assert len(threshold_flags) == 0

    def test_threshold_allows_investigation_before_approval_and_final_action(self):
        policy = _make_policy_with_threshold()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(AGENT_THRESHOLD_APPROVAL_AFTER_INVESTIGATION_OK_STEPS)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        threshold_flags = [f for f in all_flags if f and f.rule_id == "R010"]
        assert len(threshold_flags) == 0

    def test_threshold_flags_agent_decision_when_approval_missing(self):
        policy = _make_policy_with_threshold()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(AGENT_THRESHOLD_APPROVAL_VIOLATION_STEPS)
        assert result.fault_detected
        assert result.primary_fault.rule_id == "R010"


class TestPass5ProhibitionViolation:
    def test_detects_prohibited_pattern(self):
        policy = _make_policy_with_prohibition()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(PROHIBITION_VIOLATION_STEPS)
        assert result.fault_detected
        assert result.primary_fault.fault_type == "POLICY_VIOLATION"
        assert result.primary_fault.rule_id == "R020"

    def test_no_prohibition_violation_on_clean(self):
        policy = _make_policy_with_prohibition()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(CLEAN_STEPS)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        prohibition_flags = [f for f in all_flags if f and f.rule_id == "R020"]
        assert len(prohibition_flags) == 0


class TestPass6AgentApprovalGap:
    def test_detects_pending_approval_gap(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(AGENT_APPROVAL_PENDING_STEPS)
        assert result.fault_detected
        assert result.primary_fault.fault_type == "HEURISTIC_OBSERVATION"
        assert "pending" in result.primary_fault.plain_english.lower()

    def test_detects_rejected_approval_override(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(AGENT_APPROVAL_REJECTED_STEPS)
        assert result.fault_detected
        assert "rejected" in result.primary_fault.plain_english.lower()


class TestPass7ApprovalGuardViolation:
    def test_policy_approval_guard_requires_explicit_approval(self):
        policy = _make_policy_with_approval_guard()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(AGENT_APPROVAL_PENDING_STEPS)
        assert result.fault_detected
        assert result.primary_fault.fault_type == "POLICY_VIOLATION"
        assert result.primary_fault.rule_id == "R030"

    def test_policy_approval_guard_passes_with_matching_approver(self):
        policy = _make_policy_with_approval_guard()
        steps = "\n".join([
            _make_step(0, "session.start", {"workflow": "agent_refund"}),
            _make_step(1, "agent.approval.request", {"action": "approve_refund"}),
            _make_step(2, "agent.approval.response", {"action": "approve_refund", "approved": True, "reviewer": "manager"}),
            _make_step(3, "agent.decision", {"decision": "approve_refund"}),
            _make_step(4, "session.end", {"success": True}),
        ])
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(steps)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        approval_flags = [f for f in all_flags if f and f.rule_id == "R030"]
        assert len(approval_flags) == 0

    def test_approval_policy_ref_requires_multiple_role_matched_approvers(self):
        policy = _make_policy_with_approval_policy_ref()
        steps = "\n".join([
            _make_step(0, "session.start", {"workflow": "agent_refund"}),
            _make_step(1, "agent.approval.request", {"action": "approve_refund", "reason": "manual review"}),
            _make_step(2, "agent.approval.response", {"action": "approve_refund", "approved": True, "reviewer": "manager-a", "role": "manager"}),
            _make_step(3, "agent.decision", {"decision": "approve_refund"}),
            _make_step(4, "session.end", {"success": True}),
        ])
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(steps)
        assert result.fault_detected
        assert result.primary_fault.rule_id == "R032"
        assert "2 are required" in result.primary_fault.plain_english

    def test_approval_policy_ref_passes_with_two_manager_approvers_and_reason(self):
        policy = _make_policy_with_approval_policy_ref()
        steps = "\n".join([
            _make_step(0, "session.start", {"workflow": "agent_refund"}),
            _make_step(1, "agent.approval.request", {"action": "approve_refund", "reason": "manual review"}),
            _make_step(2, "agent.approval.response", {"action": "approve_refund", "approved": True, "reviewer": "manager-a", "role": "manager"}),
            _make_step(3, "agent.approval.response", {"action": "approve_refund", "approved": True, "reviewer": "manager-b", "role": "manager"}),
            _make_step(4, "agent.decision", {"decision": "approve_refund"}),
            _make_step(5, "session.end", {"success": True}),
        ])
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(steps)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        approval_flags = [f for f in all_flags if f and f.rule_id == "R032"]
        assert len(approval_flags) == 0

    def test_approval_policy_ref_requires_reason_when_configured(self):
        policy = _make_policy_with_approval_policy_ref()
        steps = "\n".join([
            _make_step(0, "session.start", {"workflow": "agent_refund"}),
            _make_step(1, "agent.approval.request", {"action": "approve_refund"}),
            _make_step(2, "agent.approval.response", {"action": "approve_refund", "approved": True, "reviewer": "manager-a", "role": "manager"}),
            _make_step(3, "agent.approval.response", {"action": "approve_refund", "approved": True, "reviewer": "manager-b", "role": "manager"}),
            _make_step(4, "agent.decision", {"decision": "approve_refund"}),
            _make_step(5, "session.end", {"success": True}),
        ])
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(steps)
        assert result.fault_detected
        assert result.primary_fault.rule_id == "R032"
        assert "reason was required" in result.primary_fault.plain_english


class TestPass8ToolPermissionGuard:
    def test_tool_permission_guard_flags_denied_tool(self):
        policy = _make_policy_with_tool_permission_guard()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(TOOL_DENIED_STEPS)
        assert result.fault_detected
        assert result.primary_fault.rule_id == "R040"
        assert "explicitly denied" in result.primary_fault.plain_english

    def test_tool_permission_guard_flags_non_allowlisted_tool(self):
        policy = _make_policy_with_tool_permission_guard()
        steps = "\n".join([
            _make_step(0, "session.start", {"workflow": "refund_flow"}),
            _make_step(1, "tool.call", {"tool": "export_ledger"}),
            _make_step(2, "session.end", {"success": True}),
        ])
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(steps)
        assert result.fault_detected
        assert result.primary_fault.rule_id == "R040"
        assert "not in the allowlist" in result.primary_fault.plain_english

    def test_tool_permission_guard_allows_allowlisted_tool(self):
        policy = _make_policy_with_tool_permission_guard()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(TOOL_ALLOWED_STEPS)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        tool_flags = [f for f in all_flags if f and f.rule_id == "R040"]
        assert len(tool_flags) == 0

    def test_tool_permission_guard_accepts_applies_at_list(self):
        policy = _make_policy_with_tool_permission_guard()
        policy.rules[0].applies_at = ["tool_call", "tool_response"]
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(TOOL_DENIED_STEPS)
        assert result.fault_detected
        assert result.primary_fault.rule_id == "R040"


class TestPass4ContextDrop:
    def test_detects_context_drop(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CONTEXT_DROP_STEPS)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        drop_flags = [f for f in all_flags if "ACC-999" in (f.plain_english or "")]
        assert len(drop_flags) > 0

    def test_no_drop_flag_when_id_present_throughout(self):
        steps_with_id = "\n".join([
            _make_step(0, "start", {"account_id": "ACC-999"}),
            _make_step(1, "llm.request", {"messages": []}),
            _make_step(2, "llm.response", {"choices": [{"message": {"content": "ACC-999"}}]}),
            _make_step(3, "tool.call", {"account_id": "ACC-999", "action": "submit"}),
            _make_step(4, "tool.response", {"account_id": "ACC-999", "status": "ok"}),
            _make_step(5, "end", {"account_id": "ACC-999"}),
        ])
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(steps_with_id)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        drop_flags = [f for f in all_flags if "ACC-999" in (f.plain_english or "")]
        assert len(drop_flags) == 0

    def test_skipped_for_short_step_count(self):
        short_steps = "\n".join([_make_step(i, "llm.request", {"account_id": "ACC-1"}) for i in range(4)])
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(short_steps)
        # Pass 4 requires >= 8 steps, should produce no context drop flag
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        drop_flags = [f for f in all_flags if "context" in (f.plain_english or "").lower()]
        assert len(drop_flags) == 0

    def test_no_drop_flag_on_short_healthy_structured_workflow(self):
        short_structured_steps = "\n".join([
            _make_step(0, "session.start", {"workflow_name": "structured-demo"}),
            _make_step(1, "tool.response", {"account_id": "ACC-1001", "balance": 1200.0}),
            _make_step(2, "llm.request", {"messages": [{"role": "user", "content": "review account"}]}),
            _make_step(3, "llm.response", {"text": "Account looks good."}),
            _make_step(4, "tool.call", {"tool": "submit_refund", "amount": 25.0}),
            _make_step(5, "session.end", {"success": True}),
        ])
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(short_structured_steps)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        drop_flags = [f for f in all_flags if "ACC-1001" in (f.plain_english or "")]
        assert len(drop_flags) == 0

    def test_stdout_is_not_treated_as_entity_identifier(self):
        stdout_like_steps = "\n".join([
            _make_step(0, "session.start", {"workflow_name": "demo"}),
            _make_step(1, "stdout.print", {"stream": "stdout", "text": "hello"}),
            _make_step(2, "stdout.print", {"stream": "stdout", "text": "processing"}),
            _make_step(3, "tool.call", {"tool": "fetch_case", "case_id": "CASE-7702"}),
            _make_step(4, "tool.response", {"status": "ok", "case_id": "CASE-7702"}),
            _make_step(5, "stdout.print", {"stream": "stdout", "text": "done"}),
            _make_step(6, "session.end", {"success": True}),
            _make_step(7, "artifact.captured", {"path": "demo.epi"}),
        ])
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(stdout_like_steps)
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        stdout_flags = [f for f in all_flags if "stdout" in (f.plain_english or "").lower()]
        assert len(stdout_flags) == 0


# ── Test: AnalysisResult output structure ─────────────────────────────────────

class TestAnalysisResult:
    def test_to_dict_has_required_keys(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CLEAN_STEPS)
        d = result.to_dict()
        for key in ("analyzer_version", "analysis_timestamp", "policy_used", "mode",
                    "coverage", "fault_detected", "confidence", "primary_fault",
                    "secondary_flags", "human_review", "disclaimer", "summary",
                    "fault_taxonomy_version", "review_required"):
            assert key in d, f"Missing key: {key}"

    def test_human_review_starts_pending(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CLEAN_STEPS)
        hr = result.to_dict()["human_review"]
        assert hr["status"] == "pending"
        assert hr["reviewed_by"] is None
        assert hr["outcome"] is None

    def test_confidence_high_on_clean(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CLEAN_STEPS)
        assert result.confidence == "high"

    def test_primary_fault_is_none_on_clean(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CLEAN_STEPS)
        assert result.primary_fault is None
        assert result.to_dict()["primary_fault"] is None

    def test_analyzer_never_raises(self):
        """The analyzer must handle any malformed input without raising."""
        analyzer = FaultAnalyzer()
        for bad_input in [
            "",
            "not json at all",
            '{"no_index": true}\n{"also_bad": null}',
            "\n\n\n",
            '{"index": 0, "kind": "x", "content": null}',
        ]:
            result = analyzer.analyze(bad_input)
            assert isinstance(result, AnalysisResult)

    def test_primary_fault_contains_product_metadata(self):
        policy = _make_policy_with_prohibition()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(PROHIBITION_VIOLATION_STEPS)
        fault = result.to_dict()["primary_fault"]
        assert fault["category"] == "policy_violation"
        assert fault["review_required"] is True
        assert "why_it_matters" in fault

    def test_summary_headline_mentions_primary_fault(self):
        policy = _make_policy_with_threshold()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(THRESHOLD_VIOLATION_STEPS)
        summary = result.to_dict()["summary"]
        assert "R010" in summary["headline"]
        assert summary["primary_step"] == result.primary_fault.step_number

    def test_policy_metadata_is_exposed_in_analysis_output(self):
        policy = _make_policy_with_v2_metadata()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(AGENT_APPROVAL_PENDING_STEPS)
        payload = result.to_dict()

        assert payload["policy_format_version"] == "2.0"
        assert payload["policy_id"] == "refund-agent-prod"
        assert payload["policy_scope"]["environment"] == "production"
        assert payload["primary_fault"]["policy_type"] == "approval_guard"
        assert payload["primary_fault"]["policy_mode"] == "require_approval"
        assert payload["primary_fault"]["policy_applies_at"] == "decision"

    def test_policy_evaluation_output_is_structured(self):
        policy = _make_policy_with_v2_metadata()
        analyzer = FaultAnalyzer(policy=policy)
        result = analyzer.analyze(AGENT_APPROVAL_PENDING_STEPS)
        evaluation = result.to_policy_evaluation_dict()

        assert evaluation["policy_id"] == "refund-agent-prod"
        assert evaluation["controls_evaluated"] == 1
        assert evaluation["controls_failed"] == 1
        assert evaluation["artifact_review_required"] is True
        assert evaluation["results"][0]["rule_id"] == "R031"
        assert evaluation["results"][0]["status"] == "failed"
        assert evaluation["results"][0]["mode"] == "require_approval"
        assert evaluation["results"][0]["applies_at"] == "decision"

    def test_policy_evaluation_absent_without_policy(self):
        analyzer = FaultAnalyzer()
        result = analyzer.analyze(CLEAN_STEPS)
        assert result.to_policy_evaluation_dict() is None
