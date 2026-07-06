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
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AIUC1DomainStatus:
    """Status of a single AIUC-1 trust domain within an EPI artifact."""

    domain: str
    label: str
    status: str
    evidence: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


_REDACTION_PLACEHOLDER_RE = re.compile(
    r"\*\*\*REDACTED\*\*\*"
    r":(?P<description>[^:]+)"
    r":HMAC-SHA256"
    r":(?P<hex>[a-f0-9]{64})"
    r"\*\*\*"
)


_DOMAIN_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "A": {
        "name": "Data & Privacy",
        "evidence_keys": [
            "redaction_verifiable",
            "redaction_coverage",
            "redaction_format_valid",
            "environment_isolated",
        ],
    },
    "B": {
        "name": "Security",
        "evidence_keys": [
            "signature_valid",
            "integrity_ok",
            "scitt_receipt_present",
            "chain_ok",
        ],
    },
    "C": {
        "name": "Safety",
        "evidence_keys": [
            "chain_ok",
            "sequence_ok",
            "timestamp_monotonic",
        ],
    },
    "D": {
        "name": "Reliability",
        "evidence_keys": [
            "completeness_ok",
            "error_steps_present",
        ],
    },
    "E": {
        "name": "Accountability",
        "evidence_keys": [
            "signature_valid",
            "identity_known",
            "review_bound_to_artifact",
            "review_signed",
            "policy_present",
        ],
    },
    "F": {
        "name": "Society",
        "evidence_keys": [
            "analysis_has_findings",
            "analysis_passes_complete",
            "redaction_audit_trail",
        ],
    },
}


_SENSITIVE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"[a-z]{2,3}-[a-zA-Z0-9]{32,}",
        r"Bearer\s+[A-Za-z0-9_\-.]{20,}",
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",
        r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
    ]
]

_REDACTION_CATEGORIES: dict[str, list[str]] = {
    "api_key": ["api key", "token", "bearer", "access key", "secret key", "github"],
    "pii": ["email", "phone", "ssn", "social security", "card", "credit", "amex"],
    "credential": ["password", "connection string", "private key", "database", "jwt"],
}


def _detect_redaction_categories(steps: list[dict] | None) -> set[str]:
    if not steps:
        return set()
    categories: set[str] = set()
    for step in steps:
        text = str(step.get("content", {}))
        for m in _REDACTION_PLACEHOLDER_RE.finditer(text):
            desc = m.group("description").lower()
            for cat, keywords in _REDACTION_CATEGORIES.items():
                if any(kw in desc for kw in keywords):
                    categories.add(cat)
                    break
    return categories


def map_verification_to_aiuc1(
    report: dict,
    manifest: Any | None = None,
    steps: list[dict] | None = None,
    epi_path: Path | None = None,
) -> dict[str, AIUC1DomainStatus]:
    facts = report.get("facts", {})
    identity = report.get("identity", {})

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
        "policy_present": _has_file_in_manifest(manifest, "policy.json", epi_path),
        "environment_isolated": _has_file_in_manifest(manifest, "environment.json", epi_path),
        "timestamp_monotonic": _check_timestamp_monotonicity(steps),
        "error_steps_present": _detect_error_steps(steps),
        "redaction_verifiable": _validate_redaction_quality(steps),
        "redaction_coverage": _check_redaction_coverage(steps),
        "redaction_format_valid": _validate_redaction_placeholders(steps),
        "review_bound_to_artifact": _check_review_binding(epi_path, manifest),
        "review_signed": _check_review_signed(epi_path),
        "analysis_has_findings": _check_analysis_has_findings(manifest, epi_path),
        "analysis_passes_complete": _check_analysis_passes_complete(manifest, epi_path),
        "redaction_audit_trail": _check_redaction_completeness(steps),
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


def _has_file_in_manifest(
    manifest: Any | None, filename: str, epi_path: Path | None = None
) -> bool:
    if manifest is not None:
        file_manifest = getattr(manifest, "file_manifest", None) or {}
        if any(key == filename or key.endswith(f"/{filename}") for key in file_manifest.keys()):
            return True
    if epi_path is not None:
        try:
            from epi_core.container import EPIContainer
            members = EPIContainer.list_members(epi_path)
            return filename in members
        except Exception:
            pass
    return False


def _validate_redaction_quality(steps: list[dict] | None) -> bool:
    if not steps:
        return False
    found = 0
    for step in steps:
        text = str(step.get("content", {}))
        for m in _REDACTION_PLACEHOLDER_RE.finditer(text):
            hex_val = m.group("hex")
            if len(hex_val) == 64 and all(c in "0123456789abcdef" for c in hex_val):
                found += 1
    return found >= 1


def _validate_redaction_placeholders(steps: list[dict] | None) -> bool:
    if not steps:
        return False
    redacted_total = 0
    well_formed = 0
    for step in steps:
        text = str(step.get("content", {}))
        occurrences = text.count("***REDACTED")
        if occurrences == 0:
            continue
        redacted_total += occurrences
        well_formed += len(_REDACTION_PLACEHOLDER_RE.findall(text))
    if redacted_total == 0:
        return False
    return well_formed == redacted_total


def _check_redaction_coverage(steps: list[dict] | None) -> bool:
    if not steps:
        return False
    categories = _detect_redaction_categories(steps)
    return len(categories) >= 1


def _check_redaction_completeness(steps: list[dict] | None) -> bool:
    if not steps:
        return False
    categories = _detect_redaction_categories(steps)
    return len(categories) >= 2


def _check_review_binding(epi_path: Path | None, manifest: Any | None) -> bool:
    if epi_path is None:
        return False
    try:
        from epi_core.review import build_artifact_binding, read_review_records
    except ImportError:
        return False
    try:
        expected_binding = build_artifact_binding(epi_path)
        records = read_review_records(epi_path)
        for record in records:
            if record.artifact_binding is not None:
                if record.artifact_binding == expected_binding:
                    return True
        return False
    except Exception:
        return False


def _check_review_signed(epi_path: Path | None) -> bool:
    if epi_path is None:
        return False
    try:
        from epi_core.review import read_review_records
        records = read_review_records(epi_path)
        for record in records:
            if record.review_signature:
                return True
        return False
    except Exception:
        return False


def _read_analysis_from_artifact(manifest: Any | None, epi_path: Path | None) -> dict | None:
    if epi_path is not None:
        try:
            from epi_core.container import EPIContainer
            data = EPIContainer.read_member_json(epi_path, "analysis.json")
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return None


def _check_analysis_has_findings(manifest: Any | None, epi_path: Path | None) -> bool:
    analysis = _read_analysis_from_artifact(manifest, epi_path)
    if analysis is None:
        return False
    if analysis.get("fault_detected") is True:
        return True
    if analysis.get("primary_fault") is not None:
        return True
    secondary = analysis.get("secondary_flags") or []
    if isinstance(secondary, list) and len(secondary) > 0:
        return True
    summary = analysis.get("summary") or {}
    if summary.get("secondary_count", 0) > 0:
        return True
    return False


def _check_analysis_passes_complete(manifest: Any | None, epi_path: Path | None) -> bool:
    analysis = _read_analysis_from_artifact(manifest, epi_path)
    if analysis is None:
        return False
    for field in ("analyzer_version", "analysis_timestamp", "coverage", "fault_detected", "summary"):
        if field not in analysis:
            return False
    coverage = analysis.get("coverage") or {}
    if coverage.get("status") != "complete":
        return False
    return True


def _detect_redaction_in_steps(steps: list[dict] | None) -> bool:
    if not steps:
        return False
    for step in steps:
        content = step.get("content", {})
        text = str(content)
        if "HMAC-SHA256" in text and "***REDACTED***" in text:
            return True
    return False


def _check_timestamp_monotonicity(steps: list[dict] | None) -> bool:
    if not steps or len(steps) < 2:
        return True
    try:
        from datetime import datetime
        has_ns = any(
            step.get("content", {}).get("timestamp_ns") is not None for step in steps
        )
        timestamps: list[int | datetime] = []
        for step in steps:
            if has_ns:
                t_ns = step.get("content", {}).get("timestamp_ns")
                if t_ns is not None:
                    timestamps.append(int(t_ns))
                else:
                    return False
            else:
                ts = step.get("timestamp")
                if isinstance(ts, str):
                    timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                elif isinstance(ts, datetime):
                    timestamps.append(ts)
                else:
                    return False
        return all(timestamps[i] <= timestamps[i + 1] for i in range(len(timestamps) - 1))
    except Exception:
        return False


def _detect_error_steps(steps: list[dict] | None) -> bool:
    if not steps:
        return False
    return any(step.get("kind", "").startswith("llm.error") for step in steps)


def aiuc1_summary(statuses: dict[str, AIUC1DomainStatus]) -> dict:
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
        "framework": "AIUC-1 (EPI's proprietary scoring methodology - not a published industry standard)",
        "overall": overall,
        "domains": domains,
        "note": (
            "Mapped to AIUC-1's six publicly declared trust domains. "
            "Specific control IDs will be added after consultation with AIUC-1."
        ),
    }
