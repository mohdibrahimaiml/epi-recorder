"""
Post-seal artifact summary — compact facts for end-of-run UX.

Reads an already-sealed .epi (analysis/policy already embedded at pack time).
Never raises. Never re-runs the fault analyzer.
Does not change crypto/verify exit semantics — this is display only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any



def _shown(path: Path) -> str:
    """The path a user can paste: relative to the current folder when possible."""
    try:
        rel = Path(path).resolve().relative_to(Path.cwd().resolve())
        text = str(rel)
    except Exception:
        text = str(path)
    return f'"{text}"' if " " in text else text

def _safe_read_json(epi_path: Path, member: str) -> dict[str, Any] | None:
    try:
        from epi_core.container import EPIContainer

        data = EPIContainer.read_member_json(epi_path, member)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _safe_manifest(epi_path: Path):
    try:
        from epi_core.container import EPIContainer

        return EPIContainer.read_manifest(epi_path)
    except Exception:
        return None


def build_artifact_run_summary(
    epi_path: Path | str,
    *,
    signed: bool | None = None,
) -> dict[str, Any]:
    """
    Build a plain dict describing what a normal user needs after a run.

    Keys:
      path, exists, signed, analysis_status, policy_status, policy_id,
      mode, rules_evaluated, rules_failed, fault_detected, top_issue,
      review_required, next_hint
    """
    path = Path(epi_path)
    summary: dict[str, Any] = {
        "path": str(path),
        "name": path.name,
        "exists": path.exists(),
        "signed": signed,
        "analysis_status": None,
        "policy_status": "unknown",
        "policy_id": None,
        "mode": None,
        "rules_evaluated": None,
        "rules_failed": None,
        "fault_detected": None,
        "top_issue": None,
        "heuristic_observation_count": None,
        "detectors_failed": None,
        "review_required": None,
        "next_hint": f"epi view {_shown(path)}" if path.name else "epi view <file.epi>",
    }
    if not path.exists():
        summary["policy_status"] = "missing_file"
        return summary

    manifest = _safe_manifest(path)
    if manifest is not None:
        if signed is None:
            summary["signed"] = bool(getattr(manifest, "signature", None))
        summary["analysis_status"] = getattr(manifest, "analysis_status", None)
        if getattr(manifest, "analysis_error", None):
            summary["analysis_error"] = str(manifest.analysis_error)[:200]

    analysis = _safe_read_json(path, "analysis.json")
    policy_eval = _safe_read_json(path, "policy_evaluation.json")
    policy_doc = _safe_read_json(path, "policy.json")

    if analysis is None:
        status = summary.get("analysis_status")
        if status == "error":
            summary["policy_status"] = "analysis_error"
        elif status == "skipped":
            summary["policy_status"] = "analysis_skipped"
        else:
            summary["policy_status"] = "no_analysis"
        return summary

    summary["mode"] = analysis.get("mode")
    summary["fault_detected"] = bool(analysis.get("fault_detected"))
    # A crashed detector must not read as a clean analysis.
    summary["detectors_failed"] = len(analysis.get("detector_errors") or [])
    summary["review_required"] = bool(analysis.get("review_required"))
    summary["policy_id"] = analysis.get("policy_id") or (
        policy_doc.get("policy_id") if policy_doc else None
    )

    policy_used = bool(analysis.get("policy_used"))
    baseline = bool(policy_eval.get("baseline")) if policy_eval else False

    if policy_used and not baseline:
        summary["policy_status"] = "applied"
    elif baseline or summary["mode"] == "heuristic_only":
        summary["policy_status"] = "missing"  # no project rulebook; heuristic only
    else:
        summary["policy_status"] = "unknown"

    if policy_eval:
        summary["rules_evaluated"] = policy_eval.get("controls_evaluated")
        summary["rules_failed"] = policy_eval.get("controls_failed")
        if policy_eval.get("baseline"):
            summary["policy_status"] = "missing"

    primary = analysis.get("primary_fault")
    if isinstance(primary, dict) and primary.get("plain_english"):
        summary["top_issue"] = str(primary["plain_english"]).strip()
    elif analysis.get("verdict_short"):
        # e.g. no fault
        summary["top_issue"] = None
    elif analysis.get("summary") and isinstance(analysis["summary"], dict):
        headline = analysis["summary"].get("headline")
        if headline and analysis.get("fault_detected"):
            summary["top_issue"] = str(headline).strip()

    # Low/info heuristic observations are notes, not faults (issue #157).
    flags = [primary] if isinstance(primary, dict) else []
    flags.extend(f for f in (analysis.get("secondary_flags") or []) if isinstance(f, dict))
    summary["heuristic_observation_count"] = sum(
        1 for f in flags if str(f.get("severity", "")).lower() in ("info", "low")
    )

    if summary["review_required"] and summary["fault_detected"]:
        summary["next_hint"] = f"epi review {_shown(path)}   # or: epi view {_shown(path)}"
    else:
        summary["next_hint"] = f"epi view {_shown(path)}"

    return summary


def format_artifact_run_summary_lines(
    epi_path: Path | str,
    *,
    signed: bool | None = None,
    max_issue_len: int = 100,
) -> list[str]:
    """
    Plain-text lines for stderr / logs (no Rich markup).

    Example::

        Seal:    signed
        Policy:  applied (insurance-claim-denial-demo) — 5 rules, 1 failed
        Issue:   High-value claim needs human approval
        Next:    epi view run.epi
    """
    s = build_artifact_run_summary(epi_path, signed=signed)
    lines: list[str] = []

    if not s.get("exists"):
        return ["Seal:    (file not found)"]

    seal = "signed" if s.get("signed") else "unsigned"
    lines.append(f"Seal:    {seal}")

    ps = s.get("policy_status")
    if ps == "applied":
        pid = s.get("policy_id") or "rulebook"
        ev = s.get("rules_evaluated")
        failed = s.get("rules_failed")
        if ev is not None and failed is not None:
            lines.append(f"Policy:  applied ({pid}) — {ev} rules, {failed} failed")
        elif ev is not None:
            lines.append(f"Policy:  applied ({pid}) — {ev} rules evaluated")
        else:
            lines.append(f"Policy:  applied ({pid})")
    elif ps == "missing":
        lines.append("Policy:  missing — heuristic only (add epi_policy.json for your rules)")
    elif ps == "analysis_error":
        err = s.get("analysis_error") or "analysis failed"
        lines.append(f"Policy:  analysis error — {err}")
    elif ps == "analysis_skipped":
        lines.append("Policy:  analysis skipped for this pack")
    elif ps == "no_analysis":
        lines.append("Policy:  no analysis.json in artifact")
    else:
        lines.append(f"Policy:  {ps}")

    if s.get("fault_detected") and s.get("top_issue"):
        issue = str(s["top_issue"])
        if len(issue) > max_issue_len:
            issue = issue[: max_issue_len - 3].rstrip() + "..."
        label = "Issue:"
        lines.append(f"{label:<8} {issue}")
        if s.get("review_required"):
            lines.append("Review:  recommended before trusting this outcome")
    else:
        if s.get("heuristic_observation_count"):
            n = int(s["heuristic_observation_count"])
            noun = "observation" if n == 1 else "observations"
            lines.append(f"Finding: {n} low-severity {noun} — not a fault")
        elif s.get("mode") == "heuristic_only" or ps == "missing":
            lines.append("Finding: no heuristic issues flagged (not a compliance pass)")
        else:
            lines.append("Finding: no rule issues flagged")

    if s.get("detectors_failed"):
        lines.append(
            f"Analysis: {s['detectors_failed']} detector(s) failed — result may be incomplete"
        )

    lines.append(f"Next:    {s.get('next_hint')}")
    return lines
