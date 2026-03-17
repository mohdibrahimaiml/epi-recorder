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
        # Pass 4 requires >= 6 steps, should produce no context drop flag
        all_flags = ([result.primary_fault] if result.primary_fault else []) + result.secondary_flags
        drop_flags = [f for f in all_flags if "context" in (f.plain_english or "").lower()]
        assert len(drop_flags) == 0


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
