"""Regression tests: Pass 1 / Pass 2 must not flag ordinary agent content.

Two false-positive classes were fixed in analyzer 1.1.0:

  Pass 1 (Error Continuation) scanned the whole step JSON for the word
  "error", so a user prompt like "how do I fix this error?" or a tool response
  carrying ``{"errors": 0}`` looked like a failed call that the agent ignored.

  Pass 2 (Constraint Violation) compared every numeric field containing a
  broad constraint keyword ("max", "limit", "allowed") against every later
  committed amount, so ``max_tokens: 100`` bounded ``amount: 250`` and a
  stale balance superseded a refreshed one.

These tests pin the true positives as well as the removals.
"""

import json

from epi_core.fault_analyzer import FaultAnalyzer
from epi_core.policy import EPIPolicy, PolicyRule


def _make_step(index, kind, content, timestamp="2025-01-01T00:00:00"):
    return json.dumps({"index": index, "kind": kind, "content": content, "timestamp": timestamp})


def _steps(*rows):
    return "\n".join(_make_step(i, kind, content) for i, (kind, content) in enumerate(rows))


def _all_flags(result):
    return ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags


def _flags_for(result, rule_id):
    return [flag for flag in _all_flags(result) if flag.rule_id == rule_id]


# ── Pass 1: error signals ─────────────────────────────────────────────────────


class TestPass1ErrorSignals:
    def test_prompt_mentioning_error_is_not_a_failure(self):
        steps = _steps(
            ("session.start", {"workflow_name": "support_bot"}),
            ("llm.request", {"model": "gpt-4o", "messages": [
                {"role": "user", "content": "How do I fix a syntax error in Python?"},
            ]}),
            ("llm.response", {"choices": [{"message": {
                "content": "Check the traceback and the line number.",
            }}]}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer().analyze(steps)
        assert _flags_for(result, "P1") == []

    def test_null_error_field_is_not_a_failure(self):
        steps = _steps(
            ("session.start", {"workflow_name": "lookup"}),
            ("tool.response", {"tool": "lookup_account", "error": None, "status": "ok"}),
            ("tool.response", {"tool": "lookup_account", "error": "", "balance": 100}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer().analyze(steps)
        assert _flags_for(result, "P1") == []

    def test_zero_error_bookkeeping_is_not_a_failure(self):
        steps = _steps(
            ("session.start", {"workflow_name": "scrubber"}),
            ("tool.response", {"tool": "scan", "errors": 0, "failed": 0, "error_count": 0}),
            ("tool.response", {"tool": "scan", "text": "completed with 0 errors"}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer().analyze(steps)
        assert _flags_for(result, "P1") == []

    def test_real_tool_error_is_still_flagged_when_ignored(self):
        steps = _steps(
            ("session.start", {"workflow_name": "charger"}),
            ("tool.response", {"tool": "charge_card", "error": "connection refused"}),
            ("tool.call", {"tool": "charge_card", "amount": 40}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer().analyze(steps)
        flags = _flags_for(result, "P1")
        assert len(flags) == 1
        assert flags[0].fault_type == "ERROR_CONTINUATION"
        assert flags[0].step_index == 1

    def test_http_failure_status_is_still_flagged(self):
        steps = _steps(
            ("session.start", {"workflow_name": "gateway"}),
            ("http.response", {"status_code": 503, "body": "unavailable"}),
            ("tool.call", {"tool": "charge_card", "amount": 40}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer().analyze(steps)
        assert len(_flags_for(result, "P1")) == 1


# ── Pass 2: constraint boundaries ─────────────────────────────────────────────


class TestPass2ConstraintBoundaries:
    def test_true_positive_balance_still_flagged(self):
        steps = _steps(
            ("session.start", {"workflow_name": "payment"}),
            ("tool.response", {"tool": "get_balance", "balance": 500.0}),
            ("tool.call", {"tool": "approve_transfer", "amount": 2000.0}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer().analyze(steps)
        flags = _flags_for(result, "P2")
        assert len(flags) == 1
        assert flags[0].fault_type == "CONSTRAINT_VIOLATION"
        assert flags[0].step_index == 2
        assert "500.00" in flags[0].plain_english
        assert "2,000.00" in flags[0].plain_english

    def test_model_config_max_tokens_does_not_bound_amount(self):
        steps = _steps(
            ("session.start", {"workflow_name": "refund"}),
            ("llm.request", {"model": "gpt-4o", "max_tokens": 100, "messages": []}),
            ("llm.response", {"choices": [{"message": {"content": "Approved."}}]}),
            ("tool.call", {"tool": "approve_refund", "amount": 250}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer().analyze(steps)
        assert _flags_for(result, "P2") == []

    def test_tool_retry_budget_does_not_bound_amount(self):
        steps = _steps(
            ("session.start", {"workflow_name": "refund"}),
            ("tool.response", {"tool": "lookup", "max_retries": 3, "timeout_seconds": 30}),
            ("tool.call", {"tool": "approve_refund", "amount": 250}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer().analyze(steps)
        assert _flags_for(result, "P2") == []

    def test_permission_counter_does_not_bound_amount(self):
        steps = _steps(
            ("session.start", {"workflow_name": "refund"}),
            ("tool.response", {"tool": "quota_check", "allowed": 3}),
            ("tool.call", {"tool": "approve_refund", "amount": 250}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer().analyze(steps)
        assert _flags_for(result, "P2") == []

    def test_latest_balance_supersedes_stale_one(self):
        steps = _steps(
            ("session.start", {"workflow_name": "payment"}),
            ("tool.response", {"tool": "get_balance", "balance": 500.0}),
            ("tool.response", {"tool": "get_balance", "balance": 5000.0}),
            ("tool.call", {"tool": "approve_transfer", "amount": 2000.0}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer().analyze(steps)
        assert _flags_for(result, "P2") == []

    def test_stale_balance_still_bounds_when_commitment_exceeds_latest(self):
        steps = _steps(
            ("session.start", {"workflow_name": "payment"}),
            ("tool.response", {"tool": "get_balance", "balance": 500.0}),
            ("tool.response", {"tool": "get_balance", "balance": 5000.0}),
            ("tool.call", {"tool": "approve_transfer", "amount": 9000.0}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer().analyze(steps)
        flags = _flags_for(result, "P2")
        assert len(flags) == 1
        # The refreshed balance is the one that was exceeded.
        assert "5,000.00" in flags[0].plain_english

    def test_token_usage_is_not_a_commitment(self):
        steps = _steps(
            ("session.start", {"workflow_name": "tokens"}),
            ("tool.response", {"tool": "get_balance", "balance": 100.0}),
            ("llm.response", {"usage": {"total_tokens": 900}, "text": "processed"}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer().analyze(steps)
        assert _flags_for(result, "P2") == []


# ── Pass 2: policy-declared fields ────────────────────────────────────────────


def _policy_with_constraint(rule_id: str):
    return EPIPolicy(
        system_name="test",
        system_version="1.0",
        policy_version="2025-01-01",
        rules=[
            PolicyRule(
                id=rule_id,
                name="Balance Check",
                severity="critical",
                description="Never exceed balance.",
                type="constraint_guard",
                watch_for=["balance"],
                violation_if="amount > balance",
            )
        ],
    )


class TestPass2PolicyConstraint:
    def test_policy_watch_for_field_reports_policy_violation(self):
        steps = _steps(
            ("session.start", {"workflow_name": "payment"}),
            ("tool.response", {"tool": "get_balance", "balance": 500.0}),
            ("tool.call", {"tool": "approve_transfer", "amount": 2000.0}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer(policy=_policy_with_constraint("R001")).analyze(steps)
        assert result.primary_fault is not None
        assert result.primary_fault.fault_type == "POLICY_VIOLATION"
        assert result.primary_fault.rule_id == "R001"

    def test_rule_id_containing_underscores_is_preserved(self):
        # The old synthetic "__policy_<id>_<step>_<term>" key was re-parsed at
        # "_", so an id like "refund_policy_v2" became "refund", the rule lookup
        # failed, and the finding was downgraded to a heuristic constraint flag.
        steps = _steps(
            ("session.start", {"workflow_name": "payment"}),
            ("tool.response", {"tool": "get_balance", "balance": 500.0}),
            ("tool.call", {"tool": "approve_transfer", "amount": 2000.0}),
            ("session.end", {"success": True}),
        )
        result = FaultAnalyzer(policy=_policy_with_constraint("refund_policy_v2")).analyze(steps)
        assert result.primary_fault is not None
        assert result.primary_fault.rule_id == "refund_policy_v2"
        assert result.primary_fault.fault_type == "POLICY_VIOLATION"
        assert result.primary_fault.policy_type == "constraint_guard"
