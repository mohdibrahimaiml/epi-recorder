"""
Score a .epi artifact against the Decision-Grade Evidence Profile (content, not crypto).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from epi_core.container import EPIContainer

_DEFAULT_PROFILE = Path(__file__).resolve().parent.parent / "docs" / "evidence-profile" / "v0.1.json"


def load_evidence_profile(path: Path | None = None) -> dict[str, Any]:
    p = path or _DEFAULT_PROFILE
    return json.loads(Path(p).read_text(encoding="utf-8"))


def score_artifact(
    epi_path: Path,
    *,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Return a content-score report for decision-grade readiness.

    Does not replace epi verify — use both: crypto verify + content score.
    """
    profile = profile or load_evidence_profile()
    weights = (profile.get("scoring") or {}).get("weights") or {}
    threshold = float((profile.get("scoring") or {}).get("pass_threshold") or 0.7)

    members = set(EPIContainer.list_members(epi_path))
    manifest = EPIContainer.read_manifest(epi_path)
    try:
        steps = EPIContainer.read_steps(epi_path)
    except Exception:
        steps = []

    kinds = {
        str(s.get("kind") or s.get("type") or "").lower()
        for s in steps
        if isinstance(s, dict)
    }

    checks: dict[str, bool] = {}
    checks["has_steps"] = "steps.jsonl" in members and len(steps) > 0
    decision_groups = profile.get("required_step_kinds_any_of") or []
    has_decision = False
    for group in decision_groups:
        # first group = decision-like, second = session/llm scaffolding
        if any(g.lower() in kinds for g in group):
            # count decision group as the "decision" weight
            if group is decision_groups[0] or any(
                x in ("agent.decision", "decision") for x in group
            ):
                has_decision = True
            break
    # More precise: first any_of group is decision-ish
    if decision_groups:
        has_decision = any(g.lower() in kinds for g in decision_groups[0])
    checks["has_decision_kind"] = has_decision
    checks["has_analysis"] = "analysis.json" in members
    checks["has_signature"] = bool(manifest.signature)
    try:
        from epi_core.review import read_review

        rev = read_review(epi_path)
        checks["has_bound_review"] = bool(
            rev
            and getattr(rev, "artifact_binding", None)
            and getattr(rev, "review_signature", None)
        )
    except Exception:
        checks["has_bound_review"] = False

    score = 0.0
    detail = []
    for key, weight in weights.items():
        ok = bool(checks.get(key))
        score += float(weight) if ok else 0.0
        detail.append({"check": key, "ok": ok, "weight": weight})

    return {
        "profile_id": profile.get("profile_id"),
        "profile_version": profile.get("version"),
        "score": round(score, 3),
        "pass": score >= threshold,
        "threshold": threshold,
        "checks": checks,
        "detail": detail,
        "step_kinds_seen": sorted(k for k in kinds if k),
        "member_count": len(members),
    }
