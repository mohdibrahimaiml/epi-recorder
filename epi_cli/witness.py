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
    from epi_core.webhook import flush_outbox, outbox_path

    _effective_secret = secret if secret is not None else _secret()
    result = flush_outbox(
        secret=_effective_secret,
        timeout_seconds=timeout,
        path=outbox_path(),
    )
    if not result["entries"]:
        console.print("[dim]Nothing pending — every report in the outbox was delivered.[/dim]")
        return
    for url in result["delivered"]:
        console.print(f"[green]Delivered:[/green] {escape(url)}")
    for url, error in result["failed"].items():
        console.print(f"[red]Failed:[/red] {escape(url)} ({escape(str(error))})")
        code = _auth_status(str(error))
        if code and not _effective_secret:
            _plain(
                f"  No secret set, so the receiver refused the report (HTTP {code}). "
                "Set EPI_WITNESS_SECRET or pass --secret (same secret as the receiver)."
            )
        elif code:
            _plain(
                f"  The receiver rejected the secret (HTTP {code}). Use the same secret "
                "as the receiver: EPI_WITNESS_SECRET or --secret."
            )
    if not result["delivered"] and not result["failed"]:
        console.print("[dim]Nothing pending.[/dim]")
    if result["failed"]:
        _plain(
            "Still pending. Fix the URL/secret and flush again, or remove an entry "
            "with: epi witness drop <id>"
        )
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
