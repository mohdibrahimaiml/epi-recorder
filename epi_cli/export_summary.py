"""
epi export-summary - produce a printable Decision Record for a .epi artifact.
"""
from __future__ import annotations

import html as _html
import json
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from typer.models import OptionInfo

from epi_cli.view import _resolve_epi_file
from epi_core.container import EPIContainer
from epi_core.trust import verify_embedded_manifest_signature

app = typer.Typer(help="Export a regulator-facing HTML or text Decision Record for a .epi artifact.")
console = Console()


def _resolve_option_value(value, default=None):
    return default if isinstance(value, OptionInfo) else value


def _format_ts(ts: str | None) -> str:
    if not ts:
        return "Unknown"
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(ts)


def _format_ts_short(ts: str | None) -> str:
    if not ts:
        return "Unknown"
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S")
    except Exception:
        return str(ts)


def _read_json_member(epi_path: Path, name: str) -> dict[str, Any] | None:
    try:
        payload = EPIContainer.read_member_json(epi_path, name)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _read_steps(epi_path: Path) -> list[dict[str, Any]]:
    return EPIContainer.read_steps(epi_path)


def _read_artifact_context(epi_path: Path) -> dict[str, Any]:
    return {
        "analysis": _read_json_member(epi_path, "analysis.json"),
        "policy": _read_json_member(epi_path, "policy.json"),
        "policy_evaluation": _read_json_member(epi_path, "policy_evaluation.json"),
        "review": _read_json_member(epi_path, "review.json"),
    }


def _titleize(value: str | None) -> str:
    text = str(value or "").replace("_", " ").replace("-", " ").strip()
    if not text:
        return "Unknown"
    return text[0].upper() + text[1:]


def _decision_label(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "Decision not stated"
    if "deny" in text or "declin" in text:
        return "Denied"
    if "approve" in text or "pay" in text or "accept" in text:
        return "Approved"
    if "escalat" in text or "review" in text:
        return "Escalated"
    return _titleize(text)


def _review_outcome_label(value: str | None) -> str:
    mapping = {
        "dismissed": "Human reviewer approved the decision",
        "confirmed_fault": "Human reviewer rejected the decision",
        "skipped": "Human reviewer deferred the decision",
    }
    return mapping.get(str(value or "").strip(), "No final human review outcome recorded")


def _extract_decision_step(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    for step in reversed(steps):
        if step.get("kind") == "agent.decision":
            return step
    return None


def _extract_latest_approval(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    for step in reversed(steps):
        if step.get("kind") == "agent.approval.response":
            return step
    return None


def _derive_outcome(manifest, steps: list[dict[str, Any]], review_info: dict[str, Any] | None) -> tuple[str, str]:
    latest_review = None
    if review_info and isinstance(review_info.get("reviews"), list) and review_info["reviews"]:
        latest_review = review_info["reviews"][-1]
    if isinstance(latest_review, dict):
        return _review_outcome_label(latest_review.get("outcome")), "human-reviewed"

    decision_step = _extract_decision_step(steps)
    if decision_step:
        content = decision_step.get("content") if isinstance(decision_step.get("content"), dict) else {}
        raw = content.get("decision") or content.get("action") or content.get("result")
        return _decision_label(raw), "system-recorded"

    if getattr(manifest, "analysis_status", None) == "error":
        return "Analysis failed - inspect appendix", "analysis-error"

    return "Decision record captured", "captured"


def _tone_for_outcome(outcome_state: str) -> str:
    if outcome_state == "human-reviewed":
        return "tone-approved"
    if outcome_state == "analysis-error":
        return "tone-warning"
    return "tone-neutral"


def _rule_type_label(value: str | None) -> str:
    mapping = {
        "constraint_guard": "Amount limit rule",
        "sequence_guard": "Required step rule",
        "threshold_guard": "High-value approval rule",
        "prohibition_guard": "PII-safe output rule",
        "approval_guard": "Human approval rule",
        "tool_permission_guard": "Allowed-tools rule",
    }
    return mapping.get(str(value or "").strip(), _titleize(value))


def _render_value(value: Any) -> str:
    if value is None or value == "":
        return "Not recorded"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return f"{value}"
    return str(value)


def _analysis_headline(analysis: dict[str, Any]) -> str:
    summary = analysis.get("summary")
    if isinstance(summary, dict):
        return str(summary.get("headline") or summary.get("primary_category") or "Not recorded")
    if isinstance(summary, str) and summary.strip():
        return summary
    return "Not recorded"


def _safe_excerpt(value: Any, limit: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _describe_step(step: dict[str, Any]) -> str:
    kind = str(step.get("kind") or "")
    content = step.get("content") if isinstance(step.get("content"), dict) else {}
    tool_name = content.get("tool") or content.get("name") or content.get("action")

    if kind == "tool.call":
        phrases = {
            "load_claim": "Claim file loaded for review.",
            "run_fraud_check": "Fraud check started.",
            "check_coverage": "Coverage review started.",
            "record_denial_reason": "Denial reason was documented.",
            "issue_denial_notice": "Denial notice was prepared.",
        }
        if isinstance(tool_name, str) and tool_name in phrases:
            return phrases[tool_name]
        return f"Business check started: {_titleize(str(tool_name or 'tool call'))}."

    if kind == "tool.response":
        status = content.get("status") or "recorded"
        phrases = {
            "load_claim": "Claim details were loaded successfully.",
            "run_fraud_check": "Fraud check completed.",
            "check_coverage": "Coverage check completed.",
            "record_denial_reason": "Denial reason was saved to the case.",
            "issue_denial_notice": "Denial notice was issued.",
        }
        if isinstance(tool_name, str) and tool_name in phrases:
            return phrases[tool_name]
        return f"Business check result: {_titleize(str(status))}."

    if kind == "llm.request":
        return "AI was consulted for a recommendation."

    if kind == "llm.response":
        choices = content.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else {}
            return _safe_excerpt(message.get("content") or "AI recommendation recorded.")
        return "AI recommendation recorded."

    if kind == "agent.approval.request":
        return f"Human approval requested for {_titleize(content.get('action') or 'the next step')}."

    if kind == "agent.approval.response":
        reviewer = content.get("reviewer") or "Reviewer"
        status = "approved" if content.get("approved") else "did not approve"
        return f"{reviewer} {status} {_titleize(content.get('action') or 'the requested action')}."

    if kind == "agent.decision":
        return f"Final decision recorded: {_decision_label(content.get('decision') or content.get('action'))}."

    if kind.endswith(".end"):
        return "Workflow completed."

    return _titleize(kind.replace(".", " "))


def _material_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    preferred = {
        "tool.call",
        "tool.response",
        "llm.request",
        "llm.response",
        "agent.approval.request",
        "agent.approval.response",
        "agent.decision",
        "agent.run.end",
    }
    selected = [step for step in steps if step.get("kind") in preferred]
    if not selected:
        selected = steps[:8]
    return selected[:10]


def _build_text_summary(
    epi_path: Path,
    manifest,
    integrity_ok: bool,
    signature_valid: bool | None,
    signer_name: str | None,
    steps: list[dict[str, Any]],
    context: dict[str, Any],
) -> str:
    analysis = context.get("analysis") or {}
    policy_eval = context.get("policy_evaluation") or {}
    review_info = context.get("review") or {}
    outcome, _ = _derive_outcome(manifest, steps, review_info)

    latest_review = review_info.get("reviews")[-1] if isinstance(review_info.get("reviews"), list) and review_info["reviews"] else {}
    approval_step = _extract_latest_approval(steps)
    timeline = _material_steps(steps)

    if signature_valid is True:
        signature_line = f"Verified signature ({signer_name or 'unknown signer'})"
    elif signature_valid is False:
        signature_line = "Invalid signature"
    else:
        signature_line = "Unsigned record"

    integrity_line = "Record has not been modified" if integrity_ok else "Integrity check failed"

    lines = [
        "EPI DECISION RECORD",
        "=" * 19,
        f"File: {epi_path.name}",
        f"Outcome: {outcome}",
        f"Workflow: {manifest.workflow_id}",
        f"Created: {_format_ts(manifest.created_at.isoformat() if manifest.created_at else None)}",
        "",
        "CASE OVERVIEW",
        "-" * 13,
        f"Goal: {manifest.goal or 'Not recorded'}",
        f"Notes: {manifest.notes or 'Not recorded'}",
        f"Analysis status: {getattr(manifest, 'analysis_status', None) or 'Not recorded'}",
        f"Analysis error: {getattr(manifest, 'analysis_error', None) or 'None'}",
        f"Analysis summary: {_analysis_headline(analysis)}",
        "",
        "POLICY COMPLIANCE",
        "-" * 17,
        f"Policy ID: {policy_eval.get('policy_id') or 'No embedded policy evaluation'}",
        f"Controls evaluated: {policy_eval.get('controls_evaluated', 'Not recorded')}",
        f"Controls failed: {policy_eval.get('controls_failed', 'Not recorded')}",
        "",
        "KEY DECISION STEPS",
        "-" * 18,
    ]

    for step in timeline:
        lines.append(f"[{_format_ts_short(step.get('timestamp'))}] {_describe_step(step)}")

    lines += [
        "",
        "HUMAN REVIEW / APPROVAL",
        "-" * 23,
        f"Latest approval: {_describe_step(approval_step) if approval_step else 'No approval step recorded'}",
        f"Reviewer: {latest_review.get('reviewer') or review_info.get('reviewed_by') or 'Not recorded'}",
        f"Review outcome: {_review_outcome_label(latest_review.get('outcome')) if latest_review else 'No final review record attached'}",
        f"Review notes: {latest_review.get('notes') or 'Not recorded'}",
        "",
        "CRYPTOGRAPHIC PROOF",
        "-" * 19,
        f"Integrity: {integrity_line}",
        f"Signature: {signature_line}",
        f"Verify locally: epi verify {epi_path.name}",
        "Verify in browser: https://epilabs.org/verify",
        "",
        "APPENDIX",
        "-" * 8,
        f"Files sealed in manifest: {len(manifest.file_manifest)}",
        f"Artifact review required: {policy_eval.get('artifact_review_required', 'Not recorded')}",
    ]
    return "\n".join(lines)


def _build_html_summary(
    epi_path: Path,
    manifest,
    integrity_ok: bool,
    signature_valid: bool | None,
    signer_name: str | None,
    steps: list[dict[str, Any]],
    context: dict[str, Any],
) -> str:
    analysis = context.get("analysis") or {}
    policy = context.get("policy") or {}
    policy_eval = context.get("policy_evaluation") or {}
    review_info = context.get("review") or {}
    latest_review = review_info.get("reviews")[-1] if isinstance(review_info.get("reviews"), list) and review_info["reviews"] else {}
    approval_step = _extract_latest_approval(steps)
    decision_step = _extract_decision_step(steps)
    outcome, outcome_state = _derive_outcome(manifest, steps, review_info)
    outcome_tone = _tone_for_outcome(outcome_state)
    summary = analysis.get("summary") if isinstance(analysis.get("summary"), dict) else {}
    timeline = _material_steps(steps)

    if signature_valid is True:
        signature_label = "Verified signature"
    elif signature_valid is False:
        signature_label = "Invalid signature"
    else:
        signature_label = "Unsigned record"

    if integrity_ok:
        integrity_label = "Record has not been modified"
        integrity_tone = "tone-approved"
    else:
        integrity_label = "Integrity check failed"
        integrity_tone = "tone-rejected"

    policy_results = policy_eval.get("results") if isinstance(policy_eval.get("results"), list) else []
    control_rows = []
    for result in policy_results[:8]:
        status = _titleize(result.get("status"))
        tone = "tone-approved" if result.get("status") == "passed" else "tone-rejected"
        control_rows.append(
            f"""
            <tr>
              <td>{_html.escape(str(result.get("rule_id") or ""))}</td>
              <td>{_html.escape(str(result.get("name") or ""))}</td>
              <td>{_html.escape(_rule_type_label(result.get("rule_type")))}</td>
              <td><span class="status-pill {tone}">{_html.escape(status)}</span></td>
              <td>{_html.escape(str(result.get("plain_english") or ""))}</td>
            </tr>
            """
        )
    if not control_rows:
        control_rows.append(
            """
            <tr>
              <td colspan="5">No embedded policy evaluation was found in this case file.</td>
            </tr>
            """
        )

    appendix_items = [
        ("Workflow ID", manifest.workflow_id),
        ("Created at", _format_ts(manifest.created_at.isoformat() if manifest.created_at else None)),
        ("Signer", signer_name or "No signer recorded"),
        ("Analysis status", getattr(manifest, "analysis_status", None) or "Not recorded"),
        ("Analysis error", getattr(manifest, "analysis_error", None) or "None"),
        ("Files sealed in manifest", len(manifest.file_manifest)),
        ("Policy profile", policy.get("profile_id") or "Not recorded"),
        ("Rule count", len(policy.get("rules") or [])),
        ("Primary finding", _analysis_headline(analysis)),
    ]
    appendix_html = "".join(
        f"<div class=\"detail-row\"><dt>{_html.escape(str(label))}</dt><dd>{_html.escape(_render_value(value))}</dd></div>"
        for label, value in appendix_items
    )

    technical_payload = {
        "manifest": json.loads(manifest.model_dump_json()),
        "analysis_summary": analysis.get("summary"),
        "policy_evaluation": {
            "controls_evaluated": policy_eval.get("controls_evaluated"),
            "controls_failed": policy_eval.get("controls_failed"),
            "artifact_review_required": policy_eval.get("artifact_review_required"),
        },
        "latest_review": latest_review or None,
        "decision": decision_step.get("content") if decision_step else None,
    }
    technical_json = _html.escape(json.dumps(technical_payload, indent=2, ensure_ascii=False))

    timeline_html = "".join(
        f"""
        <article class="timeline-item">
          <div class="timeline-top">
            <strong>{_html.escape(_describe_step(step))}</strong>
            <span>{_html.escape(_format_ts(step.get("timestamp")))}</span>
          </div>
          <p>{_html.escape(str(step.get("kind") or ""))}</p>
        </article>
        """
        for step in timeline
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EPI Decision Record - {_html.escape(epi_path.stem)}</title>
<style>
  :root {{
    color-scheme: light;
    --bg: #f5f1ea;
    --paper: #fffdf8;
    --ink: #1f2430;
    --muted: #5a6170;
    --line: #d7cdbf;
    --approved: #dff1e8;
    --approved-ink: #0d5b3f;
    --warning: #fff0cf;
    --warning-ink: #8a5b00;
    --rejected: #f8dfd9;
    --rejected-ink: #8b2414;
    --neutral: #edf0f5;
    --neutral-ink: #334155;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: "Aptos", "Segoe UI", sans-serif;
    line-height: 1.55;
  }}
  .page {{
    width: min(1080px, calc(100% - 48px));
    margin: 0 auto;
    padding: 28px 0 48px;
  }}
  .record-card {{
    background: var(--paper);
    border: 1px solid var(--line);
    border-radius: 24px;
    padding: 28px;
    margin-bottom: 20px;
    box-shadow: 0 18px 40px rgba(44, 37, 20, 0.06);
  }}
  .cover {{
    display: grid;
    gap: 16px;
  }}
  .cover-top {{
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: start;
  }}
  .eyebrow {{
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.78rem;
    color: var(--muted);
    font-weight: 700;
  }}
  h1, h2, h3 {{
    margin: 0;
    font-family: "Iowan Old Style", "Palatino Linotype", serif;
    letter-spacing: -0.02em;
  }}
  h1 {{ font-size: 2.6rem; }}
  h2 {{ font-size: 1.6rem; margin-bottom: 14px; }}
  p {{ margin: 0; }}
  .cover-copy {{
    color: var(--muted);
    max-width: 760px;
    font-size: 1rem;
  }}
  .status-pill {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 34px;
    padding: 0 14px;
    border-radius: 999px;
    font-weight: 700;
    font-size: 0.92rem;
    border: 1px solid transparent;
  }}
  .tone-approved {{ background: var(--approved); color: var(--approved-ink); }}
  .tone-warning {{ background: var(--warning); color: var(--warning-ink); }}
  .tone-rejected {{ background: var(--rejected); color: var(--rejected-ink); }}
  .tone-neutral {{ background: var(--neutral); color: var(--neutral-ink); }}
  .summary-grid {{
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
    margin-top: 18px;
  }}
  .summary-tile {{
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 16px;
    background: #fffaf3;
  }}
  .summary-tile strong {{
    display: block;
    margin-top: 8px;
    font-size: 1.05rem;
  }}
  .section-copy {{
    color: var(--muted);
    margin-bottom: 16px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.95rem;
  }}
  th, td {{
    border-bottom: 1px solid var(--line);
    padding: 12px 10px;
    text-align: left;
    vertical-align: top;
  }}
  th {{
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
  }}
  .timeline-item {{
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 14px 16px;
    background: #fffaf3;
    margin-bottom: 12px;
  }}
  .timeline-top {{
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 6px;
  }}
  .detail-list {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px 20px;
  }}
  .detail-row {{
    padding: 12px 0;
    border-bottom: 1px solid var(--line);
  }}
  .detail-row dt {{
    color: var(--muted);
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 5px;
  }}
  .detail-row dd {{
    margin: 0;
    font-weight: 600;
  }}
  details {{
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 14px 16px;
    background: #fffaf3;
  }}
  details summary {{
    cursor: pointer;
    font-weight: 700;
  }}
  pre {{
    margin: 14px 0 0;
    white-space: pre-wrap;
    word-break: break-word;
    background: #f6f1e9;
    border-radius: 14px;
    padding: 16px;
    overflow-x: auto;
    font-size: 0.88rem;
  }}
  .proof-list {{
    display: grid;
    gap: 12px;
  }}
  .footnote {{
    margin-top: 12px;
    color: var(--muted);
    font-size: 0.92rem;
  }}
  @media print {{
    body {{ background: white; }}
    .page {{ width: auto; margin: 0; padding: 0; }}
    .record-card {{
      box-shadow: none;
      border-radius: 0;
      border-left: none;
      border-right: none;
      page-break-inside: avoid;
    }}
    details {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
  <div class="page">
    <section class="record-card cover">
      <div class="cover-top">
        <div>
          <p class="eyebrow">EPI Decision Record</p>
          <h1>{_html.escape(outcome)}</h1>
          <p class="cover-copy">
            This document summarizes one sealed AI decision record in plain business language.
            It includes the outcome, the controls that were evaluated, the human review trail,
            and the cryptographic proof needed to verify the record later.
          </p>
        </div>
        <span class="status-pill {outcome_tone}">{_html.escape(outcome)}</span>
      </div>

      <div class="summary-grid">
        <article class="summary-tile">
          <p class="eyebrow">Workflow</p>
          <strong>{_html.escape(_render_value(manifest.workflow_id))}</strong>
        </article>
        <article class="summary-tile">
          <p class="eyebrow">Created</p>
          <strong>{_html.escape(_format_ts(manifest.created_at.isoformat() if manifest.created_at else None))}</strong>
        </article>
        <article class="summary-tile">
          <p class="eyebrow">Analysis</p>
          <strong>{_html.escape(getattr(manifest, "analysis_status", None) or "Not recorded")}</strong>
        </article>
        <article class="summary-tile">
          <p class="eyebrow">Trust</p>
          <strong>{_html.escape(integrity_label)}</strong>
        </article>
      </div>
    </section>

    <section class="record-card">
      <h2>Case Overview</h2>
      <p class="section-copy">A short business summary of the case and the result that was sealed into the artifact.</p>
      <div class="detail-list">
        <div class="detail-row"><dt>Goal</dt><dd>{_html.escape(_render_value(manifest.goal))}</dd></div>
        <div class="detail-row"><dt>Notes</dt><dd>{_html.escape(_render_value(manifest.notes))}</dd></div>
        <div class="detail-row"><dt>Decision</dt><dd>{_html.escape(_decision_label(((decision_step or {}).get("content") or {}).get("decision") if decision_step else None))}</dd></div>
        <div class="detail-row"><dt>Headline</dt><dd>{_html.escape(_analysis_headline(analysis))}</dd></div>
      </div>
    </section>

    <section class="record-card">
      <h2>Policy Compliance Summary</h2>
      <p class="section-copy">These are the control results embedded in the artifact at the time it was sealed.</p>
      <div class="summary-grid" style="margin-top: 0; margin-bottom: 18px;">
        <article class="summary-tile">
          <p class="eyebrow">Policy</p>
          <strong>{_html.escape(str(policy_eval.get("policy_id") or "No embedded policy evaluation"))}</strong>
        </article>
        <article class="summary-tile">
          <p class="eyebrow">Controls Evaluated</p>
          <strong>{_html.escape(_render_value(policy_eval.get("controls_evaluated")))}</strong>
        </article>
        <article class="summary-tile">
          <p class="eyebrow">Controls Failed</p>
          <strong>{_html.escape(_render_value(policy_eval.get("controls_failed")))}</strong>
        </article>
        <article class="summary-tile">
          <p class="eyebrow">Human Review Needed</p>
          <strong>{_html.escape(_render_value(policy_eval.get("artifact_review_required")))}</strong>
        </article>
      </div>
      <table>
        <thead>
          <tr>
            <th>Rule</th>
            <th>Name</th>
            <th>Business Label</th>
            <th>Status</th>
            <th>What It Means</th>
          </tr>
        </thead>
        <tbody>
          {''.join(control_rows)}
        </tbody>
      </table>
    </section>

    <section class="record-card">
      <h2>Key Decision Steps</h2>
      <p class="section-copy">Only the material steps are shown here so a reviewer can follow the decision path quickly.</p>
      {timeline_html}
    </section>

    <section class="record-card">
      <h2>Human Review and Approval</h2>
      <p class="section-copy">This section records the human approval and any later attached review notes.</p>
      <div class="detail-list">
        <div class="detail-row"><dt>Latest approval</dt><dd>{_html.escape(_describe_step(approval_step) if approval_step else "No approval step recorded")}</dd></div>
        <div class="detail-row"><dt>Reviewer</dt><dd>{_html.escape(_render_value(latest_review.get("reviewer") or review_info.get("reviewed_by") or ((approval_step or {}).get("content") or {}).get("reviewer")))}</dd></div>
        <div class="detail-row"><dt>Review outcome</dt><dd>{_html.escape(_review_outcome_label(latest_review.get("outcome")) if latest_review else "No final review record attached")}</dd></div>
        <div class="detail-row"><dt>Review notes</dt><dd>{_html.escape(_render_value(latest_review.get("notes") or ((approval_step or {}).get("content") or {}).get("reason") or ((approval_step or {}).get("content") or {}).get("reviewer_note")))}</dd></div>
      </div>
    </section>

    <section class="record-card">
      <h2>Cryptographic Proof and Verification</h2>
      <p class="section-copy">Anyone can verify this record later and detect whether it was changed after the decision was made.</p>
      <div class="proof-list">
        <div class="detail-row"><dt>Integrity</dt><dd><span class="status-pill {integrity_tone}">{_html.escape(integrity_label)}</span></dd></div>
        <div class="detail-row"><dt>Signature</dt><dd>{_html.escape(signature_label)}{_html.escape(f' - {signer_name}' if signer_name else '')}</dd></div>
        <div class="detail-row"><dt>Verify locally</dt><dd>{_html.escape(f'epi verify {epi_path.name}')}</dd></div>
        <div class="detail-row"><dt>Verify in browser</dt><dd>https://epilabs.org/verify</dd></div>
      </div>
      <p class="footnote">The raw execution record in <code>steps.jsonl</code> remains the ground truth. This Decision Record is a readable summary of the sealed artifact.</p>
    </section>

    <section class="record-card">
      <h2>Appendix</h2>
      <p class="section-copy">Technical detail for engineering, audit, or legal review when deeper inspection is needed.</p>
      <div class="detail-list">
        {appendix_html}
      </div>
      <details>
        <summary>Open technical payload</summary>
        <pre>{technical_json}</pre>
      </details>
    </section>
  </div>
</body>
</html>"""


@app.command()
def summary(
    epi_file: str = typer.Argument(..., help="Path or name of .epi file to summarise."),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Output .html file (default: <name>_summary.html alongside the .epi file).",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        help="Directory to write <name>_summary.html into. If you pass an .html path, it will be used as-is.",
    ),
    text: bool = typer.Option(False, "--text", help="Print plain text to stdout instead of writing HTML."),
):
    """
    Export a Decision Record for a .epi artifact.
    """
    try:
        epi_path = _resolve_epi_file(epi_file)
    except FileNotFoundError:
        console.print(f"[red][FAIL][/red] File not found: {epi_file}")
        raise typer.Exit(1)

    out = _resolve_option_value(out)
    output_dir = _resolve_option_value(output_dir)
    text = bool(_resolve_option_value(text, False))

    try:
        manifest = EPIContainer.read_manifest(epi_path)
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Could not read manifest: {exc}")
        raise typer.Exit(1)

    integrity_ok, _ = EPIContainer.verify_integrity(epi_path)
    signature_valid, signer_name, _ = verify_embedded_manifest_signature(manifest)
    steps = _read_steps(epi_path)
    context = _read_artifact_context(epi_path)

    if text:
        console.print(
            _build_text_summary(
                epi_path,
                manifest,
                integrity_ok,
                signature_valid,
                signer_name,
                steps,
                context,
            )
        )
        return

    default_output = epi_path.parent / f"{epi_path.stem}_summary.html"
    if out is not None and output_dir is not None:
        console.print("[red][FAIL][/red] Use either --out or --output-dir, not both.")
        raise typer.Exit(1)

    if output_dir is not None:
        if output_dir.suffix.lower() == ".html":
            out = output_dir
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            out = output_dir / default_output.name
    elif out is None:
        out = default_output
    elif out.exists() and out.is_dir():
        out = out / default_output.name

    html_content = _build_html_summary(
        epi_path,
        manifest,
        integrity_ok,
        signature_valid,
        signer_name,
        steps,
        context,
    )
    out.write_text(html_content, encoding="utf-8")
    console.print(f"[green][OK][/green] Decision Record written: {out}")
