"""
RuntimePolicyEngine — In-process policy evaluation for AI agent actions.

Evaluates EPI policy rules at specific intervention points and returns
enforcement actions (ALLOW, BLOCK, REDACT, WARN, REQUIRE_APPROVAL).
"""

from __future__ import annotations

import enum
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from epi_core.policy import EPIPolicy, PolicyRule
from epi_core.redactor import get_default_redactor


class EnforcementAction(enum.Enum):
    """Possible outcomes of policy evaluation at an intervention point."""

    ALLOW = "allow"
    BLOCK = "block"
    WARN = "warn"
    REDACT = "redact"
    REQUIRE_APPROVAL = "require_approval"
    QUARANTINE = "quarantine"
    ESCALATE = "escalate"


@dataclass
class Violation:
    """A single policy violation detected at runtime."""

    rule_id: str
    rule_name: str
    rule_type: str
    severity: str
    intervention_point: str
    action: EnforcementAction
    reason: str
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "rule_type": self.rule_type,
            "severity": self.severity,
            "intervention_point": self.intervention_point,
            "action": self.action.value,
            "reason": self.reason,
            "evidence": self.evidence,
        }


class PolicyLoadError(Exception):
    """Raised when the policy file cannot be loaded or is invalid."""

    pass


class TrustEnforcementError(Exception):
    """Raised when a policy violation is enforced with BLOCK mode."""

    def __init__(self, violation: Violation):
        self.violation = violation
        super().__init__(
            f"Trust enforcement blocked action: [{violation.rule_id}] {violation.rule_name} — {violation.reason}"
        )


class RuntimePolicyEngine:
    """
    In-process policy engine that evaluates rules at intervention points.

    Loads an epi_policy.json file and evaluates rules against agent actions.
    Designed to be fast, deterministic, and fail-closed.
    """

    # Map rule type → evaluator method name
    _EVALUATORS: Dict[str, str] = {
        "tool_permission_guard": "_eval_tool_permission",
        "prohibition_guard": "_eval_prohibition",
        "threshold_guard": "_eval_threshold",
        "approval_guard": "_eval_approval",
        "sequence_guard": "_eval_sequence",
        "constraint_guard": "_eval_constraint",
    }

    def __init__(
        self,
        policy_path: Path | str | None = None,
        *,
        default_mode: str = "warn",
        enable_blocking: bool = False,
    ):
        """
        Initialize the runtime policy engine.

        Args:
            policy_path: Path to epi_policy.json. If None, searches cwd then EPI_POLICY_PATH env.
            default_mode: Default enforcement mode when rule.mode is None.
            enable_blocking: Whether BLOCK mode is actually enforced (False = log but don't block).
                             This allows gradual rollout: start with warnings, then enable blocking.
        """
        self.default_mode = default_mode
        self.enable_blocking = enable_blocking
        self._policy: EPIPolicy | None = None
        self._sequence_state: Dict[str, Any] = {}  # Tracks sequence_guard state
        self._redactor = get_default_redactor()

        # Load policy
        self._load_policy(policy_path)

    def _load_policy(self, policy_path: Path | str | None) -> None:
        """Load and validate the EPI policy file."""
        path = self._resolve_policy_path(policy_path)
        if path is None:
            self._policy = None
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._policy = EPIPolicy.model_validate(data)
        except Exception as exc:
            raise PolicyLoadError(f"Failed to load policy from {path}: {exc}") from exc

    def _resolve_policy_path(self, policy_path: Path | str | None) -> Path | None:
        """Resolve policy file path from argument, cwd, or environment."""
        if policy_path is not None:
            p = Path(policy_path)
            if p.exists():
                return p
            raise PolicyLoadError(f"Policy file not found: {p}")

        # Search cwd
        cwd_policy = Path.cwd() / "epi_policy.json"
        if cwd_policy.exists():
            return cwd_policy

        # Search EPI_POLICY_PATH env
        env_path = os.environ.get("EPI_POLICY_PATH")
        if env_path:
            p = Path(env_path)
            if p.exists():
                return p

        # No policy found — engine operates in permissive mode
        return None

    @property
    def is_active(self) -> bool:
        """True if a valid policy is loaded and the engine is enforcing."""
        return self._policy is not None

    @property
    def policy_id(self) -> str | None:
        return self._policy.policy_id if self._policy else None

    # ─────────────────────────────────────────────────────────────
    # Public API: evaluate at intervention point
    # ─────────────────────────────────────────────────────────────

    def evaluate(
        self,
        intervention_point: str,
        context: dict[str, Any],
    ) -> Tuple[EnforcementAction, List[Violation]]:
        """
        Evaluate all applicable policy rules at an intervention point.

        Args:
            intervention_point: One of the EPI intervention points
                                (input, prompt, model_request, model_response,
                                 tool_call, tool_response, memory_read, memory_write,
                                 decision, output, handoff, review)
            context: Dict describing the action being evaluated. Keys vary by point:
                     - tool_call: {"tool": str, "input": dict}
                     - model_request: {"messages": list, "model": str}
                     - model_response: {"choices": list, "content": str}
                     - decision: {"decision": str, "confidence": float}
                     - output: {"content": str}

        Returns:
            Tuple of (most_severe_action, list_of_violations)
        """
        if not self.is_active:
            return EnforcementAction.ALLOW, []

        violations: List[Violation] = []

        for rule in self._policy.rules:
            # Skip rules that don't apply at this intervention point
            if not self._rule_applies_at(rule, intervention_point):
                continue

            # Find the evaluator for this rule type
            evaluator_name = self._EVALUATORS.get(rule.type)
            if evaluator_name is None:
                continue

            evaluator = getattr(self, evaluator_name)
            try:
                action, reason, evidence = evaluator(rule, context)
            except Exception:
                # Deterministic evaluators should not raise, but if they do,
                # fail-closed: treat as BLOCK
                action = EnforcementAction.BLOCK
                reason = f"Policy evaluator crashed for {rule.id}"
                evidence = {}

            if action != EnforcementAction.ALLOW:
                violations.append(
                    Violation(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        rule_type=rule.type,
                        severity=rule.severity,
                        intervention_point=intervention_point,
                        action=action,
                        reason=reason,
                        evidence=evidence,
                    )
                )

        if not violations:
            return EnforcementAction.ALLOW, []

        # Return the most severe action
        severity_order = [
            EnforcementAction.ALLOW,
            EnforcementAction.WARN,
            EnforcementAction.REQUIRE_APPROVAL,
            EnforcementAction.REDACT,
            EnforcementAction.QUARANTINE,
            EnforcementAction.ESCALATE,
            EnforcementAction.BLOCK,
        ]
        most_severe = max(violations, key=lambda v: severity_order.index(v.action))
        return most_severe.action, violations

    def enforce(
        self,
        intervention_point: str,
        context: dict[str, Any],
        *,
        on_violation: Callable[[Violation], Any] | None = None,
    ) -> None:
        """
        Evaluate and immediately enforce the policy.

        Raises:
            TrustEnforcementError: If a BLOCK-mode violation is detected and blocking is enabled.

        Returns silently if ALLOW, WARN, or blocking is disabled.
        """
        action, violations = self.evaluate(intervention_point, context)

        if action == EnforcementAction.ALLOW:
            return

        # Log all violations (even if we don't block)
        for v in violations:
            if on_violation:
                on_violation(v)

        # Handle non-blocking actions
        if action in (EnforcementAction.WARN, EnforcementAction.ESCALATE):
            return  # Logged via on_violation, but execution continues

        if action == EnforcementAction.REQUIRE_APPROVAL:
            return  # Caller must handle approval separately

        if action == EnforcementAction.BLOCK:
            primary = violations[0] if violations else None
            if primary and self.enable_blocking:
                raise TrustEnforcementError(primary)
            # Blocking disabled — just warn
            return

    # ─────────────────────────────────────────────────────────────
    # Rule evaluators (one per rule type)
    # ─────────────────────────────────────────────────────────────

    def _eval_tool_permission(
        self, rule: PolicyRule, context: dict
    ) -> Tuple[EnforcementAction, str, dict]:
        """Evaluate tool_permission_guard: check if tool is allowed/denied."""
        tool_name = context.get("tool", "")
        if not tool_name:
            return EnforcementAction.ALLOW, "", {}

        denied = rule.denied_tools or []
        allowed = rule.allowed_tools or []

        if tool_name in denied:
            mode = self._resolve_mode(rule)
            return (
                mode,
                f"Tool '{tool_name}' is in the denied list",
                {"tool": tool_name, "denied_list": denied},
            )

        # If allowed_tools is specified and this tool is NOT in it, deny
        if allowed and tool_name not in allowed:
            mode = self._resolve_mode(rule)
            return (
                mode,
                f"Tool '{tool_name}' is not in the allowed list",
                {"tool": tool_name, "allowed_list": allowed},
            )

        return EnforcementAction.ALLOW, "", {}

    def _eval_prohibition(
        self, rule: PolicyRule, context: dict
    ) -> Tuple[EnforcementAction, str, dict]:
        """Evaluate prohibition_guard: check for prohibited patterns in content."""
        pattern = rule.prohibited_pattern
        if not pattern:
            return EnforcementAction.ALLOW, "", {}

        # Search across all string values in context
        content_text = self._extract_text(context)
        if not content_text:
            return EnforcementAction.ALLOW, "", {}

        try:
            regex = re.compile(pattern, re.IGNORECASE)
            match = regex.search(content_text)
            if match:
                mode = self._resolve_mode(rule)
                matched_text = match.group(0)
                # Redact the match in evidence to avoid leaking secrets in logs
                redacted_match = self._redactor._get_placeholder("prohibited_match", matched_text) if hasattr(self._redactor, '_get_placeholder') else "***REDACTED***"
                return (
                    mode,
                    f"Prohibited pattern matched: {rule.name}",
                    {"matched": redacted_match, "pattern": pattern},
                )
        except re.error:
            # Invalid regex — treat as no match (conservative)
            pass

        return EnforcementAction.ALLOW, "", {}

    def _eval_threshold(
        self, rule: PolicyRule, context: dict
    ) -> Tuple[EnforcementAction, str, dict]:
        """Evaluate threshold_guard: check if a value exceeds a threshold."""
        threshold = rule.threshold_value
        field = rule.threshold_field
        if threshold is None or not field:
            return EnforcementAction.ALLOW, "", {}

        value = self._extract_numeric(context, field)
        if value is None:
            return EnforcementAction.ALLOW, "", {}

        if value > threshold:
            mode = self._resolve_mode(rule)
            return (
                mode,
                f"Value {value} exceeds threshold {threshold} for field '{field}'",
                {"field": field, "value": value, "threshold": threshold},
            )

        return EnforcementAction.ALLOW, "", {}

    def _eval_approval(
        self, rule: PolicyRule, context: dict
    ) -> Tuple[EnforcementAction, str, dict]:
        """Evaluate approval_guard: action requires explicit approval."""
        action_name = rule.approval_action
        if not action_name:
            return EnforcementAction.ALLOW, "", {}

        # Check if the current action matches the approval-required action
        current_action = context.get("action", "") or context.get("tool", "") or context.get("decision", "")
        if current_action != action_name:
            return EnforcementAction.ALLOW, "", {}

        mode = self._resolve_mode(rule)
        # approval_guard always maps to REQUIRE_APPROVAL or BLOCK
        if mode == EnforcementAction.WARN:
            mode = EnforcementAction.REQUIRE_APPROVAL

        return (
            mode,
            f"Action '{action_name}' requires explicit approval",
            {"action": action_name, "approval_policy_ref": rule.approval_policy_ref},
        )

    def _eval_sequence(
        self, rule: PolicyRule, context: dict
    ) -> Tuple[EnforcementAction, str, dict]:
        """Evaluate sequence_guard: action B must happen after action A."""
        required_before = rule.required_before
        must_call = rule.must_call
        if not required_before or not must_call:
            return EnforcementAction.ALLOW, "", {}

        current_action = context.get("action", "") or context.get("tool", "") or context.get("decision", "")
        if current_action != required_before:
            return EnforcementAction.ALLOW, "", {}

        # Check if must_call was previously recorded
        key = f"seq:{must_call}"
        if not self._sequence_state.get(key, False):
            mode = self._resolve_mode(rule)
            return (
                mode,
                f"Action '{required_before}' requires '{must_call}' to be called first",
                {"required_before": required_before, "must_call": must_call},
            )

        return EnforcementAction.ALLOW, "", {}

    def _eval_constraint(
        self, rule: PolicyRule, context: dict
    ) -> Tuple[EnforcementAction, str, dict]:
        """Evaluate constraint_guard: value must not exceed established limit."""
        watch_for = rule.watch_for or []
        if not watch_for:
            return EnforcementAction.ALLOW, "", {}

        # Extract all watched values from context
        watched_values = {}
        for key in watch_for:
            val = self._extract_numeric(context, key)
            if val is not None:
                watched_values[key] = val

        if not watched_values:
            return EnforcementAction.ALLOW, "", {}

        # For now, simplistic constraint check: if any watched value is negative
        # or if we're checking a result against a previously established constraint.
        # Full constraint evaluation requires two-phase tracking (establish + check).
        # This evaluator focuses on the "check" phase.
        mode = self._resolve_mode(rule)

        # Check if any value violates a known constraint
        for key, val in watched_values.items():
            constraint_key = f"constraint:{key}"
            established_limit = self._sequence_state.get(constraint_key)
            if established_limit is not None and val > established_limit:
                return (
                    mode,
                    f"Value {val} for '{key}' exceeds established limit {established_limit}",
                    {"field": key, "value": val, "limit": established_limit},
                )

        return EnforcementAction.ALLOW, "", {}

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _resolve_mode(self, rule: PolicyRule) -> EnforcementAction:
        """Resolve the enforcement mode for a rule."""
        raw = rule.mode or self.default_mode
        try:
            return EnforcementAction(raw)
        except ValueError:
            return EnforcementAction.WARN

    def _rule_applies_at(self, rule: PolicyRule, point: str) -> bool:
        """Check if a rule applies at a given intervention point."""
        applies = rule.applies_at
        if applies is None:
            # Default: tool_permission applies at tool_call, prohibition at output/prompt, etc.
            defaults = {
                "tool_permission_guard": ["tool_call"],
                "prohibition_guard": ["output", "prompt", "model_response"],
                "threshold_guard": ["tool_call", "decision"],
                "approval_guard": ["tool_call", "decision"],
                "sequence_guard": ["tool_call", "decision"],
                "constraint_guard": ["tool_call", "decision", "tool_response"],
            }
            applies = defaults.get(rule.type, [])

        if isinstance(applies, str):
            return applies == point
        if isinstance(applies, list):
            return point in applies
        return False

    def _extract_text(self, context: dict) -> str:
        """Extract all text content from a context dict for pattern matching."""
        parts = []

        def collect(obj):
            if isinstance(obj, str):
                parts.append(obj)
            elif isinstance(obj, dict):
                for v in obj.values():
                    collect(v)
            elif isinstance(obj, list):
                for item in obj:
                    collect(item)

        collect(context)
        return "\n".join(parts)

    def _extract_numeric(self, context: dict, field: str) -> float | None:
        """Extract a numeric value from context by field name."""
        # Direct key match
        if field in context:
            val = context[field]
            if isinstance(val, (int, float)):
                return float(val)
            try:
                return float(val)
            except (ValueError, TypeError):
                pass

        # Nested search
        def search(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == field:
                        if isinstance(v, (int, float)):
                            return float(v)
                        try:
                            return float(v)
                        except (ValueError, TypeError):
                            pass
                    result = search(v)
                    if result is not None:
                        return result
            elif isinstance(obj, list):
                for item in obj:
                    result = search(item)
                    if result is not None:
                        return result
            return None

        return search(context)

    def record_sequence_action(self, action: str) -> None:
        """Record that an action was performed (for sequence_guard tracking)."""
        self._sequence_state[f"seq:{action}"] = True

    def record_constraint(self, field: str, limit: float) -> None:
        """Record an established constraint limit (for constraint_guard tracking)."""
        self._sequence_state[f"constraint:{field}"] = limit
