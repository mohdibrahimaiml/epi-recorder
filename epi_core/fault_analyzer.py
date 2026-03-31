"""
EPI Fault Intelligence — Four-pass heuristic + policy-grounded fault analyzer.

Reads steps.jsonl content, checks it against an optional EPIPolicy,
and produces a structured analysis.json result.

Design principles:
  - Conservative: better to miss a fault than to false-positive.
  - Deterministic: no LLM calls. Plain-English summaries are template-based.
  - Additive: never modifies steps.jsonl. Analysis is a separate sealed artifact.
  - Graceful: any exception inside a detection pass is caught; analysis completes.

The four passes:
  1. Error Continuation  — tool returned error, agent continued as if it succeeded.
  2. Constraint Violation — numerical limit set at step M violated at step N.
  3. Sequence Violation   — action B occurred before required action A (policy only).
  4. Context Drop         — key entity identifier vanishes from the final third.
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional

from epi_core.policy import EPIPolicy


# ── Constants ─────────────────────────────────────────────────────────────────

ANALYZER_VERSION = "1.0.0"

DISCLAIMER = (
    "The raw execution record in steps.jsonl is the ground truth. Policy violations "
    "are deterministic rule matches. Heuristic observations are pattern-based and "
    "should be reviewed by a human."
)

_CONSTRAINT_KEYWORDS = {
    "balance", "available", "available_funds", "limit", "maximum", "max",
    "quota", "threshold", "remaining", "cap", "ceiling", "max_amount",
    "allowed", "authorized", "credit_limit", "account_limit",
}

_COMMITMENT_KEYWORDS = {
    "approve", "approved", "process", "processed", "execute", "executed",
    "authorize", "authorized", "confirm", "confirmed", "commit",
    "complete", "finalize", "submit", "issue", "disburse", "charge",
    "transfer", "transact",
}

_ERROR_INDICATORS = {
    "error", "exception", "failed", "failure", "timeout", "refused",
    "denied", "unauthorized", "forbidden", "not found", "invalid",
    "traceback", "stack trace",
}

_ERROR_KEYS = {"error", "exception", "traceback", "err", "error_message", "error_code"}

_ID_KEY_PATTERNS = re.compile(
    r"(account|customer|user|transaction|order|request|session|ref|reference|"
    r"invoice|ticket|case|id|identifier|uuid|token)$",
    re.IGNORECASE,
)

_ID_VALUE_PATTERNS = re.compile(
    r"^[A-Z]{2,6}-\d{3,}$|"                           # ACC-123, TXN-9876
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$|"  # UUID
    r"^(?=.*\d)[A-Z0-9]{6,20}$",                       # TX789, CUST001 (must contain a digit)
    re.IGNORECASE,
)

_ENTITY_ID_EXEMPT_KEYS = {
    "policy_number",
    "policy_clause",
}


# ── Data classes ───────────────────────────────────────────────────────────────

_FAULT_CATEGORY_MAP = {
    "POLICY_VIOLATION": "policy_violation",
    "HEURISTIC_OBSERVATION": "heuristic_observation",
}

_REVIEW_REQUIRED_SEVERITIES = {"critical", "high"}


class FaultFlag:
    __slots__ = (
        "step_index",
        "step_number",
        "fault_type",
        "severity",
        "rule_id",
        "rule_name",
        "plain_english",
        "fault_chain",
        "category",
        "why_it_matters",
        "review_required",
        "policy_type",
        "policy_mode",
        "policy_applies_at",
        "raw",
    )

    def __init__(self, step_index, fault_type, severity, plain_english,
                 rule_id=None, rule_name=None, fault_chain=None,
                 category=None, why_it_matters=None, review_required=None,
                 policy_type=None, policy_mode=None, policy_applies_at=None):
        self.step_index = step_index
        self.step_number = step_index + 1
        self.fault_type = fault_type
        self.severity = severity
        self.plain_english = plain_english
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.fault_chain = fault_chain or []
        self.category = category or _FAULT_CATEGORY_MAP.get(fault_type, "execution_risk")
        self.why_it_matters = why_it_matters or self._default_why_it_matters()
        self.review_required = (
            review_required if review_required is not None
            else (self.fault_type == "POLICY_VIOLATION" or self.severity in _REVIEW_REQUIRED_SEVERITIES)
        )
        self.policy_type = policy_type
        self.policy_mode = policy_mode
        self.policy_applies_at = policy_applies_at
        self.raw = {}

    def _default_why_it_matters(self) -> str:
        if self.fault_type == "POLICY_VIOLATION":
            return "This run broke an explicit policy rule and should be reviewed before the outcome is trusted."
        if self.severity in {"critical", "high"}:
            return "This pattern suggests a potentially unsafe or non-compliant outcome and should be reviewed by a human."
        return "This pattern may indicate degraded reasoning or missing context and should be inspected if the run matters."

    def to_dict(self):
        d = {
            "step_index": self.step_index,
            "step_number": self.step_number,
            "fault_type": self.fault_type,
            "category": self.category,
            "severity": self.severity,
            "plain_english": self.plain_english,
            "why_it_matters": self.why_it_matters,
            "review_required": self.review_required,
            "fault_chain": self.fault_chain,
        }
        if self.rule_id:
            d["rule_id"] = self.rule_id
        if self.rule_name:
            d["rule_name"] = self.rule_name
        if self.policy_type:
            d["policy_type"] = self.policy_type
        if self.policy_mode:
            d["policy_mode"] = self.policy_mode
        if self.policy_applies_at:
            d["policy_applies_at"] = self.policy_applies_at
        return d


class AnalysisResult:
    def __init__(self, policy: Optional[EPIPolicy], steps: list[dict]):
        self.policy = policy
        self.steps = steps
        self.primary_fault: Optional[FaultFlag] = None
        self.secondary_flags: list[FaultFlag] = []
        self.analyzer_version = ANALYZER_VERSION
        self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def fault_detected(self) -> bool:
        return self.primary_fault is not None

    @property
    def mode(self) -> str:
        return "policy_grounded" if self.policy else "heuristic_only"

    @property
    def confidence(self) -> str:
        if not self.fault_detected:
            return "high"
        # Confidence is high when we have a policy rule match with a clear chain
        if self.primary_fault and self.primary_fault.rule_id and len(self.primary_fault.fault_chain) >= 2:
            return "high"
        if self.primary_fault and len(self.primary_fault.fault_chain) >= 1:
            return "medium"
        return "low"

    def to_dict(self) -> dict:
        total = len(self.steps)
        full_data = sum(
            1 for s in self.steps
            if s.get("content") and isinstance(s["content"], dict) and len(s["content"]) > 0
        )

        d = {
            "analyzer_version": self.analyzer_version,
            "analysis_timestamp": self.timestamp,
            "policy_used": self.policy is not None,
            "policy_format_version": self.policy.policy_format_version if self.policy else None,
            "policy_id": self.policy.policy_id if self.policy else None,
            "policy_version": self.policy.policy_version if self.policy else None,
            "policy_scope": self.policy.scope.model_dump(exclude_none=True) if self.policy and self.policy.scope else None,
            "mode": self.mode,
            "fault_taxonomy_version": "1.0",
            "coverage": {
                "status": "complete",
                "steps_recorded": total,
                "steps_with_full_data": full_data,
                "coverage_percentage": round(full_data / total * 100) if total else 0,
            },
            "fault_detected": self.fault_detected,
            "confidence": self.confidence,
            "review_required": bool(
                (self.primary_fault and self.primary_fault.review_required)
                or any(flag.review_required for flag in self.secondary_flags)
            ),
            "primary_fault": self.primary_fault.to_dict() if self.primary_fault else None,
            "secondary_flags": [f.to_dict() for f in self.secondary_flags],
            "summary": {
                "headline": self._headline(),
                "primary_category": self.primary_fault.category if self.primary_fault else None,
                "primary_step": self.primary_fault.step_number if self.primary_fault else None,
                "secondary_count": len(self.secondary_flags),
            },
            "human_review": {
                "status": "pending",
                "reviewed_by": None,
                "reviewed_at": None,
                "outcome": None,
                "notes": None,
            },
            "disclaimer": DISCLAIMER,
        }
        return d

    def _all_flags(self) -> list[FaultFlag]:
        return ([self.primary_fault] if self.primary_fault else []) + self.secondary_flags

    def to_policy_evaluation_dict(self) -> Optional[dict]:
        if not self.policy:
            return None

        matched_by_rule: dict[str, list[FaultFlag]] = {}
        for flag in self._all_flags():
            if flag.rule_id:
                matched_by_rule.setdefault(flag.rule_id, []).append(flag)

        results = []
        for rule in self.policy.rules:
            matched = matched_by_rule.get(rule.id, [])
            results.append({
                "rule_id": rule.id,
                "rule_name": rule.name,
                "rule_type": rule.type,
                "severity": rule.severity,
                "mode": rule.mode or "detect",
                "applies_at": rule.applies_at,
                "status": "failed" if matched else "passed",
                "review_required": bool(matched and any(flag.review_required for flag in matched)),
                "match_count": len(matched),
                "step_numbers": [flag.step_number for flag in matched],
                "plain_english": (
                    matched[0].plain_english
                    if matched else
                    f"No violation detected for rule {rule.id} ({rule.name})."
                ),
                "matched_findings": [flag.to_dict() for flag in matched],
            })

        return {
            "policy_format_version": self.policy.policy_format_version,
            "policy_id": self.policy.policy_id,
            "policy_version": self.policy.policy_version,
            "policy_scope": self.policy.scope.model_dump(exclude_none=True) if self.policy.scope else None,
            "evaluation_timestamp": self.timestamp,
            "evaluation_mode": self.mode,
            "controls_evaluated": len(results),
            "controls_failed": sum(1 for result in results if result["status"] == "failed"),
            "artifact_review_required": bool(
                (self.primary_fault and self.primary_fault.review_required)
                or any(flag.review_required for flag in self.secondary_flags)
            ),
            "results": results,
        }

    def to_policy_evaluation_json(self) -> Optional[str]:
        data = self.to_policy_evaluation_dict()
        if data is None:
            return None
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _headline(self) -> str:
        if not self.primary_fault:
            return "No fault detected in the recorded execution."
        if self.primary_fault.rule_id and self.primary_fault.rule_name:
            return f"{self.primary_fault.rule_id} ({self.primary_fault.rule_name}) triggered at step {self.primary_fault.step_number}."
        return f"{self.primary_fault.fault_type} triggered at step {self.primary_fault.step_number}."

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _flatten_values(obj, depth=0) -> list:
    """Recursively extract all scalar values from a dict/list."""
    if depth > 6:
        return []
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            results.extend(_flatten_values(v, depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_flatten_values(item, depth + 1))
    elif obj is not None:
        results.append(obj)
    return results


def _flatten_kv(obj, prefix="", depth=0) -> list[tuple[str, object]]:
    """Recursively extract all (key_path, value) pairs from a dict."""
    if depth > 6:
        return []
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            results.extend(_flatten_kv(v, path, depth + 1))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            results.extend(_flatten_kv(item, f"{prefix}[{i}]", depth + 1))
    else:
        results.append((prefix, obj))
    return results


def _content_str(step: dict) -> str:
    """Get a lowercase string representation of step content for keyword matching."""
    content = step.get("content", {})
    try:
        return json.dumps(content, ensure_ascii=False).lower()
    except Exception:
        return str(content).lower()


def _step_kind(step: dict) -> str:
    return str(step.get("kind", "")).lower()


def _value_matches(value: object, needle: str) -> bool:
    return isinstance(value, str) and needle.lower() in value.lower()


def _is_approval_keyword(action_name: str) -> bool:
    action_lower = action_name.lower()
    return "approval" in action_lower or "signoff" in action_lower


def _get_primary_action(step: dict) -> Optional[str]:
    content = step.get("content", {})
    if not isinstance(content, dict):
        return None

    kind = _step_kind(step)
    if kind.startswith("tool."):
        tool = content.get("tool") or content.get("name") or content.get("action")
        return str(tool).lower() if isinstance(tool, str) else None
    if kind == "agent.decision":
        decision = content.get("decision")
        return str(decision).lower() if isinstance(decision, str) else None
    if kind in {"agent.approval.request", "agent.approval.response"}:
        action = content.get("action")
        return str(action).lower() if isinstance(action, str) else None
    if kind == "agent.handoff":
        target = content.get("to_agent")
        if isinstance(target, str):
            return f"handoff {target}".lower()
        return "handoff"
    if kind == "agent.state":
        state = content.get("state")
        return str(state).lower() if isinstance(state, str) else None
    return None


def _is_action_trigger_step(step: dict) -> bool:
    kind = _step_kind(step)
    if kind in {
        "agent.approval.request",
        "agent.approval.response",
        "agent.plan",
        "agent.message",
        "agent.memory.read",
        "agent.memory.write",
        "agent.run.pause",
        "agent.run.resume",
        "agent.state",
    }:
        return False
    if kind.startswith("tool.call") or kind.startswith("tool.use"):
        return True
    if kind in {"agent.decision", "agent.handoff", "agent.action", "agent.finish"}:
        return True
    return _content_mentions(step, _COMMITMENT_KEYWORDS)


def _step_satisfies_approval(step: dict, action_name: Optional[str] = None, approver: Optional[str] = None) -> bool:
    kind = _step_kind(step)
    content = step.get("content", {})
    if not isinstance(content, dict):
        content = {}

    if kind == "agent.approval.response":
        if content.get("approved") is not True:
            return False
        if action_name and not (
            _value_matches(content.get("action"), action_name)
            or action_name.lower() in _content_str(step)
        ):
            return False
        if approver and not _value_matches(content.get("reviewer"), approver):
            return False
        return True

    if content.get("approved") is True:
        if approver and not _value_matches(content.get("reviewer"), approver):
            return False
        return True

    text = _content_str(step)
    if action_name and action_name.lower() in text and ("approved" in text or "approval" in text):
        if approver and approver.lower() not in text:
            return False
        return True
    return False


def _matches_named_action(step: dict, action_name: str) -> bool:
    action_lower = action_name.lower()
    kind = _step_kind(step)
    if action_lower in kind:
        return True

    primary_action = _get_primary_action(step)
    if primary_action and action_lower in primary_action:
        return True

    content = step.get("content", {})
    if isinstance(content, dict):
        for key in ("tool", "action", "decision", "state", "requested_by", "to_agent", "from_agent"):
            if _value_matches(content.get(key), action_lower):
                return True

    if _is_approval_keyword(action_lower):
        return _step_satisfies_approval(step, action_lower)

    return action_lower in _content_str(step)


def _matching_approval_requests(steps: list[dict], *, action_name: str, before_index: int) -> list[dict]:
    matches = []
    for i, step in enumerate(steps[:before_index]):
        if _step_kind(step) != "agent.approval.request":
            continue
        if _matches_named_action(step, action_name):
            matches.append({
                "step": step,
                "index": step.get("index", i),
                "content": step.get("content", {}) if isinstance(step.get("content"), dict) else {},
            })
    return matches


def _matching_approval_responses(steps: list[dict], *, action_name: str, before_index: int) -> list[dict]:
    matches = []
    for i, step in enumerate(steps[:before_index]):
        if _step_kind(step) != "agent.approval.response":
            continue
        if not _matches_named_action(step, action_name):
            continue
        content = step.get("content", {}) if isinstance(step.get("content"), dict) else {}
        matches.append({
            "step": step,
            "index": step.get("index", i),
            "content": content,
            "approved": bool(content.get("approved")),
        })
    return matches


def _approval_actor_labels(content: dict) -> set[str]:
    labels = set()
    for key in ("reviewer", "reviewer_role", "role", "approved_by", "approver"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            labels.add(value.strip().lower())
    return labels


def _approval_responses_satisfy_policy(
    responses: list[dict],
    requests: list[dict],
    *,
    required_roles: list[str],
    minimum_approvers: int,
    reason_required: bool,
    approver: Optional[str],
) -> tuple[bool, str]:
    approved_responses = [resp for resp in responses if resp["approved"]]
    if approver:
        approved_responses = [
            resp
            for resp in approved_responses
            if approver in _approval_actor_labels(resp["content"])
        ]
        if not approved_responses:
            return False, f"no matching approval from '{approver}' was recorded"

    if required_roles:
        required_roles_lower = {role.lower() for role in required_roles}
        approved_responses = [
            resp
            for resp in approved_responses
            if _approval_actor_labels(resp["content"]) & required_roles_lower
        ]
        if not approved_responses:
            return False, (
                "no approved response matched the required role set "
                f"{sorted(required_roles_lower)}"
            )

    if minimum_approvers > 1:
        unique_approvers = {
            tuple(sorted(_approval_actor_labels(resp["content"])))
            for resp in approved_responses
            if _approval_actor_labels(resp["content"])
        }
        if len(unique_approvers) < minimum_approvers:
            return False, (
                f"only {len(unique_approvers)} approver(s) were recorded; "
                f"{minimum_approvers} are required"
            )

    if reason_required:
        request_has_reason = any(
            isinstance(req["content"].get("reason"), str) and req["content"]["reason"].strip()
            for req in requests
        )
        response_has_reason = any(
            isinstance(resp["content"].get("reason"), str) and resp["content"]["reason"].strip()
            for resp in approved_responses
        )
        if not (request_has_reason or response_has_reason):
            return False, "approval reason was required but not recorded"

    if not approved_responses:
        return False, "no approved response was recorded"

    return True, ""


def _tool_event_matches_rule(step: dict, applies_at: Optional[str | list[str]]) -> bool:
    kind = _step_kind(step)
    if isinstance(applies_at, list):
        return any(_tool_event_matches_rule(step, item) for item in applies_at)
    if applies_at == "tool_response":
        return kind == "tool.response"
    if applies_at == "tool_call":
        return kind in {"tool.call", "tool.use"} or kind.startswith("tool.call")
    return kind.startswith("tool.")


def _matches_required_action(step: dict, required_action: str) -> bool:
    required_lower = required_action.lower()
    if _is_approval_keyword(required_lower):
        return _matches_named_action(step, required_lower) or _step_satisfies_approval(step)
    if "handoff" in required_lower or "escalat" in required_lower:
        return _step_kind(step) == "agent.handoff" or required_lower in _content_str(step)
    return _matches_named_action(step, required_lower)


def _has_error(step: dict) -> bool:
    """Determine if a step contains an error signal."""
    kind = step.get("kind", "")
    if kind in ("llm.error", "http.error"):
        return True

    content = step.get("content", {})
    if not isinstance(content, dict):
        return False

    # Direct error keys
    for key in _ERROR_KEYS:
        if key in content:
            return True

    # status_code >= 400
    if isinstance(content.get("status_code"), int) and content["status_code"] >= 400:
        return True

    # success == False
    if content.get("success") is False:
        return False  # success=False is explicit — not always a continuation error

    # Text scan for error phrases in string values
    content_text = _content_str(step)
    for phrase in ("\"error\":", "\"exception\":", "traceback", "error occurred"):
        if phrase in content_text:
            return True

    return False


def _extract_numbers(content: dict) -> list[tuple[str, float]]:
    """Extract all (key_path, numeric_value) pairs from a content dict."""
    results = []
    for key, val in _flatten_kv(content):
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            results.append((key, float(val)))
    return results


def _find_matching_numeric_field(content: dict, field_name: str) -> Optional[tuple[str, float]]:
    """Return the first numeric field whose key path matches the requested field."""
    field_lower = field_name.lower()
    for key, val in _extract_numbers(content):
        key_lower = key.lower()
        key_leaf = key_lower.split(".")[-1].split("[")[0]
        if field_lower == key_leaf or field_lower in key_lower:
            return key, val
    return None


def _key_matches_constraints(key: str) -> bool:
    """Return True if the key path suggests a constraint value."""
    key_lower = key.lower()
    return any(kw in key_lower for kw in _CONSTRAINT_KEYWORDS)


def _key_matches_commitment(key: str) -> bool:
    """Return True if the key path suggests a committed amount."""
    key_lower = key.lower()
    return any(kw in key_lower for kw in {"amount", "value", "total", "sum", "price", "cost"})


def _content_mentions(step: dict, terms: set[str]) -> bool:
    text = _content_str(step)
    return any(term in text for term in terms)


def _extract_entity_ids(steps: list[dict]) -> set[str]:
    """Extract likely entity identifier values (account IDs, transaction IDs, etc.)."""
    ids = set()
    for step in steps:
        content = step.get("content", {})
        for key, val in _flatten_kv(content):
            key_leaf = key.split(".")[-1].split("[")[0]
            if key_leaf in _ENTITY_ID_EXEMPT_KEYS:
                continue
            if _ID_KEY_PATTERNS.search(key_leaf) and isinstance(val, str) and len(val) >= 4:
                ids.add(val)
            elif isinstance(val, str) and _ID_VALUE_PATTERNS.match(val):
                ids.add(val)
    return ids


def _policy_flag_kwargs(rule) -> dict:
    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "policy_type": rule.type,
        "policy_mode": rule.mode or "detect",
        "policy_applies_at": rule.applies_at,
    }


# ── The Analyzer ──────────────────────────────────────────────────────────────

class FaultAnalyzer:
    """
    Fault detector for policy and agent execution risks.

    Usage:
        analyzer = FaultAnalyzer(policy=policy)  # policy may be None
        result = analyzer.analyze(steps_jsonl_string)
        analysis_json = result.to_json()
    """

    def __init__(self, policy: Optional[EPIPolicy] = None):
        self.policy = policy

    def analyze(self, steps_jsonl: str) -> AnalysisResult:
        """
        Run all detection passes and return an AnalysisResult.

        Args:
            steps_jsonl: Newline-delimited JSON (one step per line).

        Returns:
            AnalysisResult — never raises.
        """
        steps = self._parse_steps(steps_jsonl)
        result = AnalysisResult(policy=self.policy, steps=steps)

        if not steps:
            return result

        flags: list[FaultFlag] = []

        # Run passes — each is individually guarded
        try:
            flags.extend(self._pass1_error_continuation(steps))
        except Exception:
            pass

        try:
            flags.extend(self._pass2_constraint_violation(steps))
        except Exception:
            pass

        if self.policy:
            try:
                flags.extend(self._pass3_sequence_violation(steps))
            except Exception:
                pass

            try:
                flags.extend(self._pass4_threshold_violation(steps))
            except Exception:
                pass

            try:
                flags.extend(self._pass5_prohibition_violation(steps))
            except Exception:
                pass

            try:
                flags.extend(self._pass7_approval_guard_violation(steps))
            except Exception:
                pass

            try:
                flags.extend(self._pass9_tool_permission_guard(steps))
            except Exception:
                pass

        try:
            flags.extend(self._pass6_agent_approval_gap(steps))
        except Exception:
            pass

        try:
            flags.extend(self._pass8_context_drop(steps))
        except Exception:
            pass

        # Rank: policy violations first, then by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        policy_first = sorted(
            flags,
            key=lambda f: (
                0 if f.fault_type == "POLICY_VIOLATION" else 1,
                severity_order.get(f.severity, 9),
                f.step_index,
            )
        )

        if policy_first:
            result.primary_fault = policy_first[0]
            result.secondary_flags = policy_first[1:]

        return result

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_steps(self, steps_jsonl: str) -> list[dict]:
        steps = []
        for i, line in enumerate(steps_jsonl.strip().splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # Normalise: ensure index field exists
                if "index" not in obj:
                    obj["index"] = i
                steps.append(obj)
            except json.JSONDecodeError:
                pass
        return steps

    # ── Pass 1: Error Continuation ─────────────────────────────────────────────

    def _pass1_error_continuation(self, steps: list[dict]) -> list[FaultFlag]:
        """
        Flag steps where a tool returned an error and the next step continued
        as if nothing happened (no retry, no error reference, no fallback).
        """
        flags = []
        for i, step in enumerate(steps[:-1]):
            if not _has_error(step):
                continue

            next_step = steps[i + 1]
            next_content_str = _content_str(next_step)

            # Check if next step references the error at all
            references_error = any(
                phrase in next_content_str
                for phrase in ("error", "retry", "failed", "exception", "fallback", "skip")
            )

            # Check if next step is itself an error/retry (acceptable)
            next_is_error = _has_error(next_step) or next_step.get("kind", "").endswith(".error")

            if not references_error and not next_is_error:
                step_num = step.get("index", i) + 1
                next_num = next_step.get("index", i + 1) + 1
                flags.append(FaultFlag(
                    step_index=step.get("index", i),
                    fault_type="HEURISTIC_OBSERVATION",
                    severity="medium",
                    plain_english=(
                        f"Step {step_num} returned an error signal. "
                        f"Step {next_num} continued without referencing or handling the error."
                    ),
                    fault_chain=[
                        {
                            "step_index": step.get("index", i),
                            "step_number": step_num,
                            "role": "error_source",
                            "detail": f"Kind: {step.get('kind', 'unknown')}",
                        },
                        {
                            "step_index": next_step.get("index", i + 1),
                            "step_number": next_num,
                            "role": "continuation_without_handling",
                            "detail": f"Kind: {next_step.get('kind', 'unknown')}",
                        },
                    ],
                ))
        return flags

    # ── Pass 2: Constraint Violation ──────────────────────────────────────────

    def _pass2_constraint_violation(self, steps: list[dict]) -> list[FaultFlag]:
        """
        Flag when a numerical constraint established at step M is exceeded at step N.

        Builds a constraint register incrementally. Each entry:
            key_path → (value, step_index, keyword_context)
        """
        flags = []
        constraint_register: dict[str, tuple[float, int, str]] = {}

        # Also apply policy constraint_guard rules
        policy_constraint_rules = (
            self.policy.rules_of_type("constraint_guard") if self.policy else []
        )

        for step in steps:
            content = step.get("content", {})
            if not isinstance(content, dict):
                continue
            step_idx = step.get("index", 0)
            step_num = step_idx + 1
            numbers = _extract_numbers(content)

            # Record constraint values
            for key, val in numbers:
                if _key_matches_constraints(key):
                    key_leaf = key.split(".")[-1]
                    constraint_register[key_leaf] = (val, step_idx, key)

                    # Also check policy watch_for lists
                    for rule in policy_constraint_rules:
                        if rule.watch_for:
                            for watch_term in rule.watch_for:
                                if watch_term.lower() in key.lower():
                                    constraint_register[f"__policy_{rule.id}_{watch_term}"] = (
                                        val, step_idx, key
                                    )

            # Check for commitment violations against registered constraints
            content_str_lower = _content_str(step)
            is_commitment = _content_mentions(step, _COMMITMENT_KEYWORDS)
            if not is_commitment:
                continue

            for key, committed_val in numbers:
                if not _key_matches_commitment(key):
                    continue

                # Check against each registered constraint
                for c_key, (c_val, c_step_idx, c_key_path) in constraint_register.items():
                    # Don't compare constraint to itself
                    if c_step_idx >= step_idx:
                        continue

                    if committed_val > c_val * 1.001:  # 0.1% tolerance for float precision
                        c_step_num = c_step_idx + 1

                        # Check if a policy rule matches
                        rule_id = rule_name = None
                        policy_rule = None
                        if c_key.startswith("__policy_"):
                            parts = c_key.split("_")
                            if len(parts) >= 3:
                                rule_id = parts[2]
                                matching = [r for r in policy_constraint_rules if r.id == rule_id]
                                if matching:
                                    policy_rule = matching[0]
                                    rule_name = policy_rule.name

                        fault_type = "POLICY_VIOLATION" if rule_id else "HEURISTIC_OBSERVATION"
                        severity = "critical" if rule_id else "high"

                        flags.append(FaultFlag(
                            step_index=step_idx,
                            fault_type=fault_type,
                            severity=severity,
                            rule_id=rule_id,
                            rule_name=rule_name,
                            plain_english=(
                                f"At step {c_step_num} the agent received a constraint value "
                                f"of {c_val:,.2f} (field: {c_key_path.split('.')[-1]}). "
                                f"At step {step_num} a committed value of {committed_val:,.2f} "
                                f"exceeded this limit."
                                + (f" Rule {rule_id} ({rule_name}) was violated." if rule_id else "")
                            ),
                            fault_chain=[
                                {
                                    "step_index": c_step_idx,
                                    "step_number": c_step_num,
                                    "role": "constraint_source",
                                    "detail": f"Constraint value {c_val:,.2f} established",
                                },
                                {
                                    "step_index": step_idx,
                                    "step_number": step_num,
                                    "role": "violation_point",
                                    "detail": f"Committed value {committed_val:,.2f} exceeds constraint",
                                },
                            ],
                            **(_policy_flag_kwargs(policy_rule) if policy_rule else {}),
                        ))
                        # One flag per commitment step — break inner loops
                        break
                else:
                    continue
                break

        return flags

    # ── Pass 3: Sequence Violation (policy only) ──────────────────────────────

    def _pass3_sequence_violation(self, steps: list[dict]) -> list[FaultFlag]:
        """
        Flag when action B occurs without action A having occurred first.
        Only runs when policy contains sequence_guard rules.
        """
        if not self.policy:
            return []

        flags = []
        sequence_rules = self.policy.rules_of_type("sequence_guard")

        for rule in sequence_rules:
            if not rule.required_before or not rule.must_call:
                continue

            required_before = rule.required_before.lower()
            must_call = rule.must_call.lower()

            for i, step in enumerate(steps):

                # Only check tool.call steps for sequence violations —
                # keywords in workflow names / messages are not action triggers.
                if not _is_action_trigger_step(step):
                    continue

                # Check if this step is the "B" action (the one that requires a predecessor)
                b_present = _matches_named_action(step, required_before)
                if not b_present:
                    continue

                # Search backwards for the "A" action
                a_found = any(
                    _matches_required_action(prev, must_call)
                    for prev in steps[:i]
                )

                if not a_found:
                    step_idx = step.get("index", i)
                    flags.append(FaultFlag(
                        step_index=step_idx,
                        fault_type="POLICY_VIOLATION",
                        severity=rule.severity,
                        plain_english=(
                            f"At step {step_idx + 1}, action '{required_before}' was executed. "
                            f"Rule {rule.id} ({rule.name}) requires '{must_call}' to be called "
                            f"first. No prior '{must_call}' call was found in the execution record."
                        ),
                        fault_chain=[
                            {
                                "step_index": step_idx,
                                "step_number": step_idx + 1,
                                "role": "violation_point",
                                "detail": (
                                    f"'{required_before}' executed without prior '{must_call}'"
                                ),
                            },
                        ],
                        **_policy_flag_kwargs(rule),
                    ))

        return flags

    # ── Pass 4: Context Drop ──────────────────────────────────────────────────

    def _pass4_threshold_violation(self, steps: list[dict]) -> list[FaultFlag]:
        """
        Flag when a value exceeds a policy threshold and the required action
        does not appear before or at the violating step.
        """
        if not self.policy:
            return []

        flags = []
        threshold_rules = self.policy.rules_of_type("threshold_guard")

        for rule in threshold_rules:
            if (
                rule.threshold_value is None
                or not rule.required_action
            ):
                continue

            candidate_fields = []
            if rule.threshold_field:
                candidate_fields.append(rule.threshold_field)
            if rule.watch_for:
                candidate_fields.extend(rule.watch_for)
            if not candidate_fields:
                continue

            breach_source = None

            for i, step in enumerate(steps):
                content = step.get("content", {})
                if not isinstance(content, dict):
                    content = {}

                matched = None
                for candidate in candidate_fields:
                    matched = _find_matching_numeric_field(content, candidate)
                    if matched:
                        break
                current_breach = None
                if matched:
                    key_path, observed_value = matched
                    if observed_value > rule.threshold_value:
                        current_breach = (step.get("index", i), key_path, observed_value)
                        breach_source = current_breach

                if breach_source is None:
                    continue

                if not _is_action_trigger_step(step):
                    continue

                action_found = any(
                    _matches_required_action(prev, rule.required_action)
                    for prev in steps[: i + 1]
                )
                if action_found:
                    continue

                source_idx, source_key_path, source_value = breach_source
                step_idx = step.get("index", i)
                fault_chain = [
                    {
                        "step_index": source_idx,
                        "step_number": source_idx + 1,
                        "role": "threshold_source",
                        "detail": (
                            f"Observed {source_value:,.2f} in '{source_key_path}' above "
                            f"threshold {rule.threshold_value:,.2f}"
                        ),
                    },
                ]
                if step_idx != source_idx:
                    fault_chain.append(
                        {
                            "step_index": step_idx,
                            "step_number": step_idx + 1,
                            "role": "violation_point",
                            "detail": f"Agent proceeded without '{rule.required_action}'",
                        }
                    )

                flags.append(FaultFlag(
                    step_index=step_idx,
                    fault_type="POLICY_VIOLATION",
                    severity=rule.severity,
                    plain_english=(
                        f"By step {step_idx + 1}, field '{source_key_path}' had value {source_value:,.2f}, "
                        f"which exceeded the threshold {rule.threshold_value:,.2f}. "
                        f"Rule {rule.id} ({rule.name}) requires '{rule.required_action}' before proceeding."
                    ),
                    fault_chain=fault_chain,
                    **_policy_flag_kwargs(rule),
                ))
                break

        return flags

    def _pass5_prohibition_violation(self, steps: list[dict]) -> list[FaultFlag]:
        """Flag when a prohibited pattern appears in the recorded content."""
        if not self.policy:
            return []

        flags = []
        prohibition_rules = self.policy.rules_of_type("prohibition_guard")

        for rule in prohibition_rules:
            if not rule.prohibited_pattern:
                continue

            try:
                pattern = re.compile(rule.prohibited_pattern)
            except re.error:
                continue

            for i, step in enumerate(steps):
                content_text = _content_str(step)
                match = pattern.search(content_text)
                if not match:
                    continue

                step_idx = step.get("index", i)
                flags.append(FaultFlag(
                    step_index=step_idx,
                    fault_type="POLICY_VIOLATION",
                    severity=rule.severity,
                    plain_english=(
                        f"At step {step_idx + 1}, content matched prohibited pattern "
                        f"'{rule.prohibited_pattern}'. Rule {rule.id} ({rule.name}) was violated."
                    ),
                    fault_chain=[
                        {
                            "step_index": step_idx,
                            "step_number": step_idx + 1,
                            "role": "prohibited_output",
                            "detail": f"Matched prohibited content: {match.group(0)}",
                        },
                    ],
                    **_policy_flag_kwargs(rule),
                ))

        return flags

    def _pass6_agent_approval_gap(self, steps: list[dict]) -> list[FaultFlag]:
        """
        Flag when an agent executes a decision/action while approval is still pending
        or after an approval response explicitly rejected that action.
        """
        flags = []

        approval_requests: list[dict] = []
        approval_responses: list[dict] = []

        for i, step in enumerate(steps):
            kind = _step_kind(step)
            step_idx = step.get("index", i)
            action = _get_primary_action(step)

            if kind == "agent.approval.request":
                approval_requests.append({
                    "step": step,
                    "index": step_idx,
                    "action": action,
                })
                continue

            if kind == "agent.approval.response":
                approval_responses.append({
                    "step": step,
                    "index": step_idx,
                    "action": action,
                    "approved": bool(step.get("content", {}).get("approved")),
                })
                continue

            if not _is_action_trigger_step(step) or not action:
                continue

            matching_requests = [
                req for req in approval_requests
                if req["index"] < step_idx
                and req["action"]
                and (req["action"] in action or action in req["action"])
            ]
            if not matching_requests:
                continue

            latest_request = matching_requests[-1]
            matching_responses = [
                resp for resp in approval_responses
                if resp["index"] > latest_request["index"]
                and resp["index"] < step_idx
                and resp["action"]
                and (resp["action"] in action or action in resp["action"])
            ]

            if not matching_responses:
                flags.append(FaultFlag(
                    step_index=step_idx,
                    fault_type="HEURISTIC_OBSERVATION",
                    severity="high",
                    plain_english=(
                        f"At step {step_idx + 1}, action '{action}' executed while a prior approval "
                        f"request was still pending."
                    ),
                    fault_chain=[
                        {
                            "step_index": latest_request["index"],
                            "step_number": latest_request["index"] + 1,
                            "role": "approval_requested",
                            "detail": f"Approval requested for '{latest_request['action']}'",
                        },
                        {
                            "step_index": step_idx,
                            "step_number": step_idx + 1,
                            "role": "violation_point",
                            "detail": f"Action '{action}' executed before approval response",
                        },
                    ],
                ))
                continue

            latest_response = matching_responses[-1]
            if latest_response["approved"] is False:
                flags.append(FaultFlag(
                    step_index=step_idx,
                    fault_type="HEURISTIC_OBSERVATION",
                    severity="high",
                    plain_english=(
                        f"At step {step_idx + 1}, action '{action}' executed after an approval response "
                        f"rejected that action."
                    ),
                    fault_chain=[
                        {
                            "step_index": latest_request["index"],
                            "step_number": latest_request["index"] + 1,
                            "role": "approval_requested",
                            "detail": f"Approval requested for '{latest_request['action']}'",
                        },
                        {
                            "step_index": latest_response["index"],
                            "step_number": latest_response["index"] + 1,
                            "role": "approval_rejected",
                            "detail": f"Approval rejected for '{latest_response['action']}'",
                        },
                        {
                            "step_index": step_idx,
                            "step_number": step_idx + 1,
                            "role": "violation_point",
                            "detail": f"Action '{action}' executed despite rejection",
                        },
                    ],
                ))

        return flags

    def _pass7_approval_guard_violation(self, steps: list[dict]) -> list[FaultFlag]:
        """Policy-only approval guard for named actions."""
        if not self.policy:
            return []

        flags = []
        approval_rules = self.policy.rules_of_type("approval_guard")

        for rule in approval_rules:
            if not rule.approval_action:
                continue

            action_name = rule.approval_action.lower()
            approver = rule.approved_by.lower() if rule.approved_by else None
            approval_policy = (
                self.policy.approval_policy(rule.approval_policy_ref)
                if rule.approval_policy_ref else None
            )

            for i, step in enumerate(steps):
                if not _is_action_trigger_step(step):
                    continue
                if not _matches_named_action(step, action_name):
                    continue

                if rule.approval_policy_ref and approval_policy is None:
                    step_idx = step.get("index", i)
                    flags.append(FaultFlag(
                        step_index=step_idx,
                        fault_type="POLICY_VIOLATION",
                        severity=rule.severity,
                        plain_english=(
                            f"At step {step_idx + 1}, action '{action_name}' executed under rule "
                            f"{rule.id} ({rule.name}), but the referenced approval policy "
                            f"'{rule.approval_policy_ref}' was not defined."
                        ),
                        fault_chain=[
                            {
                                "step_index": step_idx,
                                "step_number": step_idx + 1,
                                "role": "policy_reference_missing",
                                "detail": f"Missing approval policy '{rule.approval_policy_ref}'",
                            },
                        ],
                        **_policy_flag_kwargs(rule),
                    ))
                    continue

                requests = _matching_approval_requests(steps, action_name=action_name, before_index=i + 1)
                responses = _matching_approval_responses(steps, action_name=action_name, before_index=i + 1)

                if approval_policy is not None:
                    approved, failure_reason = _approval_responses_satisfy_policy(
                        responses,
                        requests,
                        required_roles=approval_policy.required_roles,
                        minimum_approvers=approval_policy.minimum_approvers,
                        reason_required=approval_policy.reason_required,
                        approver=approver,
                    )
                else:
                    approved = any(
                        _step_satisfies_approval(prev, action_name=action_name, approver=approver)
                        for prev in steps[: i + 1]
                    )
                    failure_reason = "no matching approved response was recorded"

                if approved:
                    continue

                step_idx = step.get("index", i)
                detail = f"'{action_name}' executed without approval"
                if approval_policy is not None:
                    detail = (
                        f"'{action_name}' executed without satisfying approval policy "
                        f"'{approval_policy.approval_id}'"
                    )
                flags.append(FaultFlag(
                    step_index=step_idx,
                    fault_type="POLICY_VIOLATION",
                    severity=rule.severity,
                    plain_english=(
                        f"At step {step_idx + 1}, action '{action_name}' executed without an approved "
                        f"approval response. Rule {rule.id} ({rule.name}) requires explicit approval first."
                        + (f" Requirement not met: {failure_reason}." if failure_reason else "")
                    ),
                    fault_chain=[
                        {
                            "step_index": step_idx,
                            "step_number": step_idx + 1,
                            "role": "violation_point",
                            "detail": detail,
                        },
                    ],
                    **_policy_flag_kwargs(rule),
                ))

        return flags

    def _pass9_tool_permission_guard(self, steps: list[dict]) -> list[FaultFlag]:
        """Policy-only tool allow/deny controls."""
        if not self.policy:
            return []

        flags = []
        tool_rules = self.policy.rules_of_type("tool_permission_guard")

        for rule in tool_rules:
            allowed_tools = {tool.lower() for tool in (rule.allowed_tools or [])}
            denied_tools = {tool.lower() for tool in (rule.denied_tools or [])}
            if not allowed_tools and not denied_tools:
                continue

            for i, step in enumerate(steps):
                if not _tool_event_matches_rule(step, rule.applies_at):
                    continue

                tool_name = _get_primary_action(step)
                if not tool_name:
                    continue

                violation_reason = None
                if tool_name in denied_tools:
                    violation_reason = f"tool '{tool_name}' is explicitly denied"
                elif allowed_tools and tool_name not in allowed_tools:
                    violation_reason = (
                        f"tool '{tool_name}' is not in the allowlist {sorted(allowed_tools)}"
                    )

                if not violation_reason:
                    continue

                step_idx = step.get("index", i)
                flags.append(FaultFlag(
                    step_index=step_idx,
                    fault_type="POLICY_VIOLATION",
                    severity=rule.severity,
                    plain_english=(
                        f"At step {step_idx + 1}, tool '{tool_name}' was used. "
                        f"Rule {rule.id} ({rule.name}) was violated because {violation_reason}."
                    ),
                    fault_chain=[
                        {
                            "step_index": step_idx,
                            "step_number": step_idx + 1,
                            "role": "violation_point",
                            "detail": violation_reason,
                        },
                    ],
                    **_policy_flag_kwargs(rule),
                ))

        return flags

    def _pass8_context_drop(self, steps: list[dict]) -> list[FaultFlag]:
        """
        Flag when entity identifiers established in the first third of execution
        vanish completely from the final third.

        Only fires when there are enough steps to make the comparison meaningful.
        """
        flags = []
        if len(steps) < 8:
            return flags

        split_a = max(1, len(steps) // 3)
        split_b = len(steps) - split_a

        early_steps = steps[:split_a]
        late_steps = steps[split_b:]

        early_ids = _extract_entity_ids(early_steps)
        if not early_ids:
            return flags

        late_str = " ".join(_content_str(s) for s in late_steps).lower()

        for entity_id in early_ids:
            if len(entity_id) < 4:
                continue
            if entity_id.lower() not in late_str:
                # Find the last step where this ID appeared
                last_seen_idx = 0
                for j, step in enumerate(steps[:split_b]):
                    if entity_id.lower() in _content_str(step).lower():
                        last_seen_idx = step.get("index", j)

                flags.append(FaultFlag(
                    step_index=last_seen_idx,
                    fault_type="HEURISTIC_OBSERVATION",
                    severity="low",
                    plain_english=(
                        f"Entity identifier '{entity_id}' appeared in the early execution steps "
                        f"but was absent from the final {split_a} steps. "
                        f"This may indicate the agent lost track of the original context."
                    ),
                    fault_chain=[
                        {
                            "step_index": last_seen_idx,
                            "step_number": last_seen_idx + 1,
                            "role": "last_known_reference",
                            "detail": f"Last step where '{entity_id}' was present",
                        },
                    ],
                ))

        return flags
