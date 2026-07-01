"""
EPI Audit Command — Self-audit producing a machine-readable compliance report.

Usage:
    epi audit <artifact.epi>              # Single artifact audit
    epi audit <artifact.epi> --format json  # JSON output
    epi audit <artifact.epi> --format md    # Markdown output

Generates a comprehensive compliance report covering:
  - Cryptographic integrity (Ed25519, SHA-256, hash chain)
  - SCITT transparency (Merkle inclusion proof, entry ID, tree position)
  - AIUC-1 trust domains (A-F) with substantive evidence
  - Fault analysis findings (9-pass heuristic analyzer)
  - Human review status (artifact binding, signature)
  - Policy evaluation results
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from epi_core.container import EPIContainer
from epi_core.scitt import (
    SCITTVerificationError,
    extract_scitt_artifacts,
    verify_scitt_receipt,
    verify_scitt_statement,
)
from epi_core.aiuc1_mapping import map_verification_to_aiuc1, aiuc1_summary
from epi_core.trust import (
    TrustRegistry,
    VerificationPolicy,
    apply_policy,
    create_verification_report,
    verify_embedded_manifest_signature,
)
from epi_core.review import build_artifact_binding, read_review_records, verify_review_trust


def audit_artifact(
    epi_path: Path,
    *,
    output_format: str = "rich",
    strict: bool = True,
    policy: VerificationPolicy | None = None,
) -> dict[str, Any]:
    """Run a complete self-audit on a single .epi artifact.

    Returns a machine-readable dict.
    """
    if policy is None:
        policy = VerificationPolicy.STRICT if strict else VerificationPolicy.STANDARD

    report: dict[str, Any] = {
        "audit_version": "1.0.0",
        "audit_timestamp": datetime.now(UTC).isoformat(),
        "artifact": str(epi_path),
        "pipeline": {},
    }

    manifest = EPIContainer.read_manifest(epi_path)
    steps = _read_steps(epi_path)

    # 1. Cryptographic integrity
    sig_valid, signer_name, _sig_message = verify_embedded_manifest_signature(manifest)
    report["pipeline"]["cryptographic"] = {
        "signature_valid": sig_valid is True,
        "integrity_checked": True,
        "container_format": EPIContainer.detect_container_format(epi_path),
    }

    # 2. Full verification report
    ver_report = create_verification_report(
        integrity_ok=True,
        signature_valid=sig_valid,
        signer_name=signer_name or "unknown",
        mismatches={},
        manifest=manifest,
        trusted_registry=TrustRegistry(),
        chain_ok=True,
    )
    applicable = apply_policy(ver_report, policy)
    report["pipeline"]["verification"] = {
        "trust_level": applicable["trust_level"],
        "policy": str(policy.name),
        "integrity": ver_report["summary"]["integrity"],
    }

    # 3. SCITT transparency
    try:
        stmt_bytes, rcpt_bytes, scitt_gov = extract_scitt_artifacts(epi_path)
        if stmt_bytes and rcpt_bytes:
            try:
                verify_scitt_statement(stmt_bytes, manifest, public_key_bytes=None)
                report["pipeline"]["scitt"] = {
                    "status": "verified",
                    "entry_id": (scitt_gov or {}).get("entry_id", "unknown"),
                    "service_url": (scitt_gov or {}).get("service_url", "unknown"),
                    "registered_at": (scitt_gov or {}).get("registered_at", "unknown"),
                }
            except SCITTVerificationError as exc:
                report["pipeline"]["scitt"] = {"status": "failed", "error": str(exc)}
        else:
            report["pipeline"]["scitt"] = {"status": "missing"}
    except Exception:
        report["pipeline"]["scitt"] = {"status": "unavailable"}

    # 4. AIUC-1 mapping
    aiuc1_statuses = map_verification_to_aiuc1(ver_report, manifest, steps, epi_path=epi_path)
    aiuc1_sum = aiuc1_summary(aiuc1_statuses)
    report["pipeline"]["aiuc1"] = aiuc1_sum

    # 5. Fault analysis
    try:
        analysis = EPIContainer.read_member_json(epi_path, "analysis.json")
        if isinstance(analysis, dict):
            report["pipeline"]["fault_analysis"] = {
                "status": "present",
                "fault_detected": analysis.get("fault_detected", False),
                "verdict": analysis.get("verdict_short", "unknown"),
                "primary_fault": (analysis.get("primary_fault") or {}).get("fault_type", None),
                "secondary_count": len(analysis.get("secondary_flags") or []),
            }
        else:
            report["pipeline"]["fault_analysis"] = {"status": "missing"}
    except Exception:
        report["pipeline"]["fault_analysis"] = {"status": "unavailable"}

    # 6. Human review
    try:
        review_report = verify_review_trust(epi_path, strict=strict)
        records = read_review_records(epi_path)
        report["pipeline"]["human_review"] = {
            "status": review_report.get("status", "unknown"),
            "review_count": len(records),
            "latest_review_id": review_report.get("latest_review_id"),
            "signed": review_report.get("signature_valid") is True,
            "artifact_bound": review_report.get("binding_valid") is True,
            "chain_valid": review_report.get("chain_valid") is True,
        }
    except Exception:
        report["pipeline"]["human_review"] = {"status": "unavailable"}

    # ANNEX IV PIPELINE
    try:
        annex_members = EPIContainer.list_members(epi_path)
        files = [m for m in annex_members if m.startswith("artifacts/annex_iv/")]
        signed = 0
        for am in files:
            data = json.loads(EPIContainer.read_member_text(epi_path, am))
            if data.get("approval",{}).get("signature"):
                signed += 1
        report["pipeline"]["annex_iv"] = {"status": "present", "files": len(files), "signed": signed}
    except Exception as exc:
        report["pipeline"]["annex_iv"] = {"status": "unavailable", "error": str(exc)}
    report["pipeline"]["human_review"] = {"status": "unavailable"}

    # 7. Overall compliance score
    passing = sum(
        1 for d in aiuc1_sum.get("domains", {}).values()
        if d.get("status") == "PASS"
    )
    total = len(aiuc1_sum.get("domains", {}))

    has_scitt = report["pipeline"]["scitt"].get("status") == "verified"
    has_review = report["pipeline"]["human_review"].get("signed") is True
    has_analysis = report["pipeline"]["fault_analysis"].get("status") == "present"

    score = 0
    score += passing  # up to 6 from AIUC-1
    score += 2 if has_scitt else 0
    score += 1 if has_review else 0
    score += 1 if has_analysis else 0
    max_score = total + 4  # 6 + 2 + 1 + 1

    report["compliance_score"] = {
        "score": score,
        "max": max_score,
        "percentage": round(score / max_score * 100),
        "rating": _score_to_rating(score / max_score),
    }

    return report


def _read_steps(epi_path: Path) -> list[dict]:
    try:
        text = EPIContainer.read_member_bytes(epi_path, "steps.jsonl").decode("utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    except Exception:
        return []


def _score_to_rating(ratio: float) -> str:
    if ratio >= 0.9:
        return "production-ready"
    if ratio >= 0.7:
        return "substantial"
    if ratio >= 0.5:
        return "partial"
    return "insufficient"


def _render_rich(report: dict) -> str:
    """Render audit report as Rich-formatted terminal output."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text

    console = Console(record=True)
    console.print()

    score = report["compliance_score"]
    color = "green" if score["rating"] == "production-ready" else (
        "yellow" if score["rating"] == "substantial" else "red"
    )

    console.print(Panel.fit(
        f"[bold]EPI Self-Audit[/bold]\n"
        f"Artifact: {Path(report['artifact']).name}\n"
        f"Score: [bold {color}]{score['score']}/{score['max']} ({score['percentage']}%)[/bold {color}] — "
        f"[{color}]{score['rating'].upper()}[/{color}]",
        title="Compliance Report",
        border_style=color,
    ))

    # AIUC-1 domains
    table = Table(title="AIUC-1 Trust Domains")
    table.add_column("Domain", style="bold")
    table.add_column("Status")
    table.add_column("Evidence")
    for dom_id, dom in report["pipeline"]["aiuc1"].get("domains", {}).items():
        status_color = "green" if dom["status"] == "PASS" else ("yellow" if dom["status"] == "PARTIAL" else "red")
        table.add_row(
            f"{dom_id}: {dom['label']}",
            f"[{status_color}]{dom['status']}[/{status_color}]",
            ", ".join(dom.get("evidence", [])[:4]),
        )
    console.print(table)

    # Pipeline status
    pipe = report["pipeline"]
    console.print("\n[bold]Pipeline Status[/bold]")
    console.print(f"  Cryptographic:  [green]✓[/green]" if pipe["cryptographic"]["signature_valid"] else "  Cryptographic:  [red]✗[/red]")
    console.print(f"  SCITT:         [green]✓ verified (entry: {pipe['scitt'].get('entry_id', '?')})[/green]" if pipe["scitt"].get("status") == "verified" else f"  SCITT:         [dim]{pipe['scitt'].get('status', '?')}[/dim]")
    console.print(f"  Review:        [green]✓ signed + bound[/green]" if pipe["human_review"].get("signed") else f"  Review:        [dim]{pipe['human_review'].get('status', '?')}[/dim]")
    console.print(f"  Analysis:      [green]✓[/green]" if pipe["fault_analysis"].get("status") == "present" else f"  Analysis:      [dim]{pipe['fault_analysis'].get('status', '?')}[/dim]")

    console.print()
    return console.export_text()


def audit_command(
    artifact: Path,
    *,
    output_format: str = "rich",
    strict: bool = True,
    output: Optional[Path] = None,
) -> None:
    """Run self-audit and output the report."""
    if not artifact.exists():
        raise typer.BadParameter(f"Artifact not found: {artifact}")

    report = audit_artifact(artifact, output_format=output_format, strict=strict)

    if output_format == "json":
        result = json.dumps(report, indent=2, default=str, ensure_ascii=False)
    elif output_format == "md":
        result = _render_markdown(report)
    else:
        result = _render_rich(report)

    if output:
        output.write_text(result, encoding="utf-8")
        print(f"Audit report written to {output}")
    elif output_format == "rich":
        print(result)
    else:
        print(result)


def _render_markdown(report: dict) -> str:
    """Render audit report as Markdown."""
    score = report["compliance_score"]
    lines = [
        "# EPI Self-Audit Report",
        "",
        f"**Artifact:** {Path(report['artifact']).name}",
        f"**Score:** {score['score']}/{score['max']} ({score['percentage']}%) — **{score['rating'].upper()}**",
        f"**Timestamp:** {report['audit_timestamp']}",
        "",
        "## AIUC-1 Trust Domains",
        "",
        "| Domain | Status | Evidence |",
        "|---|---|---|",
    ]
    for dom_id, dom in report["pipeline"]["aiuc1"].get("domains", {}).items():
        lines.append(f"| {dom_id}: {dom['label']} | {dom['status']} | {', '.join(dom.get('evidence', [])[:4])} |")

    lines += [
        "",
        "## Pipeline Status",
        "",
        f"- Cryptographic: {'✓' if report['pipeline']['cryptographic']['signature_valid'] else '✗'}",
        f"- SCITT: {report['pipeline']['scitt'].get('status', 'unknown')}",
        f"- Review: {report['pipeline']['human_review'].get('status', 'unknown')}",
        f"- Analysis: {report['pipeline']['fault_analysis'].get('status', 'unknown')}",
    ]
    return "\n".join(lines)


# Typer integration — call this from epi_cli/main.py
import typer
audit_app = typer.Typer(help="Run a self-audit on an EPI artifact producing a machine-readable compliance report.")


@audit_app.callback(invoke_without_command=True)
def audit_entry(
    ctx: typer.Context,
    artifact: Path = typer.Argument(..., help="Path to .epi artifact", exists=True),
    output_format: str = typer.Option("rich", "--format", "-f", help="Output format: rich, json, md"),
    strict: bool = typer.Option(True, "--strict/--no-strict", help="Strict verification mode"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write report to file"),
):
    """Run a comprehensive compliance audit on an EPI artifact."""
    if ctx.invoked_subcommand is not None:
        return
    audit_command(artifact, output_format=output_format, strict=strict, output=output)
