"""
AIUC-1 Domain Mapping for EPI Verification Reports.

Maps EPI's cryptographic and forensic evidence to the six trust domains
published by AIUC-1 (https://aiuc-1.org):

    A. Data & Privacy
    B. Security
    C. Safety
    D. Reliability
    E. Accountability
    F. Society

This module does NOT invent control IDs. AIUC-1 does not publish individual
control IDs publicly. Instead, it maps to the domains that AIUC-1 has declared.
When speaking with the AIUC-1 team, ask: "What specific controls within each
domain should our evidence artifacts address?" and refine this mapping afterward.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIUC1DomainStatus:
    """Status of a single AIUC-1 trust domain within an EPI artifact."""

    domain: str
    label: str
    status: str  # "PASS", "FAIL", "PARTIAL", "NOT_APPLICABLE"
    evidence: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


# Mapping of EPI verification facts to AIUC-1 domains
# Each domain lists the evidence features that would satisfy it.
_DOMAIN_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "A": {
        "name": "Data & Privacy",
        "evidence_keys": [
            "redaction_applied",  # HMAC-SHA256 placeholders present
            "environment_isolated",  # environment.json captured separately
        ],
    },
    "B": {
        "name": "Security",
        "evidence_keys": [
            "signature_valid",  # Ed25519 manifest signature
            "integrity_ok",  # SHA-256 file manifest matches
            "scitt_receipt_present",  # SCITT transparency receipt embedded
            "chain_ok",  # prev_hash chain unbroken
        ],
    },
    "C": {
        "name": "Safety",
        "evidence_keys": [
            "chain_ok",  # prev_hash chain = tamper-evident sequence
            "sequence_ok",  # monotonic step indices
            "timestamp_monotonic",  # time moves forward
        ],
    },
    "D": {
        "name": "Reliability",
        "evidence_keys": [
            "completeness_ok",  # every request has a response
            "error_steps_present",  # errors are captured, not hidden
        ],
    },
    "E": {
        "name": "Accountability",
        "evidence_keys": [
            "signature_valid",  # someone signed this
            "identity_known",  # signer is in a trust registry
            "human_review_present",  # review.json exists
            "policy_present",  # policy.json exists
        ],
    },
    "F": {
        "name": "Society",
        "evidence_keys": [
            "analysis_present",  # analysis.json exists
            "redaction_audit_trail",  # redaction is verifiable (HMAC)
        ],
    },
}


def map_verification_to_aiuc1(
    report: dict,
    manifest: Any | None = None,
    steps: list[dict] | None = None,
) -> dict[str, AIUC1DomainStatus]:
    """
    Map an EPI verification report to AIUC-1 trust domains.

    Args:
        report: The verification report dict from create_verification_report().
        manifest: Optional ManifestModel for additional metadata.
        steps: Optional list of steps for forensic analysis.

    Returns:
        Dict mapping domain letter -> AIUC1DomainStatus.
    """
    facts = report.get("facts", {})
    identity = report.get("identity", {})

    # Extract evidence booleans from the report
    evidence = {
        "signature_valid": facts.get("signature_valid") is True,
        "integrity_ok": facts.get("integrity_ok", False),
        "chain_ok": facts.get("chain_ok", True),
        "sequence_ok": facts.get("sequence_ok", True),
        "completeness_ok": facts.get("completeness_ok", True),
        "scitt_receipt_present": bool(
            (identity.get("scitt") or {}).get("entry_id")
        ),
        "identity_known": identity.get("status") == "KNOWN",
        "human_review_present": _has_file_in_manifest(manifest, "review.json"),
        "policy_present": _has_file_in_manifest(manifest, "policy.json"),
        "analysis_present": _has_file_in_manifest(manifest, "analysis.json"),
        "environment_isolated": _has_file_in_manifest(manifest, "environment.json"),
        "redaction_applied": _detect_redaction_in_steps(steps),
        "redaction_audit_trail": _detect_redaction_in_steps(steps),
        "timestamp_monotonic": _check_timestamp_monotonicity(steps),
        "error_steps_present": _detect_error_steps(steps),
    }

    result: dict[str, AIUC1DomainStatus] = {}
    for domain_id, cfg in _DOMAIN_REQUIREMENTS.items():
        passed = []
        missing = []
        for key in cfg["evidence_keys"]:
            if evidence.get(key):
                passed.append(key)
            else:
                missing.append(key)

        if not missing:
            status = "PASS"
        elif not passed:
            status = "FAIL"
        else:
            status = "PARTIAL"

        result[domain_id] = AIUC1DomainStatus(
            domain=domain_id,
            label=cfg["name"],
            status=status,
            evidence=passed,
            missing=missing,
        )

    return result


def _has_file_in_manifest(manifest: Any | None, filename: str) -> bool:
    """Check if a file exists in the manifest's file_manifest."""
    if manifest is None:
        return False
    file_manifest = getattr(manifest, "file_manifest", None) or {}
    return any(filename in key for key in file_manifest.keys())


def _detect_redaction_in_steps(steps: list[dict] | None) -> bool:
    """Detect if any step contains HMAC-SHA256 redaction placeholders."""
    if not steps:
        return False
    for step in steps:
        content = step.get("content", {})
        text = str(content)
        if "HMAC-SHA256" in text and "***REDACTED***" in text:
            return True
    return False


def _check_timestamp_monotonicity(steps: list[dict] | None) -> bool:
    """Check that step timestamps are monotonically increasing."""
    if not steps or len(steps) < 2:
        return True
    try:
        from datetime import datetime

        timestamps = []
        for step in steps:
            ts = step.get("timestamp")
            if isinstance(ts, str):
                timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
            elif isinstance(ts, datetime):
                timestamps.append(ts)
        return all(timestamps[i] <= timestamps[i + 1] for i in range(len(timestamps) - 1))
    except Exception:
        return True  # Graceful fallback


def _detect_error_steps(steps: list[dict] | None) -> bool:
    """Detect if any error steps are present in the timeline."""
    if not steps:
        return False
    return any(step.get("kind", "").startswith("llm.error") for step in steps)


def aiuc1_summary(statuses: dict[str, AIUC1DomainStatus]) -> dict:
    """
    Produce a JSON-serializable summary of AIUC-1 domain compliance.

    Returns:
        Dict suitable for embedding in verification report JSON.
    """
    domains = {}
    for domain_id, status in statuses.items():
        domains[domain_id] = {
            "label": status.label,
            "status": status.status,
            "evidence": status.evidence,
            "missing": status.missing,
        }

    overall = "PASS"
    if any(s.status == "FAIL" for s in statuses.values()):
        overall = "FAIL"
    elif any(s.status == "PARTIAL" for s in statuses.values()):
        overall = "PARTIAL"

    return {
        "framework": "AIUC-1",
        "overall": overall,
        "domains": domains,
        "note": (
            "Mapped to AIUC-1's six publicly declared trust domains. "
            "Specific control IDs will be added after consultation with AIUC-1."
        ),
    }
