"""`epi witness` — customer witness outbox management and receiver.

Every seal (with EPI_WITNESS_URL or witness_url= set) appends a hash-only
payload to the outbox and delivers it from a daemon thread. `flush` retries
whatever is undelivered; `status` lists pending, delivered and failed entries;
`drop` removes entries that can never be delivered (e.g. a wrong URL).

`serve` is the customer side: a small receiver that checks the HMAC and
appends each report to the log that `epi verify --witness-log` reads.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

app = typer.Typer(help="Customer witness: run the receiver, retry and inspect seal reports.")
console = Console()


def _secret() -> str | None:
    return os.environ.get("EPI_WITNESS_SECRET")


def _plain(text: str) -> None:
    console.print(text, markup=False, highlight=False, soft_wrap=True)


def _auth_status(error: str) -> str | None:
    """'401' / '403' when a delivery error is the receiver rejecting the secret."""
    import re

    match = re.search(r"\bHTTP(?: Error)? (401|403)\b", error)
    return match.group(1) if match else None


@app.command(name="flush")
def flush(
    secret: str | None = typer.Option(
        None, "--secret", help="HMAC secret for delivery (default: EPI_WITNESS_SECRET)."
    ),
    timeout: int = typer.Option(10, "--timeout", help="Per-request timeout in seconds."),
) -> None:
    """Retry every undelivered witness entry."""
    from epi_core.webhook import flush_outbox, outbox_path, split_witness_urls

    _effective_secret = secret if secret is not None else _secret()
    # Cloud-login fallback (same-source rule): with no explicit --secret or
    # env secret, use the secret saved by `epi cloud login` — but only for
    # outbox entries whose URL matches the saved witness_url. The saved
    # secret is never sent to any other URL.
    _resolver = None
    if _effective_secret is None:
        try:
            from epi_cli.cloud import saved_customer as _saved_preset_fn
        except Exception:
            _saved_preset_fn = None  # type: ignore
        if _saved_preset_fn is not None:
            try:
                _preset = _saved_preset_fn() or {}
            except Exception:
                _preset = {}
            _saved_urls = set(split_witness_urls(_preset.get("witness_url")))
            _saved_secret = _preset.get("witness_secret") or None
            if _saved_urls and _saved_secret:
                def _resolver(url: str, _urls=_saved_urls, _sec=_saved_secret):  # type: ignore[misc]
                    return _sec if str(url) in _urls else None
    result = flush_outbox(
        secret=_effective_secret,
        timeout_seconds=timeout,
        path=outbox_path(),
        secret_for_url=_resolver,
    )
    if not result["entries"]:
        console.print("[dim]Nothing pending — every report in the outbox was delivered.[/dim]")
        return
    for url in result["delivered"]:
        console.print(f"[green]Delivered:[/green] {escape(url)}")
    # Map failing urls back to outbox entry ids (for the drop hint on 400s).
    from epi_core.webhook import read_outbox as _read_outbox

    _url_to_id: dict[str, str] = {}
    try:
        for _e in _read_outbox(outbox_path()):
            for _u in _e.get("pending") or []:
                _url_to_id.setdefault(str(_u), str(_e.get("id")))
    except Exception:
        _url_to_id = {}
    import re as _re

    _saved_urls_for_hint: set[str] = set()
    _saved_customer: str | None = None
    if _effective_secret is None:
        try:
            from epi_core.webhook import split_witness_urls as _split
            from epi_cli.cloud import saved_customer as _hint_preset_fn
            _hint_preset = (_hint_preset_fn() or {}) if _hint_preset_fn else {}
            _saved_urls_for_hint = set(_split(_hint_preset.get("witness_url")))
            _saved_customer = _hint_preset.get("customer") or None
        except Exception:
            _saved_urls_for_hint = set()
    from epi_core.webhook import describe_witness_failure

    _summaries: list[str] = []
    for url, error in result["failed"].items():
        console.print(f"[red]Failed:[/red] {escape(url)} ({escape(str(error))})")
        code = _auth_status(str(error))
        _cloud = str(url) in _saved_urls_for_hint
        if _re.search(r"\bHTTP(?: Error)? 400\b", str(error)):
            _drop = f"epi witness drop {_url_to_id[url]}" if url in _url_to_id else "epi witness drop <id>"
            _plain(
                "  Rejected as malformed (HTTP 400): the stamp's format was refused, "
                f"so retrying won't help — remove it with `{_drop}`."
            )
            _summaries.append(
                "Nothing to retry: malformed stamps stay rejected. Remove "
                "them with `epi witness drop <id>` (see ids above)."
            )
            continue
        if code == "401" and not _effective_secret and not _cloud:
            _plain(
                f"  No secret set, so the receiver refused the report (HTTP {code}). "
                "Set EPI_WITNESS_SECRET or pass --secret (same secret as the receiver)."
            )
            _summaries.append(
                "Still pending. Fix the URL/secret and flush again, or remove an entry "
                "with: epi witness drop <id>"
            )
            continue
        info = describe_witness_failure(error, cloud_login=_cloud, customer=_saved_customer)
        _plain(f"  Not delivered: {info['reason']} — {info['fix']}")
        if info["status"] == 410:
            _summaries.append("Not retried: a closed customer can't receive reports.")
        elif info["status"] == 401 and _cloud:
            _summaries.append(
                "Still pending. Run epi cloud login — it sends the waiting reports for you."
            )
        elif info["status"] == 401:
            _summaries.append(
                "Still pending. Fix the URL/secret and flush again, or remove an entry "
                "with: epi witness drop <id>"
            )
        else:
            _summaries.append(
                "Still queued — flush again when it's reachable, or remove an entry "
                "with: epi witness drop <id>"
            )
    if not result["delivered"] and not result["failed"]:
        console.print("[dim]Nothing pending.[/dim]")
    if result["failed"]:
        for _line in dict.fromkeys(_summaries):
            _plain(_line)
        # Scripts and CI must see that reports are still undelivered.
        raise typer.Exit(1)


@app.command(name="status")
def status() -> None:
    """List pending, delivered and failed witness entries."""
    from epi_core.webhook import outbox_path, read_outbox

    entries = read_outbox(outbox_path())
    if not entries:
        console.print("[dim]Witness outbox is empty.[/dim]")
        return
    table = Table(title=f"Witness outbox ({outbox_path()})")
    table.add_column("id", no_wrap=True, min_width=8)  # needed for `epi witness drop`
    table.add_column("created (UTC)", no_wrap=True)
    table.add_column("workflow", no_wrap=True, min_width=8)
    table.add_column("case / file", overflow="fold")
    table.add_column("pending")
    table.add_column("delivered")
    table.add_column("last error", overflow="fold", ratio=1)
    for entry in entries:
        payload = entry.get("payload") or {}
        table.add_row(
            str(entry.get("id", ""))[:8],
            str(entry.get("created_at", ""))[5:19].replace("T", " "),
            str(payload.get("workflow_id", ""))[:8],
            str(payload.get("case_id") or ("sha " + str(payload.get("file_sha256") or "")[:8])),
            str(len(entry.get("pending") or [])),
            str(len(entry.get("delivered") or {})),
            str(entry.get("last_error") or "")[:160],
        )
    console.print(table)
    pending = sum(len(e.get("pending") or []) for e in entries)
    console.print(f"[dim]{len(entries)} entries, {pending} URLs pending.[/dim]")
    if pending:
        console.print(
            "[dim]Retry with `epi witness flush`; remove an undeliverable entry with "
            "`epi witness drop <id>`.[/dim]"
        )


def _print_entry(verb: str, entry: dict) -> None:
    payload = entry.get("payload") or {}
    pending = entry.get("pending") or []
    _plain(
        f"{verb} {str(entry.get('id', ''))[:8]} "
        f"(workflow {str(payload.get('workflow_id', ''))[:8]}, "
        f"pending: {', '.join(pending) or 'none'})"
    )


def _load_witness_entries(log_path: Path) -> tuple[list[dict], str | None]:
    """Every seal report in a witness log, newest shape or legacy JSONL.

    Returns ``(entries, error)``. Each entry is the report payload plus the
    ``received_at`` the receiver stamped. Signed docs (``witness.json`` with a
    ``lines`` array) and plain JSONL (``epi witness serve --out``) both work.
    """
    import json as _json

    try:
        raw = log_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        return [], f"{log_path} could not be read ({exc})"

    def _from_item(item: dict) -> dict | None:
        payload_raw = item.get("payload_raw")
        receipt = item.get("receipt")
        if isinstance(payload_raw, str) and isinstance(receipt, dict):
            try:
                inner = _json.loads(payload_raw)
            except Exception:
                return None
            if not isinstance(inner, dict):
                return None
            inner = dict(inner)
            inner.setdefault(
                "received_at",
                receipt.get("received_at") or item.get("received_at"),
            )
            return inner
        return item if item.get("workflow_id") else None

    items: list[dict] = []
    try:
        doc = _json.loads(raw) if raw.strip() else None
    except Exception:
        doc = None
    if isinstance(doc, dict) and isinstance(doc.get("lines"), list):
        items = [item for item in doc["lines"] if isinstance(item, dict)]
    else:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = _json.loads(line)
            except Exception:
                continue
            if isinstance(parsed, dict):
                items.append(parsed)

    entries = [entry for item in items if (entry := _from_item(item)) is not None]
    if not entries:
        return [], (
            f"{log_path} contains no witness reports — is it the --out file of "
            "`epi witness serve`?"
        )
    return entries, None


def _case_key(entry: dict) -> str:
    """The customer's grouping key: case id when the vendor sent one, else workflow."""
    return str(entry.get("case_id") or entry.get("workflow_id") or "")


def _expand_cases(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.epi")))
        elif path.suffix.lower() == ".epi":
            files.append(path)
        elif path.exists():
            files.extend(sorted(path.rglob("*.epi")))
    # De-duplicate while keeping the caller's order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for file in files:
        resolved = file.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(file)
    return unique

def _read_expectations(path: Path) -> list[str]:
    """Claim/case IDs the customer expects to find. First cell of each row."""
    import csv

    try:
        rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
    except Exception:
        return []
    header = {"case_id", "claim_id", "claim", "claim_number", "id", "case"}
    values: list[str] = []
    for index, row in enumerate(rows):
        cells = [cell.strip() for cell in row if cell.strip()]
        if not cells:
            continue
        if index == 0 and cells[0].lower() in header:
            continue
        values.append(cells[0])
    return values


def _entries_for_expectation(value: str, entries: list[dict]) -> list[dict]:
    """Reports that speak to this claim id: an exact case_id, or the goal text."""
    needle = value.strip().lower()
    found = []
    for entry in entries:
        case_id = str(entry.get("case_id") or "").strip().lower()
        goal = str(entry.get("goal") or "").strip().lower()
        if case_id == needle or (needle and needle in goal):
            found.append(entry)
    return found

def _print_expectations(expectations: list[dict], source: object) -> list[dict]:
    """Table of expected claim/case ids. Returns the MISSING rows."""
    missing = [item for item in expectations if item["status"] == "MISSING"]
    if not expectations:
        return missing
    table = Table(title=f"Expected cases ({source})")
    table.add_column("case", no_wrap=True)
    table.add_column("reports", justify="right")
    table.add_column("status", no_wrap=True)
    table.add_column("last received (UTC)")
    for item in expectations:
        ok = item["status"] == "FOUND"
        status = f"[green]{item['status']}[/green]" if ok else f"[red]{item['status']}[/red]"
        table.add_row(
            escape(item["case"]),
            str(item["reports"]),
            status,
            str(item["last_received"] or "-")[:19].replace("T", " "),
        )
    console.print(table)
    if missing:
        console.print(
            f"[red]{len(missing)} expected case(s) have no witnessed record:[/red] "
            + escape(", ".join(item["case"] for item in missing[:12]))
        )
    return missing


@app.command(name="report")
def report(
    log: Path | None = typer.Option(
        None,
        "--log",
        envvar="EPI_WITNESS_LOG",
        help="Witness log to read (default: EPI_WITNESS_LOG, then ./received.jsonl).",
    ),
    cases: list[Path] | None = typer.Option(
        None,
        "--cases",
        help="A .epi file or a directory of them, checked against the log. Repeatable.",
    ),
    witness_pubkey: str | None = typer.Option(
        None,
        "--witness-pubkey",
        envvar="EPI_WITNESS_PUBKEY",
        help="Pinned EPI witness key, for logs that carry signed receipts.",
    ),
    expect: Path | None = typer.Option(
        None,
        "--expect",
        help="CSV of claim/case IDs the customer expects. Any with no witnessed "
        "record is reported MISSING, not silently absent.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
    fail_on_unwitnessed: bool = typer.Option(
        False,
        "--fail-on-unwitnessed",
        help="Exit 1 when a case file is not in the log (scripted checks, CI gates).",
    ),
):
    """What the customer's witness knows, by case.

    Without ``--cases``: every case in the log, with how many times it was
    witnessed and when. With ``--cases``: each sealed file is matched to the log
    and reported as WITNESSED, NOT IN WITNESS LOG, MISMATCH or NOT CONFIRMED.

    This is the check a signature cannot make. A vendor who re-seals a changed
    decision signs a perfectly valid file; only the customer's own record shows
    that the bytes they were handed are not the bytes that were reported.
    """
    import json as _json

    from epi_core.container import EPIContainer

    log_path = Path(log) if log else Path(os.environ.get("EPI_WITNESS_LOG") or "received.jsonl")
    entries, error = _load_witness_entries(log_path)
    if error:
        console.print(f"[red]{escape(error)}[/red]")
        raise typer.Exit(2)

    by_case: dict[str, list[dict]] = {}
    by_workflow: dict[str, list[dict]] = {}
    for entry in entries:
        by_case.setdefault(_case_key(entry), []).append(entry)
        workflow = str(entry.get("workflow_id") or "")
        if workflow:
            by_workflow.setdefault(workflow, []).append(entry)

    case_files: list[Path] = _expand_cases(list(cases or []))
    results: list[dict] = []
    for file in case_files:
        try:
            manifest = EPIContainer.read_manifest(file)
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "path": str(file),
                    "workflow_id": "",
                    "case_id": "",
                    "status": "UNREADABLE",
                    "received_at": None,
                    "detail": f"not a readable .epi ({exc})",
                }
            )
            continue
        from epi_cli.verify import _check_witness_log

        check = _check_witness_log(file, manifest, log_path, witness_pubkey)
        workflow_id = str(getattr(manifest, "workflow_id", "") or "")
        matching = by_workflow.get(workflow_id) or []
        goal = str(getattr(manifest, "goal", "") or "").strip()
        status = str(check.get("status") or "")
        detail = str(check.get("detail") or "")

        # A vendor who re-seals a forged decision under a NEW workflow id is
        # "not in the log" by id alone - but the customer's log still names the
        # case they were told about. Match on the goal and say that instead.
        if status == "NOT IN WITNESS LOG" and goal:
            same_goal = [
                entry for entry in entries
                if str(entry.get("goal") or "").strip() == goal
            ]
            if same_goal:
                latest = max(
                    (str(entry.get("received_at") or "") for entry in same_goal),
                    default="",
                )
                status = "MISMATCH"
                detail = (
                    f"a different version of {goal!r} was reported to you "
                    f"({len(same_goal)} report(s), latest {latest or 'unknown time'}); "
                    "this copy was never reported"
                )

        label = str((matching[0].get("case_id") if matching else "") or "").strip() or goal
        results.append(
            {
                "path": str(file),
                "workflow_id": workflow_id,
                "case_id": label,
                "goal": goal,
                "status": status,
                "received_at": check.get("received_at"),
                "matches": check.get("matches", 0),
                "detail": detail,
            }
        )

    unwitnessed = [r for r in results if r["status"] != "WITNESSED"]

    expectations: list[dict] = []
    for value in _read_expectations(expect) if expect is not None else []:
        hits = _entries_for_expectation(value, entries)
        latest = max((str(entry.get("received_at") or "") for entry in hits), default="")
        expectations.append(
            {
                "case": value,
                "reports": len(hits),
                "status": "FOUND" if hits else "MISSING",
                "last_received": latest,
            }
        )
    missing = [item for item in expectations if item["status"] == "MISSING"]

    if as_json:
        payload = {
            "log": str(log_path),
            "reports": len(entries),
            "cases_in_log": {
                key: {
                    "reports": len(items),
                    "first_received": min(
                        (str(e.get("received_at") or "") for e in items), default=""
                    ),
                    "last_received": max(
                        (str(e.get("received_at") or "") for e in items), default=""
                    ),
                    "steps": max((int(e.get("steps") or 0) for e in items), default=0),
                }
                for key, items in sorted(by_case.items())
            },
            "checked_files": results,
            "unwitnessed": len(unwitnessed),
            "expected": expectations,
            "missing": len(missing),
        }
        console.print_json(_json.dumps(payload))
        raise typer.Exit(1 if (fail_on_unwitnessed and (unwitnessed or missing)) else 0)

    if not case_files:
        table = Table(title=f"Witness cases ({log_path})")
        table.add_column("case", no_wrap=True, min_width=8)
        table.add_column("reports", justify="right")
        table.add_column("steps", justify="right")
        table.add_column("first received (UTC)")
        table.add_column("last received (UTC)")
        for key, items in sorted(by_case.items()):
            times = sorted(str(e.get("received_at") or "") for e in items)
            table.add_row(
                escape(key[:8]),
                str(len(items)),
                str(max((int(e.get("steps") or 0) for e in items), default=0)),
                times[0][:19].replace("T", " ") if times else "-",
                times[-1][:19].replace("T", " ") if times else "-",
            )
        console.print(table)
        console.print(
            f"[dim]{len(entries)} report(s) across {len(by_case)} case(s). "
            "Check specific files with --cases <file-or-dir>.[/dim]"
        )
        if expectations:
            _print_expectations(expectations, expect)
            raise typer.Exit(1 if (fail_on_unwitnessed and missing) else 0)
        return

    if results:
        table = Table(title=f"Witness report ({log_path})")
        table.add_column("file", overflow="fold")
        table.add_column("case", overflow="fold")
        table.add_column("status", no_wrap=True)
        table.add_column("received (UTC)")
        table.add_column("detail", overflow="fold", ratio=1)
        for row in results:
            ok = row["status"] == "WITNESSED"
            status = f"[green]{row['status']}[/green]" if ok else f"[red]{row['status']}[/red]"
            table.add_row(
                escape(Path(row["path"]).name),
                escape((row["case_id"] or row["workflow_id"] or "-")[:60]),
                status,
                str(row["received_at"] or "-")[:19].replace("T", " "),
                escape(str(row["detail"] or "")[:160]),
            )
        console.print(table)
        console.print(
            f"[dim]{len(results)} file(s) checked against {len(entries)} report(s); "
            f"{len(results) - len(unwitnessed)} witnessed, {len(unwitnessed)} not.[/dim]"
        )

    if expectations:
        _print_expectations(expectations, expect)

    if (unwitnessed or missing) and not fail_on_unwitnessed:
        console.print(
            "[dim]A file that is not in the customer's log is not necessarily a forgery "
            "- but it was never reported to the customer. Re-run with "
            "--fail-on-unwitnessed to make that a non-zero exit.[/dim]"
        )
    raise typer.Exit(1 if (fail_on_unwitnessed and (unwitnessed or missing)) else 0)


@app.command(name="drop")
def drop(
    entry_id: str | None = typer.Argument(
        None,
        help="Outbox entry id, or a unique prefix such as the 8-char id `epi witness status` shows.",
    ),
    all_failed: bool = typer.Option(
        False, "--all-failed", help="Drop every entry that still has pending URLs (needs --yes)."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm --all-failed."),
) -> None:
    """Remove undeliverable entries from the witness outbox (e.g. a wrong URL).

    Dropping only stops the local retry: the sealed .epi file is unchanged,
    and the receiver never gets the dropped report.
    """
    from epi_core.webhook import drop_outbox_entries, match_outbox_ids, outbox_path, read_outbox

    path = outbox_path()
    if all_failed and entry_id:
        _plain("Give an entry id or --all-failed, not both.")
        raise typer.Exit(2)
    if not all_failed and not entry_id:
        _plain("Give an entry id (see `epi witness status`) or --all-failed.")
        raise typer.Exit(2)

    if all_failed:
        targets = [e for e in read_outbox(path) if e.get("pending")]
        if not targets:
            console.print("[dim]No entries with pending URLs — nothing to drop.[/dim]")
            return
        if not yes:
            for entry in targets:
                _print_entry("Would drop", entry)
            _plain(f"{len(targets)} entries would be dropped. Re-run with --yes to drop them.")
            raise typer.Exit(1)
        removed = drop_outbox_entries([str(e.get("id")) for e in targets], path)
        for entry in removed:
            _print_entry("Dropped", entry)
        _plain(f"Dropped {len(removed)} entries.")
        return

    matches = match_outbox_ids(entry_id or "", path)
    if not matches:
        _plain(f"No witness entry matches id {entry_id!r}. List ids with: epi witness status")
        raise typer.Exit(1)
    if len(matches) > 1:
        _plain(
            f"Id prefix {entry_id!r} is ambiguous; it matches {len(matches)} entries: "
            + ", ".join(m[:12] for m in matches)
            + ". Give more characters."
        )
        raise typer.Exit(1)
    _entry = next((e for e in read_outbox(path) if str(e.get("id")) == matches[0]), {})
    if not _entry.get("pending"):
        _plain(
            "That entry was already delivered; there is nothing to drop. "
            "(drop is for reports that can never be delivered.)"
        )
        return
    removed = drop_outbox_entries(matches, path)
    if not removed:  # pragma: no cover - removed by a concurrent drop
        _plain("Entry already gone.")
        return
    _print_entry("Dropped", removed[0])


@app.command(name="serve")
def serve(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Interface to listen on (default: this machine only). Use 0.0.0.0 only "
        "behind a TLS-terminating reverse proxy.",
    ),
    port: int = typer.Option(8099, "--port", help="Port to listen on."),
    out: Path = typer.Option(
        Path("received.jsonl"), "--out", help="Append-only witness log to write."
    ),
    secret: str | None = typer.Option(
        None,
        "--secret",
        help="Shared HMAC secret agreed with the vendor (default: EPI_WITNESS_SECRET).",
    ),
    insecure_no_secret: bool = typer.Option(
        False,
        "--insecure-no-secret",
        help="Run without an HMAC secret: anyone who can reach the port can add entries.",
    ),
) -> None:
    """Run the customer witness receiver (the vendor's EPI_WITNESS_URL points here).

    Each hash-only seal report is HMAC-checked, stamped with received_at and
    appended to --out. Check a file later with
    `epi verify run.epi --policy strict --witness-log received.jsonl`.
    """
    from epi_core import witness_receiver

    secret = secret if secret is not None else _secret()
    if not secret and not insecure_no_secret:
        _plain(
            "Refusing to start without a shared secret: set EPI_WITNESS_SECRET or pass "
            "--secret (the vendor uses the same value). For a local trial only, pass "
            "--insecure-no-secret."
        )
        raise typer.Exit(2)

    out = out.expanduser().resolve()
    try:
        server = witness_receiver.make_server(host, port, out=out, secret=secret or None)
    except OSError as exc:
        _plain(witness_receiver.bind_error_message(host, port, exc))
        raise typer.Exit(2) from exc

    url = witness_receiver.vendor_url(host, server.server_port)
    _plain(
        f"Witness receiver listening on {host}:{server.server_port} "
        f"(HMAC check {'on' if secret else 'OFF'})"
    )
    _plain(f"Give the vendor:  EPI_WITNESS_URL={url}")
    if secret:
        _plain("                  EPI_WITNESS_SECRET=<the same secret this receiver uses>")
    if host in ("", "0.0.0.0", "::"):
        _plain(
            "                  (replace <this-host> with your public https:// address "
            "behind a TLS reverse proxy)"
        )
    _plain(f"Witness log:      {out}")
    _plain(f"Check a file:     epi verify run.epi --policy strict --witness-log {out}")
    if not secret:
        _plain("WARNING: no secret - any well-formed report from anyone is kept.")
    _plain("Press Ctrl-C to stop.")
    witness_receiver.serve_forever(server)


def _fetch_json(url: str, timeout: int) -> dict:
    """GET JSON over HTTPS (stdlib). Raises CheckError on any failure."""
    import urllib.request

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception as exc:
        raise CheckError(f"GET {url} failed: {exc}") from exc


def _fetch_text_lines(url: str, timeout: int) -> list[str]:
    import urllib.request

    req = urllib.request.Request(url, headers={"Accept": "application/x-ndjson"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.read().decode("utf-8").splitlines()
    except Exception as exc:
        raise CheckError(f"GET {url} failed: {exc}") from exc


class CheckError(Exception):
    """A failed audit step (message is shown to the reviewer)."""


def _chain_verify(envelopes: list[dict]) -> dict[str, dict]:
    """Recompute the hash chain. Returns per-day {count, head}. Raises CheckError."""
    import hashlib

    prev = "GENESIS"
    by_day: dict[str, dict] = {}
    for index, env in enumerate(envelopes):
        seq = env.get("seq")
        if seq != index + 1:
            raise CheckError(f"chain broken at line {index + 1}: seq is {seq}, want {index + 1}")
        if env.get("prev_hash") != prev:
            raise CheckError(f"chain broken at seq {seq}: prev_hash does not link")
        inner = hashlib.sha256(str(env.get("payload_raw", "")).encode()).hexdigest()
        stamp = str(env.get("received_at", ""))
        recomputed = hashlib.sha256(f"{prev}{inner}{stamp}".encode()).hexdigest()
        if recomputed != env.get("entry_hash"):
            raise CheckError(f"chain broken at seq {seq}: entry_hash mismatch (edited line?)")
        prev = str(env.get("entry_hash"))
        day = str(env.get("received_at", ""))[:10]
        slot = by_day.setdefault(day, {"count": 0, "head": ""})
        slot["count"] += 1
        slot["head"] = prev
    return by_day


def _canonical_checkpoint(inbox: str, day: str, count: int, head: str) -> bytes:
    return json.dumps(
        {"inbox": inbox, "day": day, "count": count, "head_hash": head},
        separators=(",", ":"),
    ).encode("utf-8")


def _verify_ed25519(pub_hex: str, message: bytes, sig_hex: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex)).verify(
            bytes.fromhex(sig_hex), message
        )
        return True
    except (InvalidSignature, ValueError):
        return False


def _verify_anchor(anchor_pem: str, message: bytes, sig_der: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    try:
        key = load_pem_public_key(anchor_pem.encode("utf-8"))
        assert isinstance(key, ec.EllipticCurvePublicKey)
        key.verify(sig_der, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, AssertionError):
        return False


def _load_mirror(mirror: str, inbox_id: str, timeout: int) -> tuple[dict, dict]:
    """Load the public mirror: an https base URL or a local directory clone."""
    base = str(mirror).rstrip("/")
    local = Path(base)
    if local.is_dir():
        cp_path = local / "checkpoints" / f"{inbox_id}.json"
        key_path = local / "witness-key.json"
        if not cp_path.is_file():
            raise CheckError(f"mirror has no checkpoints for {inbox_id} ({cp_path})")
        try:
            cp_doc = json.loads(cp_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CheckError(f"mirror checkpoints unreadable: {exc}") from exc
        keys: dict = {}
        if key_path.is_file():
            try:
                keys = json.loads(key_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise CheckError(f"mirror witness key unreadable: {exc}") from exc
        return cp_doc, keys
    return (
        _fetch_json(f"{base}/checkpoints/{inbox_id}.json", timeout),
        _fetch_json(f"{base}/witness-key.json", timeout),
    )


def _rotation_documented(
    live_keys: dict, mirror_keys: dict, live_pub: str, mirror_pub: str
) -> bool:
    """A key change is acceptable only if one side names the other as a previous key."""
    for doc, other in ((live_keys or {}, mirror_pub), (mirror_keys or {}, live_pub)):
        previous = doc.get("previous_witness_ed25519_pub_hexes") or []
        if isinstance(previous, list) and any(
            str(item).lower() == str(other).lower() for item in previous
        ):
            return True
    return False


def _compare_mirror(
    live_cps: list[dict], mirror_cps: list[dict], live_keys: dict, mirror_keys: dict
) -> list[str]:
    """Cross-check the mirror against the live witness. Days only on the live
    side are fine (the mirror lags by up to a day); anything else is history."""
    failures: list[str] = []
    live_by_day = {str(cp.get("day")): cp for cp in live_cps}
    for mirrored in mirror_cps:
        day = str(mirrored.get("day"))
        live = live_by_day.get(day)
        if live is None:
            failures.append(
                f"mirror day {day} is missing from the live witness (history rewritten)"
            )
            continue
        if (live.get("count"), live.get("head_hash")) != (
            mirrored.get("count"),
            mirrored.get("head_hash"),
        ):
            failures.append(f"mirror day {day} differs from the live witness (history rewritten)")
        elif str(live.get("signature")) != str(mirrored.get("signature")):
            failures.append(f"mirror day {day}: signature differs from the live witness")
    live_pub = str((live_keys or {}).get("witness_ed25519_pub_hex") or "")
    mirror_pub = str((mirror_keys or {}).get("witness_ed25519_pub_hex") or "")
    if live_pub and mirror_pub and live_pub.lower() != mirror_pub.lower():
        if not _rotation_documented(live_keys or {}, mirror_keys or {}, live_pub, mirror_pub):
            failures.append(
                "witness key changed without a key-rotation entry "
                f"(live {live_pub[:16]}…, mirror {mirror_pub[:16]}…)"
            )
    return failures


@app.command(name="check")
def check(
    inbox_url: str = typer.Option(
        ..., "--inbox-url", help="Hosted inbox base URL, e.g. https://cloud.epilabs.org/w/inb_abc."
    ),
    export: Path | None = typer.Option(
        None, "--export", help="Local export.jsonl to cross-check (default: fetched)."
    ),
    chain: Path | None = typer.Option(None, "--chain", help="Local chain.jsonl (offline mode)."),
    checkpoints: Path | None = typer.Option(
        None, "--checkpoints", help="Local checkpoints JSON (offline mode)."
    ),
    offline: bool = typer.Option(False, "--offline", help="Verify local files only; no network."),
    mirror: str | None = typer.Option(
        None,
        "--mirror",
        help=(
            "Public mirror base URL or local directory clone to cross-check against "
            "(checkpoints/<inbox>.json + witness-key.json)."
        ),
    ),
    allow_http: bool = typer.Option(
        False, "--allow-http", help="Allow http:// inbox URLs (local trials only)."
    ),
    timeout: int = typer.Option(15, "--timeout", help="Per-request timeout in seconds."),
) -> None:
    """Audit EPI Labs itself: verify checkpoint signatures, the hash chain,
    and the Rekor anchoring of a hosted witness inbox.

    Online: `epi witness check --inbox-url https://cloud.epilabs.org/w/inb_abc`
    Offline: add --offline with --chain/--checkpoints files (--export optional).
    """
    import hashlib

    base = inbox_url.rstrip("/")
    if not (base.startswith("https://") or (allow_http and base.startswith("http://"))):
        _plain("Give an https:// inbox URL (or pass --allow-http for a local trial).")
        raise typer.Exit(2)

    failures: list[str] = []
    try:
        if checkpoints is not None:
            cp_doc = json.loads(checkpoints.read_text(encoding="utf-8"))
        elif offline:
            raise CheckError("offline mode needs --checkpoints FILE")
        else:
            cp_doc = _fetch_json(f"{base}/checkpoints", timeout)
        inbox_id = base.rsplit("/", 1)[-1]
        if cp_doc.get("inbox", inbox_id) != inbox_id:
            raise CheckError("checkpoints are for a different inbox")
        cps = cp_doc.get("checkpoints", [])

        if chain is not None:
            lines = chain.read_text(encoding="utf-8").splitlines()
        elif offline:
            raise CheckError("offline mode needs --chain FILE")
        else:
            lines = _fetch_text_lines(f"{base}/chain.jsonl", timeout)
        envelopes = [json.loads(line) for line in lines if line.strip()]
        by_day = _chain_verify(envelopes)
        _plain(f"Chain: {len(envelopes)} entries recomputed, links intact.")

        if export is not None:
            raw_lines = [
                line for line in export.read_text(encoding="utf-8").splitlines() if line.strip()
            ]
            payloads = [str(e.get("payload_raw")) for e in envelopes]
            if raw_lines != payloads:
                raise CheckError("export.jsonl does not match the audited chain payloads")
            _plain(f"Export: {len(raw_lines)} lines match the chain byte for byte.")

        if offline:
            keys = {"witness_ed25519_pub_hex": None, "anchor_p256_pem": None}
        else:
            origin = base.split("/w/")[0]
            keys = _fetch_json(f"{origin}/.well-known/epi-witness-key.json", timeout)
        witness_pub = keys.get("witness_ed25519_pub_hex")
        if not witness_pub:
            raise CheckError("witness public key is not published yet")
        for cp in cps:
            canonical = _canonical_checkpoint(inbox_id, cp["day"], cp["count"], cp["head_hash"])
            if not _verify_ed25519(witness_pub, canonical, cp["signature"]):
                raise CheckError(f"checkpoint {cp['day']}: Ed25519 signature INVALID")
            day_info = by_day.get(cp["day"])
            same = (
                day_info
                and day_info["count"] == cp["count"]
                and day_info["head"] == cp["head_hash"]
            )
            if not same:
                have = day_info["count"] if day_info else 0
                raise CheckError(
                    f"checkpoint {cp['day']}: chain has {have} entries, "
                    f"checkpoint says {cp['count']}"
                )
            _plain(f"Checkpoint {cp['day']}: signature valid, {cp['count']} entries, head matches.")
            uuid = cp.get("rekor_uuid")
            if uuid and not offline:
                entry = _fetch_json(
                    f"https://rekor.sigstore.dev/api/v1/log/entries/{uuid}", timeout
                )
                body = entry.get("body", {})
                if isinstance(body, str):
                    import base64

                    body = json.loads(base64.b64decode(body))
                want = hashlib.sha256(canonical).hexdigest()
                got = ((body.get("spec") or {}).get("data") or {}).get("hash", {}).get("value")
                anchor_pem = keys.get("anchor_p256_pem")
                sig_b64 = ((body.get("spec") or {}).get("signature") or {}).get("content")
                if got != want:
                    raise CheckError(f"checkpoint {cp['day']}: Rekor entry hash does not match")
                if not anchor_pem or not sig_b64:
                    raise CheckError(f"checkpoint {cp['day']}: Rekor entry lacks anchor signature")
                import base64

                if not _verify_anchor(anchor_pem, canonical, base64.b64decode(sig_b64)):
                    raise CheckError(f"checkpoint {cp['day']}: Rekor anchor signature INVALID")
                _plain(f"Rekor: entry {uuid[:12]}… present, hash matches, anchor signature valid.")
            elif uuid:
                _plain(f"Rekor: {uuid[:12]}… recorded (offline: not re-checked).")
            else:
                _plain(f"Checkpoint {cp['day']}: not yet anchored (signed only).")

        if mirror:
            mirror_doc, mirror_keys = _load_mirror(mirror, inbox_id, timeout)
            mirror_cps = mirror_doc.get("checkpoints", [])
            if not isinstance(mirror_cps, list):
                raise CheckError("mirror checkpoints document is malformed")
            mismatches = _compare_mirror(cps, mirror_cps, keys or {}, mirror_keys)
            if mismatches:
                raise CheckError("; ".join(mismatches))
            _plain(
                f"Mirror: {len(mirror_cps)} checkpoint(s) match the live witness "
                "(history not rewritten)."
            )
    except CheckError as exc:
        failures.append(str(exc))

    if failures:
        for failure in failures:
            _plain(f"FAIL: {failure}")
        raise typer.Exit(1)
    _plain("OK: hosted witness audited — signatures, chain and anchoring all check out.")
