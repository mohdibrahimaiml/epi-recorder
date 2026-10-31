"""``epi oversight report`` - what the customer actually received, over a period.

A pile of decision files answers nothing on its own. The question a bank, an
insurer or an auditor asks is a period-shaped one: *over these three months,
what did your AI decide, which model answered, who approved it, and which cases
can you not produce?*

This command joins the three sources the customer already holds:

* the sealed ``.epi`` files - outcome, reasons, served model, approvals;
* the customer's witness log - which cases the vendor reported, and when;
* the customer's own list of expected cases (``--expect``) - the denominator.

It reports the gaps explicitly: cases the vendor reported but never delivered a
file for, and cases the customer expected that were never sealed or reported.
"""

from __future__ import annotations

import html as _html
import json
import re
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table
from rich.markup import escape

console = Console()

app = typer.Typer(help="Oversight: decisions by outcome, model and approval over a period.")

PINNED = "pinned"
UNPINNED = "unpinned"
ABSENT = "absent"
INVALID = "invalid"
SEALING_KEY = "sealing_key"

_APPROVAL_BUCKETS = {
    "human_signed": PINNED,
    "signed_unknown_key": UNPINNED,
    "invalid": INVALID,
    "signed_by_sealing_key": SEALING_KEY,
    "unsigned": ABSENT,
}


def _date_of(value: Any) -> str:
    """The UTC calendar day of an ISO timestamp, or "" when there is none."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date().isoformat()


def _in_period(day: str, since: str | None, until: str | None) -> bool:
    if not day:
        # An undated record cannot be proved to be outside the period.
        return True
    if since and day < since:
        return False
    if until and day > until:
        return False
    return True


def _approval_bucket(detail: dict[str, Any]) -> str:
    classification = detail.get("classification")
    if not classification:
        return ABSENT
    return _APPROVAL_BUCKETS.get(str(classification), ABSENT)


def _describe(record: dict[str, Any]) -> dict[str, Any]:
    """One line per sealed decision: what it says and how it is approved."""
    from epi_cli.export_summary import _approval_detail, _decision_detail, _decision_label

    file = Path(record["path"])
    decision = _decision_detail(record["steps"])
    approval = _approval_detail(file, record["steps"])
    bucket = _approval_bucket(approval)
    raw_outcome = decision.get("outcome")
    return {
        "case": record["case"],
        "file": file.name,
        "created_at": record["created_at"],
        "day": _date_of(record["created_at"]),
        # "DENY", "deny_claim" and "Denied" are one outcome to a customer.
        "outcome": _decision_label(raw_outcome) if raw_outcome else "Not recorded",
        "outcome_raw": raw_outcome,
        "rationale": decision.get("rationale"),
        "model": decision.get("served_model") or decision.get("requested_model"),
        "approval": bucket,
        "approver": approval.get("name"),
        "approver_fingerprint": approval.get("fingerprint"),
        "approval_classification": approval.get("classification"),
        "witnessed": record["witnessed"],
        "witness_detail": record.get("witness_detail") or "",
    }


def _load(paths: list[Path]) -> list[dict[str, Any]]:
    """Read every file's manifest and steps once; unreadable files are kept as gaps."""
    from epi_core.container import EPIContainer

    from epi_cli.witness import _expand_cases

    records: list[dict[str, Any]] = []
    for file in _expand_cases(paths):
        try:
            manifest = EPIContainer.read_manifest(file)
            steps = EPIContainer.read_steps(file)
        except Exception as exc:  # noqa: BLE001 - reported, never raised
            records.append(
                {
                    "path": str(file),
                    "case": file.name,
                    "created_at": None,
                    "steps": [],
                    "manifest": None,
                    "error": f"not a readable .epi ({exc})",
                }
            )
            continue
        records.append(
            {
                "path": str(file),
                "case": str(getattr(manifest, "goal", "") or file.stem),
                "goal": str(getattr(manifest, "goal", "") or ""),
                "workflow_id": str(getattr(manifest, "workflow_id", "") or ""),
                "created_at": str(getattr(manifest, "created_at", "") or ""),
                "steps": steps,
                "manifest": manifest,
                "error": None,
            }
        )
    return records


def _attach_witness(
    records: list[dict[str, Any]],
    log_path: Path | None,
    witness_pubkey: str | None,
    entries: list[dict],
) -> None:
    """Match each file to the customer's log, with the same rules as `epi witness report`."""
    from epi_cli.verify import _check_witness_log

    for record in records:
        if record.get("error") or log_path is None:
            record["witnessed"] = "not checked"
            record["witness_detail"] = "no witness log supplied (--log)"
            continue
        manifest = record["manifest"]
        check = _check_witness_log(Path(record["path"]), manifest, log_path, witness_pubkey)
        status = str(check.get("status") or "")
        detail = str(check.get("detail") or "")
        goal = str(record.get("goal") or "").strip()
        if status == "NOT IN WITNESS LOG" and goal:
            same_goal = [
                entry for entry in entries if str(entry.get("goal") or "").strip() == goal
            ]
            if same_goal:
                latest = max(
                    (str(entry.get("received_at") or "") for entry in same_goal), default=""
                )
                status = "MISMATCH"
                detail = (
                    f"a different version of {goal!r} was reported "
                    f"({len(same_goal)} report(s), latest {latest or 'unknown time'}); "
                    "this copy was never reported"
                )
        record["witnessed"] = status.lower().replace(" ", "_")
        record["witness_detail"] = detail
        if status == "WITNESSED":
            workflow = str(record.get("workflow_id") or "")
            for entry in entries:
                if str(entry.get("workflow_id") or "") == workflow and entry.get("case_id"):
                    record["case"] = str(entry["case_id"])
                    break


def _counts(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes: dict[str, int] = {}
    models: dict[str, dict[str, Any]] = {}
    approvals = {PINNED: 0, UNPINNED: 0, ABSENT: 0, INVALID: 0, SEALING_KEY: 0}
    witness: dict[str, int] = {}

    for item in decisions:
        outcomes[str(item["outcome"])] = outcomes.get(str(item["outcome"]), 0) + 1
        model = str(item["model"] or "Not recorded")
        bucket = models.setdefault(model, {"count": 0, "first": None, "last": None})
        bucket["count"] += 1
        day = item["day"]
        if day:
            bucket["first"] = min(filter(None, [bucket["first"], day]), default=None)
            bucket["last"] = max(filter(None, [bucket["last"], day]), default=None)
        approvals[item["approval"]] = approvals.get(item["approval"], 0) + 1
        witness[item["witnessed"]] = witness.get(item["witnessed"], 0) + 1

    return {
        "outcomes": dict(sorted(outcomes.items(), key=lambda kv: (-kv[1], kv[0]))),
        "models": dict(sorted(models.items(), key=lambda kv: (-kv[1]["count"], kv[0]))),
        "approvals": approvals,
        "witness": witness,
    }


def _delivery_gaps(
    entries: list[dict],
    decisions: list[dict[str, Any]],
    since: str | None,
    until: str | None,
) -> list[dict[str, Any]]:
    """Cases the vendor reported in the period with no file in the set."""
    from epi_cli.witness import _case_key

    delivered_workflows = {
        str(item.get("workflow_id") or "") for item in decisions if not item.get("error")
    }
    delivered_cases = {str(item.get("case") or "").strip() for item in decisions}

    gaps: dict[str, dict[str, Any]] = {}
    for entry in entries:
        day = _date_of(entry.get("received_at"))
        if not _in_period(day, since, until):
            continue
        if str(entry.get("workflow_id") or "") in delivered_workflows:
            continue
        key = _case_key(entry)
        if key and key in delivered_cases:
            continue
        item = gaps.setdefault(
            key or "(no case id)",
            {"case": key or "(no case id)", "reports": 0, "last_received": None, "goal": None},
        )
        item["reports"] += 1
        received = str(entry.get("received_at") or "")
        if received and (item["last_received"] is None or received > item["last_received"]):
            item["last_received"] = received
        item["goal"] = item["goal"] or entry.get("goal")
    return sorted(gaps.values(), key=lambda item: item["case"])


def _never_sealed(
    expectations: list[str],
    entries: list[dict],
    decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Cases the customer expected that have neither a file nor a report."""
    from epi_cli.witness import _entries_for_expectation

    present = {str(item.get("case") or "").strip().lower() for item in decisions}
    goals = {str(item.get("goal") or "").strip().lower() for item in decisions}
    missing: list[dict[str, Any]] = []
    for value in expectations:
        needle = value.strip().lower()
        if needle in present or needle in goals:
            continue
        reports = _entries_for_expectation(value, entries)
        if reports:
            continue
        missing.append({"case": value, "reports": 0})
    return missing


def _build_payload(
    decisions: list[dict[str, Any]],
    *,
    log_path: Path | None,
    since: str | None,
    until: str | None,
    gaps: list[dict[str, Any]],
    never_sealed: list[dict[str, Any]],
    expectations: list[str],
) -> dict[str, Any]:
    counts = _counts(decisions)
    days = sorted({item["day"] for item in decisions if item.get("day")})
    return {
        "period": {
            "since": since,
            "until": until,
            "data_from": days[0] if days else None,
            "data_to": days[-1] if days else None,
        },
        "log": str(log_path) if log_path else None,
        "sealed": {
            "files": len(decisions),
            "unreadable": sum(1 for item in decisions if item.get("error")),
            "decisions_in_period": len(decisions),
        },
        "outcomes": counts["outcomes"],
        "models": counts["models"],
        "approvals": counts["approvals"],
        "witness": counts["witness"],
        "reported_not_delivered": gaps,
        "expected_never_sealed": never_sealed,
        "expected_total": len(expectations),
        "decisions": [
            {
                key: value
                for key, value in item.items()
                if key not in {"manifest", "steps"}
            }
            for item in decisions
        ],
    }


def _scope(period: dict[str, Any]) -> str:
    """The period as a reader would state it: asked for, or what the data covers."""
    if period.get("since") or period.get("until"):
        return f"{period.get('since') or 'start'} to {period.get('until') or 'today'}"
    first, last = period.get("data_from"), period.get("data_to")
    if first and last:
        return f"all records, {first} to {last}"
    return "all records"


def _print_tables(payload: dict[str, Any]) -> None:
    period = payload["period"]
    scope = _scope(period)
    console.print(
        f"[bold]Oversight report[/bold]  {escape(scope)}  "
        f"[dim]{payload['sealed']['files']} sealed decision(s)"
        + (f", log {escape(str(payload['log']))}" if payload["log"] else "")
        + "[/dim]"
    )

    table = Table(title="Decisions by outcome")
    table.add_column("outcome", overflow="fold")
    table.add_column("count", justify="right")
    for outcome, count in payload["outcomes"].items():
        table.add_row(escape(str(outcome)), str(count))
    console.print(table)

    table = Table(title="Model versions")
    table.add_column("served model", overflow="fold")
    table.add_column("decisions", justify="right")
    table.add_column("first seen")
    table.add_column("last seen")
    for model, info in payload["models"].items():
        table.add_row(
            escape(str(model)),
            str(info["count"]),
            str(info["first"] or "-"),
            str(info["last"] or "-"),
        )
    console.print(table)

    table = Table(title="Human approvals")
    table.add_column("state", overflow="fold")
    table.add_column("decisions", justify="right")
    labels = {
        PINNED: "signed, key pinned",
        UNPINNED: "signed, key not pinned",
        ABSENT: "no approval attached",
        INVALID: "signature does NOT verify",
        SEALING_KEY: "signed by the sealing key only",
    }
    for bucket, label in labels.items():
        count = payload["approvals"].get(bucket, 0)
        colour = "green" if bucket == PINNED else ("red" if bucket in (INVALID, SEALING_KEY) else "yellow")
        table.add_row(escape(label), f"[{colour}]{count}[/{colour}]" if count else "0")
    console.print(table)

    if payload["witness"]:
        table = Table(title="Against the customer's witness log")
        table.add_column("state", overflow="fold")
        table.add_column("decisions", justify="right")
        for state, count in sorted(payload["witness"].items()):
            colour = "green" if state == "witnessed" else "red"
            table.add_row(escape(state.replace("_", " ")), f"[{colour}]{count}[/{colour}]")
        console.print(table)

    off_log = [
        item
        for item in payload["decisions"]
        if item.get("witnessed") not in ("witnessed", "not_checked")
    ]
    if off_log:
        table = Table(title="Decisions that do not match your witness log")
        table.add_column("file", overflow="fold")
        table.add_column("case", overflow="fold")
        table.add_column("state", no_wrap=True)
        table.add_column("detail", overflow="fold", ratio=1)
        for item in off_log:
            table.add_row(
                escape(str(item.get("file") or "-")),
                escape(str(item.get("case") or "-")),
                f"[red]{escape(str(item.get('witnessed') or '-').replace('_', ' '))}[/red]",
                escape(str(item.get("witness_detail") or "")[:160]),
            )
        console.print(table)

    if payload["reported_not_delivered"]:
        table = Table(title="Reported to you, but no file delivered")
        table.add_column("case", overflow="fold")
        table.add_column("reports", justify="right")
        table.add_column("last received (UTC)")
        for item in payload["reported_not_delivered"]:
            table.add_row(
                escape(str(item["case"])),
                str(item["reports"]),
                str(item["last_received"] or "-")[:19].replace("T", " "),
            )
        console.print(table)

    if payload["expected_never_sealed"]:
        table = Table(title="Expected, but never sealed or reported")
        table.add_column("case", overflow="fold")
        for item in payload["expected_never_sealed"]:
            table.add_row(escape(str(item["case"])))
        console.print(table)

    if payload["expected_total"]:
        covered = payload["expected_total"] - len(payload["expected_never_sealed"])
        console.print(
            f"[dim]{covered} of {payload['expected_total']} expected case(s) have a "
            "record or a report.[/dim]"
        )


_CSS = """
:root { color-scheme: light; --bg:#f5f1ea; --paper:#fffdf8; --ink:#1f2430; --muted:#5a6170;
  --line:#d7cdbf; --ok:#0d5b3f; --warn:#8a5b00; --bad:#8b2414; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font-family:"Aptos","Segoe UI",sans-serif; line-height:1.55; }
.page { width:min(1080px, calc(100% - 48px)); margin:0 auto; padding:28px 0 48px; }
.card { background:var(--paper); border:1px solid var(--line); border-radius:24px;
  padding:28px; margin-bottom:20px; box-shadow:0 18px 40px rgba(44,37,20,.06); }
.eyebrow { text-transform:uppercase; letter-spacing:.12em; font-size:.78rem;
  color:var(--muted); font-weight:700; }
h1,h2,h3 { margin:0; font-family:"Iowan Old Style","Palatino Linotype",serif; font-weight:600; }
h1 { font-size:2rem; margin-top:.4rem; }
h2 { font-size:1.25rem; margin-bottom:.75rem; }
p { margin:.5rem 0; }
.table-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:.95rem; }
th,td { border-bottom:1px solid var(--line); padding:10px 8px; text-align:left; vertical-align:top; }
th { font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }
.pill { display:inline-block; padding:.15rem .55rem; border-radius:999px; font-size:.78rem;
  border:1px solid transparent; }
.ok { background:#dff1e8; color:var(--ok); }
.warn { background:#fff0cf; color:var(--warn); }
.bad { background:#f8dfd9; color:var(--bad); }
.grid { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px; margin-top:18px; }
.tile { border:1px solid var(--line); border-radius:18px; padding:16px; background:#fffaf3; }
.tile strong { display:block; margin-top:8px; font-size:1.4rem; }
.mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.85rem; }
@media (max-width:760px) { .grid { grid-template-columns:repeat(2, minmax(0,1fr)); } }
"""


def _pill(text: str, tone: str) -> str:
    return f'<span class="pill {tone}">{_html.escape(text)}</span>'


def _tone_for(bucket: str) -> str:
    if bucket == PINNED:
        return "ok"
    if bucket in (ABSENT, UNPINNED):
        return "warn"
    return "bad"


def _build_html(payload: dict[str, Any]) -> str:
    period = payload["period"]
    scope = _scope(period)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    outcome_rows = "".join(
        f"<tr><td>{_html.escape(str(name))}</td><td>{count}</td></tr>"
        for name, count in payload["outcomes"].items()
    ) or '<tr><td colspan="2">No decisions in this period.</td></tr>'

    model_rows = "".join(
        "<tr><td class=\"mono\">{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            _html.escape(str(name)),
            info["count"],
            _html.escape(str(info["first"] or "-")),
            _html.escape(str(info["last"] or "-")),
        )
        for name, info in payload["models"].items()
    ) or '<tr><td colspan="4">No model version recorded.</td></tr>'

    approval_labels = {
        PINNED: "Signed, key pinned",
        UNPINNED: "Signed, key not pinned by this verifier",
        ABSENT: "No approval attached",
        INVALID: "Signature does NOT verify",
        SEALING_KEY: "Signed by the sealing key only (not an approval)",
    }
    approval_rows = "".join(
        f"<tr><td>{_html.escape(approval_labels[bucket])}</td>"
        f"<td>{_pill(str(payload['approvals'].get(bucket, 0)), _tone_for(bucket))}</td></tr>"
        for bucket in (PINNED, UNPINNED, ABSENT, INVALID, SEALING_KEY)
    )

    decision_rows = "".join(
        "<tr><td>{}<div class=\"mono\" style=\"color:var(--muted)\">{}</div></td>"
        "<td>{}</td><td>{}</td><td class=\"mono\">{}</td><td>{}</td><td title=\"{}\">{}</td></tr>".format(
            _html.escape(str(item.get("case") or "-")),
            _html.escape(str(item.get("file") or "")),
            _html.escape(str(item.get("day") or "-")),
            _html.escape(str(item.get("outcome") or "-")),
            _html.escape(str(item.get("model") or "not recorded")),
            _pill(
                approval_labels.get(item.get("approval"), "No approval attached"),
                _tone_for(str(item.get("approval"))),
            ),
            _html.escape(str(item.get("witness_detail") or "")),
            _pill(
                "witnessed" if item.get("witnessed") == "witnessed" else str(item.get("witnessed") or "-").replace("_", " "),
                "ok" if item.get("witnessed") == "witnessed" else "bad",
            ),
        )
        for item in payload["decisions"]
        if not item.get("error")
    ) or '<tr><td colspan="6">No readable decision files.</td></tr>'

    gaps = payload["reported_not_delivered"]
    gap_rows = "".join(
        f"<tr><td>{_html.escape(str(item['case']))}</td><td>{item['reports']}</td>"
        f"<td>{_html.escape(str(item['last_received'] or '-')[:19])}</td></tr>"
        for item in gaps
    )
    never = payload["expected_never_sealed"]
    never_rows = "".join(
        f"<tr><td>{_html.escape(str(item['case']))}</td></tr>" for item in never
    )

    page_html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Oversight report - {_html.escape(scope)}</title>
<style>{_CSS}</style></head>
<body><div class="page">

<section class="card">
  <p class="eyebrow">EPI Oversight Report</p>
  <h1>What your AI decided, and what you can prove</h1>
  <p class="eyebrow" style="margin-top:1rem">Period</p>
  <p>{_html.escape(scope)} &middot; generated {generated}</p>
  <div class="grid">
    <div class="tile"><p class="eyebrow">Decisions</p><strong>{payload['sealed']['files']}</strong></div>
    <div class="tile"><p class="eyebrow">Witnessed</p><strong>{payload['witness'].get('witnessed', 0)}</strong></div>
    <div class="tile"><p class="eyebrow">Reported, not delivered</p><strong>{len(gaps)}</strong></div>
    <div class="tile"><p class="eyebrow">Expected, never sealed</p><strong>{len(never)}</strong></div>
  </div>
  <p style="margin-top:1rem;color:var(--muted)">Every number here comes from files you hold, plus your
  own witness log. Nothing was asked of the vendor to produce it.</p>
</section>

<section class="card">
  <h2>Decisions by outcome</h2>
  <table><thead><tr><th>Outcome</th><th>Decisions</th></tr></thead>
  <tbody>{outcome_rows}</tbody></table>
</section>

<section class="card">
  <h2>Model versions</h2>
  <p style="color:var(--muted)">The change log a bank asks a vendor for, read from the sealed records.</p>
  <table><thead><tr><th>Served model</th><th>Decisions</th><th>First seen</th><th>Last seen</th></tr></thead>
  <tbody>{model_rows}</tbody></table>
</section>

<section class="card">
  <h2>Human approvals</h2>
  <p style="color:var(--muted)">A signature by the vendor's sealing key is not an approval by a person.
  An unpinned key is still a signature; pin the fingerprint to make it one you can rely on.</p>
  <table><thead><tr><th>State</th><th>Decisions</th></tr></thead>
  <tbody>{approval_rows}</tbody></table>
</section>

<section class="card">
  <h2>Reported to you, but no file delivered</h2>
  <p style="color:var(--muted)">Your witness log has a report for these cases; no sealed file was
  handed over in this set.</p>
  <table><thead><tr><th>Case</th><th>Reports</th><th>Last received (UTC)</th></tr></thead>
  <tbody>{gap_rows or '<tr><td colspan="3">None. Every reported case has a file.</td></tr>'}</tbody></table>
</section>

<section class="card">
  <h2>Expected, but never sealed or reported</h2>
  <table><thead><tr><th>Case</th></tr></thead>
  <tbody>{never_rows or '<tr><td>None.</td></tr>'}</tbody></table>
</section>

<section class="card">
  <h2>Every decision</h2>
  <table><thead><tr><th>Case</th><th>Date</th><th>Outcome</th><th>Model</th><th>Approval</th><th>Witness</th></tr></thead>
  <tbody>{decision_rows}</tbody></table>
</section>

<section class="card">
  <h2>How to check this</h2>
  <p class="mono">epi verify &lt;file.epi&gt; --witness-log received.jsonl --require-human-approval</p>
  <p style="color:var(--muted)">Or open <span class="mono">https://epilabs.org/verify</span> and drop the
  file and your log in - nothing is uploaded. This report is evidence input, not a certificate:
  it does not prove the AI was right, or that the run was captured completely.</p>
</section>

</div></body></html>
"""
    # A six-column table cannot fit a phone; let the table scroll, not the page.
    return re.sub(
        r"<table>(.*?)</table>",
        r'<div class="table-wrap"><table>\1</table></div>',
        page_html,
        flags=re.S,
    )


@app.command(name="report")
def report(
    cases: list[Path] | None = typer.Option(
        None,
        "--cases",
        help="A .epi file or a directory of them. Repeatable.",
    ),
    log: Path | None = typer.Option(
        None,
        "--log",
        envvar="EPI_WITNESS_LOG",
        help="The customer's witness log (default: EPI_WITNESS_LOG, then ./received.jsonl).",
    ),
    since: str | None = typer.Option(
        None, "--since", help="First day to include, inclusive (YYYY-MM-DD, UTC)."
    ),
    until: str | None = typer.Option(
        None, "--until", help="Last day to include, inclusive (YYYY-MM-DD, UTC)."
    ),
    expect: Path | None = typer.Option(
        None,
        "--expect",
        help="CSV of case IDs you expected. Any with no file and no report is listed.",
    ),
    witness_pubkey: str | None = typer.Option(
        None,
        "--witness-pubkey",
        envvar="EPI_WITNESS_PUBKEY",
        help="Pinned EPI witness key, for logs that carry signed receipts.",
    ),
    out: Path | None = typer.Option(
        None, "--out", help="Write the one-page report here (HTML)."
    ),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
    fail_on_gaps: bool = typer.Option(
        False,
        "--fail-on-gaps",
        help="Exit 1 when a reported case has no file, an expected case was never "
        "sealed, or a file is not in the witness log.",
    ),
):
    """Decisions by outcome, model versions, approvals and delivery gaps, per period.

    The period selects which decisions and which witness reports are counted; the
    reconciliation is over the whole set, so a file delivered last month still
    counts as delivered for a case reported this month.
    """
    from epi_cli.witness import _load_witness_entries, _read_expectations

    for label, value in (("--since", since), ("--until", until)):
        if value and not _is_day(value):
            console.print(f"[red]{label} must be YYYY-MM-DD (got {value!r})[/red]")
            raise typer.Exit(2)

    if not cases:
        console.print("[red]--cases is required: a .epi file or a directory of them.[/red]")
        raise typer.Exit(2)

    records = _load(list(cases))

    log_path: Path | None = Path(log) if log else None
    if log_path is None:
        default_log = Path(os.environ.get("EPI_WITNESS_LOG") or "received.jsonl")
        log_path = default_log if default_log.exists() else None

    entries: list[dict] = []
    if log_path is not None:
        entries, error = _load_witness_entries(log_path)
        if error:
            console.print(f"[red]{escape(error)}[/red]")
            raise typer.Exit(2)

    _attach_witness(records, log_path, witness_pubkey, entries)

    readable = [record for record in records if not record.get("error")]
    in_period = [
        record
        for record in readable
        if _in_period(_date_of(record.get("created_at")), since, until)
    ]
    decisions = [_describe(record) for record in in_period]

    gaps = _delivery_gaps(entries, readable, since, until)
    expectations = _read_expectations(expect) if expect is not None else []
    never_sealed = _never_sealed(expectations, entries, readable)

    payload = _build_payload(
        decisions,
        log_path=log_path,
        since=since,
        until=until,
        gaps=gaps,
        never_sealed=never_sealed,
        expectations=expectations,
    )
    payload["sealed"]["files"] = len(readable)
    payload["sealed"]["decisions_in_period"] = len(decisions)
    payload["sealed"]["unreadable"] = len(records) - len(readable)

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_build_html(payload), encoding="utf-8")
        console.print(f"[green]Oversight report written:[/green] {out}")

    if as_json:
        console.print_json(json.dumps(payload))
    else:
        _print_tables(payload)

    gapped = bool(gaps or never_sealed or payload["witness"].get("mismatch") or payload["witness"].get("not_in_witness_log"))
    if fail_on_gaps and gapped:
        raise typer.Exit(1)


def _is_day(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True
