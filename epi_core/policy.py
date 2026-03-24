"""
EPI Policy — Load and validate company-defined rules for fault analysis.

Companies create an `epi_policy.json` file in their project directory.
The PolicyLoader finds it, validates its structure, and returns a typed
EPIPolicy object for the FaultAnalyzer to check against.

Never raises. A missing or malformed policy silently returns None so
recording always completes regardless of policy state.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator


PolicySeverity = Literal["critical", "high", "medium", "low"]
PolicyMode = Literal["detect", "warn", "block", "require_approval", "redact", "quarantine", "escalate"]
PolicyInterventionPoint = Literal[
    "input",
    "prompt",
    "model_request",
    "model_response",
    "tool_call",
    "tool_response",
    "memory_read",
    "memory_write",
    "decision",
    "output",
    "handoff",
    "review",
]


def _slugify_policy_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "epi-policy"


class PolicyScope(BaseModel):
    organization: Optional[str] = None
    team: Optional[str] = None
    application: Optional[str] = None
    workflow: Optional[str] = None
    environment: Optional[str] = None


class ApprovalPolicy(BaseModel):
    approval_id: str
    required_roles: list[str] = Field(default_factory=list)
    minimum_approvers: int = 1
    expires_after_minutes: Optional[int] = None
    reason_required: bool = False
    separation_of_duties: bool = False

    @field_validator("required_roles", mode="before")
    @classmethod
    def coerce_required_roles(cls, v):
        if isinstance(v, str):
            return [v]
        return v


class PolicyRule(BaseModel):
    id: str
    name: str
    severity: PolicySeverity
    description: str
    type: Literal[
        "constraint_guard",
        "sequence_guard",
        "threshold_guard",
        "prohibition_guard",
        "approval_guard",
        "tool_permission_guard",
    ]
    mode: Optional[PolicyMode] = None
    applies_at: Optional[PolicyInterventionPoint] = None

    # constraint_guard: value established at step M must not be exceeded at step N
    watch_for: Optional[list[str]] = None         # keywords that identify the constraint field
    violation_if: Optional[str] = None            # human-readable condition description

    # sequence_guard: action B must only happen after action A
    required_before: Optional[str] = None         # the "B" action (must be preceded)
    must_call: Optional[str] = None               # the "A" action (must come first)

    # threshold_guard: when value crosses threshold, specific action required
    threshold_value: Optional[float] = None
    threshold_field: Optional[str] = None
    required_action: Optional[str] = None

    # prohibition_guard: pattern that must never appear in output
    prohibited_pattern: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("prohibited_pattern", "pattern"),
        serialization_alias="prohibited_pattern",
    )

    # approval_guard: action requires an explicit approval response before execution
    approval_action: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("approval_action", "action"),
        serialization_alias="approval_action",
    )
    approved_by: Optional[str] = None
    approval_policy_ref: Optional[str] = None

    # tool_permission_guard: allow/deny tool usage at selected intervention points
    allowed_tools: Optional[list[str]] = None
    denied_tools: Optional[list[str]] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_prohibition_pattern_alias(cls, values):
        if isinstance(values, dict):
            prohibited = values.get("prohibited_pattern")
            pattern = values.get("pattern")
            if (prohibited is None or prohibited == "") and pattern:
                values["prohibited_pattern"] = pattern
        return values

    @field_validator("watch_for", mode="before")
    @classmethod
    def coerce_watch_for(cls, v):
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("allowed_tools", "denied_tools", mode="before")
    @classmethod
    def coerce_tool_lists(cls, v):
        if isinstance(v, str):
            return [v]
        return v


class EPIPolicy(BaseModel):
    policy_format_version: str = "1.0"
    policy_id: Optional[str] = None
    system_name: str
    system_version: str = "1.0"
    policy_version: str
    profile_id: Optional[str] = None
    scope: Optional[PolicyScope] = None
    approval_policies: list[ApprovalPolicy] = Field(default_factory=list)
    rules: list[PolicyRule] = Field(default_factory=list)

    def rules_of_type(self, rule_type: str) -> list[PolicyRule]:
        return [r for r in self.rules if r.type == rule_type]

    def approval_policy(self, approval_id: str) -> Optional[ApprovalPolicy]:
        for policy in self.approval_policies:
            if policy.approval_id == approval_id:
                return policy
        return None


POLICY_PROFILES: dict[str, dict] = {
    "finance.loan-underwriting": {
        "description": "High-risk lending and underwriting decisions with human approval thresholds.",
        "rules": [
            {
                "id": "R001",
                "name": "Do Not Exceed Known Exposure Limit",
                "severity": "critical",
                "description": "The agent must not approve or recommend an amount above the known balance, limit, or exposure ceiling.",
                "type": "constraint_guard",
                "watch_for": ["balance", "available_balance", "credit_limit", "exposure_limit"],
                "violation_if": "approved_amount > watched_value",
            },
            {
                "id": "R002",
                "name": "Risk Checks Before Final Decision",
                "severity": "high",
                "description": "The agent must complete risk assessment before any approve or decline action.",
                "type": "sequence_guard",
                "required_before": "approve_loan",
                "must_call": "risk_assessment",
            },
            {
                "id": "R003",
                "name": "Human Approval Above Underwriting Threshold",
                "severity": "critical",
                "description": "Loan values above the underwriting threshold require human approval.",
                "type": "threshold_guard",
                "threshold_value": 10000,
                "threshold_field": "amount",
                "required_action": "human_approval",
            },
            {
                "id": "R004",
                "name": "Never Output Secrets Or Account Credentials",
                "severity": "critical",
                "description": "The agent must never emit API keys, tokens, or credential-like strings.",
                "type": "prohibition_guard",
                "prohibited_pattern": r"(sk-[A-Za-z0-9]+|api[_-]?key|secret[_-]?key)",
            },
        ],
    },
    "finance.refund-agent": {
        "description": "Refund and payments operations with identity and escalation controls.",
        "rules": [
            {
                "id": "R001",
                "name": "Do Not Exceed Available Refund Limit",
                "severity": "critical",
                "description": "The agent must not approve refunds above the available balance or authorized limit.",
                "type": "constraint_guard",
                "watch_for": ["balance", "available_balance", "refund_limit"],
                "violation_if": "refund_amount > watched_value",
            },
            {
                "id": "R002",
                "name": "Verify Identity Before Refund",
                "severity": "critical",
                "description": "Identity verification must happen before any refund action.",
                "type": "sequence_guard",
                "required_before": "refund",
                "must_call": "verify_identity",
            },
            {
                "id": "R003",
                "name": "Human Approval Above Refund Threshold",
                "severity": "high",
                "description": "Large refunds require human approval before execution.",
                "type": "threshold_guard",
                "threshold_value": 5000,
                "threshold_field": "amount",
                "required_action": "human_approval",
            },
            {
                "id": "R004",
                "name": "Never Output Payment Secrets",
                "severity": "critical",
                "description": "The agent must never expose tokens, PAN fragments, or API credentials.",
                "type": "prohibition_guard",
                "prohibited_pattern": r"(sk-[A-Za-z0-9]+|tok_[A-Za-z0-9]+|api[_-]?key)",
            },
        ],
    },
    "healthcare.triage": {
        "description": "Clinical triage with escalation and patient-safety controls.",
        "rules": [
            {
                "id": "R001",
                "name": "Do Not Recommend Above Known Risk Ceiling",
                "severity": "critical",
                "description": "The agent must not downgrade or override a known critical risk indicator.",
                "type": "constraint_guard",
                "watch_for": ["risk_score", "acuity_level", "severity_score"],
                "violation_if": "recommended_disposition < watched_value",
            },
            {
                "id": "R002",
                "name": "Collect Symptoms Before Triage Decision",
                "severity": "critical",
                "description": "A triage decision must not occur before symptom capture or intake review.",
                "type": "sequence_guard",
                "required_before": "triage_decision",
                "must_call": "collect_symptoms",
            },
            {
                "id": "R003",
                "name": "Escalate Above Clinical Risk Threshold",
                "severity": "critical",
                "description": "High-risk cases require clinician escalation before final disposition.",
                "type": "threshold_guard",
                "threshold_value": 8,
                "threshold_field": "risk_score",
                "required_action": "clinician_approval",
            },
            {
                "id": "R004",
                "name": "Never Output Secret Or Unsafe Clinical Tokens",
                "severity": "critical",
                "description": "The agent must not emit credentials, tokens, or secret-like values in clinical output.",
                "type": "prohibition_guard",
                "prohibited_pattern": r"(sk-[A-Za-z0-9]+|bearer\s+[A-Za-z0-9._-]+|api[_-]?key)",
            },
        ],
    },
    "healthcare.clinical-assistant": {
        "description": "Clinical support assistant with human signoff and PHI-safe output controls.",
        "rules": [
            {
                "id": "R001",
                "name": "Do Not Exceed Medication Or Dosage Limits",
                "severity": "critical",
                "description": "The agent must not recommend doses or interventions above the known safe limit.",
                "type": "constraint_guard",
                "watch_for": ["dose_limit", "max_dosage", "care_limit"],
                "violation_if": "recommended_value > watched_value",
            },
            {
                "id": "R002",
                "name": "Verify Patient Context Before Recommendation",
                "severity": "critical",
                "description": "The agent must collect patient context before making a recommendation.",
                "type": "sequence_guard",
                "required_before": "clinical_recommendation",
                "must_call": "collect_patient_context",
            },
            {
                "id": "R003",
                "name": "Clinician Signoff Above Severity Threshold",
                "severity": "critical",
                "description": "Severe or high-risk cases require clinician signoff before recommendation is finalized.",
                "type": "threshold_guard",
                "threshold_value": 7,
                "threshold_field": "severity_score",
                "required_action": "clinician_approval",
            },
            {
                "id": "R004",
                "name": "Never Output Secrets Or Unsafe Identifiers",
                "severity": "critical",
                "description": "The agent must never expose secret-like strings or credential material in output.",
                "type": "prohibition_guard",
                "prohibited_pattern": r"(sk-[A-Za-z0-9]+|api[_-]?key|secret[_-]?key)",
            },
        ],
    },
}


def list_policy_profiles() -> list[str]:
    """Return supported built-in policy profile names."""
    return sorted(POLICY_PROFILES.keys())


def build_policy_from_profile(
    profile_name: str,
    *,
    system_name: str,
    system_version: str,
    policy_version: str,
) -> dict:
    """
    Render a built-in policy profile into a concrete epi_policy.json payload.

    Raises:
        KeyError: if the profile name is unknown.
    """
    profile = POLICY_PROFILES[profile_name]
    return {
        "policy_format_version": "2.0",
        "policy_id": _slugify_policy_id(system_name),
        "system_name": system_name,
        "system_version": system_version,
        "policy_version": policy_version,
        "profile_id": profile_name,
        "rules": [dict(rule) for rule in profile["rules"]],
    }


def load_policy(search_dir: Optional[Path] = None) -> Optional[EPIPolicy]:
    """
    Look for epi_policy.json in search_dir and return a typed EPIPolicy.

    Args:
        search_dir: Directory to search. Defaults to cwd().

    Returns:
        EPIPolicy if found and valid, None otherwise.
        Never raises — a broken policy never breaks recording.
    """
    search_dir = search_dir or Path.cwd()
    policy_path = search_dir / "epi_policy.json"

    if not policy_path.exists():
        return None

    try:
        data = json.loads(policy_path.read_text(encoding="utf-8"))
        return EPIPolicy(**data)
    except Exception:
        # Malformed policy must not break recording, but the user should know
        # why policy-grounded analysis was skipped.
        print(
            f"[EPI] Warning: {policy_path} exists but is invalid; "
            "continuing without policy-grounded analysis",
            file=sys.stderr,
        )
        return None


STARTER_POLICY_TEMPLATE = """\
{
  "system_name": "{system_name}",
  "system_version": "{system_version}",
  "policy_version": "{policy_version}",
  "rules": [
    {
      "id": "R001",
      "name": "Example Constraint Guard",
      "severity": "critical",
      "description": "Agent must never approve an amount exceeding the available balance.",
      "type": "constraint_guard",
      "watch_for": ["balance", "available_funds", "limit"],
      "violation_if": "approval_amount > watched_value"
    },
    {
      "id": "R002",
      "name": "Example Sequence Guard",
      "severity": "high",
      "description": "Agent must verify identity before processing a refund.",
      "type": "sequence_guard",
      "required_before": "refund",
      "must_call": "verify_identity"
    },
    {
      "id": "R003",
      "name": "Example Threshold Guard",
      "severity": "high",
      "description": "Transactions above $10,000 require human approval.",
      "type": "threshold_guard",
      "threshold_value": 10000,
      "threshold_field": "transaction_amount",
      "required_action": "human_approval"
    },
    {
      "id": "R004",
      "name": "Example Prohibition Guard",
      "severity": "critical",
      "description": "Agent must never output raw API keys or secrets.",
      "type": "prohibition_guard",
      "prohibited_pattern": "sk-[A-Za-z0-9]+"
    },
    {
      "id": "R005",
      "name": "Example Approval Guard",
      "severity": "critical",
      "description": "Refund approval requires an explicit approved response from a manager.",
      "type": "approval_guard",
      "approval_action": "approve_refund",
      "approved_by": "manager"
    },
    {
      "id": "R006",
      "name": "Example Tool Permission Guard",
      "severity": "critical",
      "description": "Only approved tools may be used in this workflow.",
      "type": "tool_permission_guard",
      "mode": "block",
      "applies_at": "tool_call",
      "allowed_tools": ["lookup_order", "verify_identity", "approve_refund"],
      "denied_tools": ["delete_customer"]
    }
  ]
}
"""
