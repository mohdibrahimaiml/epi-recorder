"""Tests for epi_core.policy — policy loading and validation."""

import json
import pytest
from pathlib import Path

from epi_core.policy import (
    load_policy,
    EPIPolicy,
    PolicyRule,
    build_policy_from_profile,
    list_policy_profiles,
)


MINIMAL_POLICY = {
    "system_name": "test-agent",
    "system_version": "1.0",
    "policy_version": "2025-01-01",
    "rules": [],
}

FULL_POLICY = {
    "system_name": "payment-agent",
    "system_version": "2.0",
    "policy_version": "2025-03-01",
    "rules": [
        {
            "id": "R001",
            "name": "Balance Check",
            "severity": "critical",
            "description": "Never exceed balance.",
            "type": "constraint_guard",
            "watch_for": ["balance", "limit"],
            "violation_if": "amount > balance",
        },
        {
            "id": "R002",
            "name": "Identity Before Refund",
            "severity": "high",
            "description": "Must verify identity before refund.",
            "type": "sequence_guard",
            "required_before": "refund",
            "must_call": "verify_identity",
        },
        {
            "id": "R003",
            "name": "Large Transaction Approval",
            "severity": "high",
            "description": "Over $10k needs human approval.",
            "type": "threshold_guard",
            "threshold_value": 10000,
            "threshold_field": "amount",
            "required_action": "human_approval",
        },
        {
            "id": "R004",
            "name": "No API Keys",
            "severity": "critical",
            "description": "Never output API keys.",
            "type": "prohibition_guard",
            "prohibited_pattern": r"sk-[A-Za-z0-9]+",
        },
    ],
}


class TestLoadPolicy:
    def test_returns_none_when_file_missing(self, tmp_path):
        result = load_policy(search_dir=tmp_path)
        assert result is None

    def test_returns_none_on_malformed_json(self, tmp_path):
        (tmp_path / "epi_policy.json").write_text("not valid json", encoding="utf-8")
        result = load_policy(search_dir=tmp_path)
        assert result is None

    def test_returns_none_on_schema_mismatch(self, tmp_path):
        (tmp_path / "epi_policy.json").write_text(
            json.dumps({"wrong_field": True}), encoding="utf-8"
        )
        result = load_policy(search_dir=tmp_path)
        assert result is None

    def test_returns_policy_for_valid_file(self, tmp_path):
        (tmp_path / "epi_policy.json").write_text(
            json.dumps(MINIMAL_POLICY), encoding="utf-8"
        )
        result = load_policy(search_dir=tmp_path)
        assert isinstance(result, EPIPolicy)
        assert result.system_name == "test-agent"

    def test_empty_rules_list_is_valid(self, tmp_path):
        (tmp_path / "epi_policy.json").write_text(
            json.dumps(MINIMAL_POLICY), encoding="utf-8"
        )
        result = load_policy(search_dir=tmp_path)
        assert result.rules == []

    def test_never_raises(self, tmp_path):
        """load_policy must not raise under any circumstance."""
        (tmp_path / "epi_policy.json").write_text(
            '{"system_name": null, "rules": "not_a_list"}', encoding="utf-8"
        )
        result = load_policy(search_dir=tmp_path)
        assert result is None  # invalid schema, no exception


class TestEPIPolicy:
    def test_all_four_rule_types_parse(self, tmp_path):
        (tmp_path / "epi_policy.json").write_text(
            json.dumps(FULL_POLICY), encoding="utf-8"
        )
        policy = load_policy(search_dir=tmp_path)
        assert policy is not None
        types = {r.type for r in policy.rules}
        assert types == {"constraint_guard", "sequence_guard", "threshold_guard", "prohibition_guard"}

    def test_rules_of_type_filters_correctly(self, tmp_path):
        (tmp_path / "epi_policy.json").write_text(
            json.dumps(FULL_POLICY), encoding="utf-8"
        )
        policy = load_policy(search_dir=tmp_path)
        cg = policy.rules_of_type("constraint_guard")
        assert len(cg) == 1
        assert cg[0].id == "R001"

    def test_constraint_guard_fields(self, tmp_path):
        (tmp_path / "epi_policy.json").write_text(
            json.dumps(FULL_POLICY), encoding="utf-8"
        )
        policy = load_policy(search_dir=tmp_path)
        rule = policy.rules_of_type("constraint_guard")[0]
        assert "balance" in rule.watch_for
        assert rule.severity == "critical"

    def test_sequence_guard_fields(self, tmp_path):
        (tmp_path / "epi_policy.json").write_text(
            json.dumps(FULL_POLICY), encoding="utf-8"
        )
        policy = load_policy(search_dir=tmp_path)
        rule = policy.rules_of_type("sequence_guard")[0]
        assert rule.required_before == "refund"
        assert rule.must_call == "verify_identity"

    def test_threshold_guard_fields(self, tmp_path):
        (tmp_path / "epi_policy.json").write_text(
            json.dumps(FULL_POLICY), encoding="utf-8"
        )
        policy = load_policy(search_dir=tmp_path)
        rule = policy.rules_of_type("threshold_guard")[0]
        assert rule.threshold_value == 10000
        assert rule.required_action == "human_approval"

    def test_prohibition_guard_fields(self, tmp_path):
        (tmp_path / "epi_policy.json").write_text(
            json.dumps(FULL_POLICY), encoding="utf-8"
        )
        policy = load_policy(search_dir=tmp_path)
        rule = policy.rules_of_type("prohibition_guard")[0]
        assert rule.prohibited_pattern is not None

    def test_watch_for_string_coerced_to_list(self, tmp_path):
        policy_data = {**FULL_POLICY, "rules": [{
            **FULL_POLICY["rules"][0],
            "watch_for": "balance",  # string, not list
        }]}
        (tmp_path / "epi_policy.json").write_text(
            json.dumps(policy_data), encoding="utf-8"
        )
        policy = load_policy(search_dir=tmp_path)
        assert isinstance(policy.rules[0].watch_for, list)
        assert "balance" in policy.rules[0].watch_for


class TestPolicyProfiles:
    def test_lists_expected_regulated_profiles(self):
        profiles = list_policy_profiles()
        assert "finance.loan-underwriting" in profiles
        assert "finance.refund-agent" in profiles
        assert "healthcare.triage" in profiles
        assert "healthcare.clinical-assistant" in profiles

    def test_build_finance_profile_returns_valid_policy_shape(self):
        policy = build_policy_from_profile(
            "finance.loan-underwriting",
            system_name="loan-agent",
            system_version="2.8.0",
            policy_version="2026-03-17",
        )
        parsed = EPIPolicy(**policy)
        assert parsed.system_name == "loan-agent"
        assert len(parsed.rules) == 4
        assert parsed.rules_of_type("threshold_guard")[0].required_action == "human_approval"

    def test_build_healthcare_profile_returns_valid_policy_shape(self):
        policy = build_policy_from_profile(
            "healthcare.triage",
            system_name="triage-agent",
            system_version="2.8.0",
            policy_version="2026-03-17",
        )
        parsed = EPIPolicy(**policy)
        assert parsed.system_name == "triage-agent"
        assert len(parsed.rules) == 4
        assert parsed.rules_of_type("sequence_guard")[0].must_call == "collect_symptoms"
