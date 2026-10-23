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
    except CheckError as exc:
        failures.append(str(exc))

    if failures:
        for failure in failures:
            _plain(f"FAIL: {failure}")
        raise typer.Exit(1)
    _plain("OK: hosted witness audited — signatures, chain and anchoring all check out.")
