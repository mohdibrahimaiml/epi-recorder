"""
epi gateway - developer-facing entrypoint for the open EPI capture gateway.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

app = typer.Typer(help="Run the open-source AI capture gateway.")
console = Console()


def _env(name: str) -> str | None:
    value = (os.environ.get(name) or "").strip()
    return value or None


def _resolve_did(did: str | None) -> str | None:
    """--did wins, then EPI_GATEWAY_DID, then EPI_DID (same rule as record())."""
    value = (did or "").strip() or _env("EPI_GATEWAY_DID") or _env("EPI_DID")
    if value and not value.startswith("did:web:"):
        console.print(f"[red][FAIL][/red] DID must start with 'did:web:', got: {value}")
        raise typer.Exit(1)
    return value


def _signing_disabled() -> bool:
    return (_env("EPI_GATEWAY_DISABLE_SIGNING") or "").lower() in {"1", "true", "yes", "on"}


_SERVE_SETTINGS = "gateway-settings.json"


def _save_serve_settings(storage_dir: Path, did: str | None, witness_url: str | None) -> None:
    """Remember the running gateway's DID and witness URL (never the secret),
    so `epi gateway export` on the same --storage-dir uses them too."""
    import json

    try:
        storage_dir.mkdir(parents=True, exist_ok=True)
        (storage_dir / _SERVE_SETTINGS).write_text(
            json.dumps({"did": did, "witness_url": witness_url}, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _load_serve_settings(storage_dir: Path) -> dict:
    import json

    try:
        data = json.loads((storage_dir / _SERVE_SETTINGS).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _require_case_store(storage_dir: Path) -> None:
    """Refuse a storage dir without a case store instead of creating an empty one."""
    if not (storage_dir / "cases.sqlite3").is_file():
        console.print(
            f"[red][FAIL][/red] No gateway case store at {storage_dir} (cases.sqlite3 not found). "
            "Pass the --storage-dir that `epi gateway serve` uses."
        )
        raise typer.Exit(1)


def _witness_export(
    epi_path: Path, witness_url: str, witness_secret: str | None, case_id: str | None = None
) -> str:
    """Report an exported file to the customer witness, exactly as record() does.

    Outbox-first via epi_core.webhook.report_seal (bounded wait, never raises),
    so a delivery failure never fails the export. Returns the status line.
    """
    from epi_core.webhook import read_outbox, report_seal, split_witness_urls
    from epi_gateway.main import _gateway_witness_key_bytes

    urls = split_witness_urls(witness_url)
    if not urls:
        return "Witness: none"
    key_bytes = _gateway_witness_key_bytes()
    entry = report_seal(
        epi_path,
        urls=urls,
        secret=witness_secret,
        key_name=(_env("EPI_GATEWAY_SIGNING_KEY_NAME") or "default") if key_bytes else None,
        private_key_bytes=key_bytes,
        case_id=case_id,
    )
    if entry is None:
        return "Witness: QUEUED (could not stage report) — run epi witness flush"
    stored = next((e for e in read_outbox() if e.get("id") == entry.get("id")), entry)
    pending = list(stored.get("pending") or [])
    if not pending:
        return f"Witness: delivered to {', '.join(urls)}"
    _reason = _short_reason(stored.get("last_error"), urls)
    _hint = ""
    if "401" in _reason or "403" in _reason:
        _hint = (
            " — no secret set: export with EPI_WITNESS_SECRET (or --witness-secret)"
            if not witness_secret
            else " — witness secret changed — update EPI_WITNESS_SECRET"
        )
    return f"Witness: QUEUED ({_reason}){_hint} — run epi witness flush"


def _short_reason(error: object, urls: list[str]) -> str:
    """'http://x: <urlopen error [Errno 111] Connection refused>' -> 'Connection refused'."""
    import re

    reason = str(error or "delivery timed out")
    for url in urls:
        reason = reason.removeprefix(f"{url}: ")
    reason = re.sub(r"^<urlopen error (.*)>$", r"\1", reason.strip())
    # Windows words socket errors differently; normalise the common ones.
    if "10061" in reason or "actively refused" in reason:
        return "Connection refused"
    if "10060" in reason or "timed out" in reason.lower():
        return "Connection timed out"
    reason = re.sub(r"^\[(?:Errno|WinError) -?\d+\]\s*", "", reason)
    return reason[:80] or "delivery failed"


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Host interface to bind."),
    port: int = typer.Option(8787, "--port", help="Port for the capture gateway."),
    storage_dir: Path = typer.Option(
        Path("./evidence_vault"),
        "--storage-dir",
        help="Directory for append-only gateway capture batches.",
    ),
    batch_size: int = typer.Option(50, "--batch-size", min=1, help="Flush after this many events."),
    batch_timeout: float = typer.Option(
        2.0,
        "--batch-timeout",
        min=0.1,
        help="Flush buffered events after this many seconds.",
    ),
    retention_mode: str = typer.Option(
        "full_content",
        "--retention-mode",
        help="Retention mode for provider request/response bodies: redacted_hashes or full_content.",
    ),
    proxy_failure_mode: str = typer.Option(
        "fail-closed",
        "--proxy-failure-mode",
        help="What to do if upstream relay succeeds but EPI cannot persist the capture: fail-open or fail-closed.",
    ),
    access_token: str | None = typer.Option(
        None,
        "--access-token",
        help="Optional shared bearer token required for /api case-review routes.",
    ),
    users_file: Path | None = typer.Option(
        None,
        "--users-file",
        help="Optional JSON file with local gateway users for browser sign-in.",
    ),
    webhook_url: str | None = typer.Option(
        None,
        "--webhook-url",
        help="Optional webhook URL to POST when a case needs review (Slack, Teams, PagerDuty, etc.).",
    ),
    did: str | None = typer.Option(
        None,
        "--did",
        help="did:web identity bound into every exported case (manifest governance.did). Default: EPI_DID.",
    ),
    witness_url: str | None = typer.Option(
        None,
        "--witness-url",
        help="Customer witness endpoint(s), comma-separated; every export is reported (hash-only). Default: EPI_WITNESS_URL.",
    ),
    witness_secret: str | None = typer.Option(
        None,
        "--witness-secret",
        help="HMAC secret for witness delivery. Default: EPI_WITNESS_SECRET.",
    ),
    reload: bool = typer.Option(False, "--reload", help="Enable uvicorn auto-reload for development."),
    ssl_certfile: Path | None = typer.Option(
        None,
        "--ssl-certfile",
        help="Path to TLS certificate file (PEM) to enable HTTPS.",
    ),
    ssl_keyfile: Path | None = typer.Option(
        None,
        "--ssl-keyfile",
        help="Path to TLS private key file (PEM) to enable HTTPS.",
    ),
):
    """
    Start the open-source EPI gateway.

    This is the low-friction adoption path for AI teams that want to record
    consequential LLM traffic without building a control plane first.
    """

    from epi_cli._shared import require_extra

    require_extra("gateway", "uvicorn", "epi gateway serve")
    require_extra("gateway", "fastapi", "epi gateway serve")

    import uvicorn

    from epi_gateway.main import GatewayRuntimeSettings, require_auth_for_host

    require_auth_for_host(
        host,
        GatewayRuntimeSettings(
            access_token=access_token,
            users_file=str(users_file.resolve()) if users_file else None,
        ),
    )

    did = _resolve_did(did)
    witness_url = witness_url or _env("EPI_GATEWAY_WITNESS_URL") or _env("EPI_WITNESS_URL")
    witness_secret = witness_secret or _env("EPI_GATEWAY_WITNESS_SECRET") or _env("EPI_WITNESS_SECRET")

    storage_dir = storage_dir.resolve()
    # A restart without the flags keeps the identity and witness the gateway
    # last ran with (a routine reboot must not silently stop witnessing).
    _previous = _load_serve_settings(storage_dir)
    if not did and _previous.get("did"):
        did = _resolve_did(_previous["did"])
        console.print(f"[dim]DID kept from the previous run ({storage_dir / _SERVE_SETTINGS}).[/dim]")
    if not witness_url and _previous.get("witness_url"):
        witness_url = _previous["witness_url"]
        console.print(
            f"[dim]Witness URL kept from the previous run ({storage_dir / _SERVE_SETTINGS}); "
            "delete that file to stop witnessing.[/dim]"
        )
    _save_serve_settings(storage_dir, did, witness_url)
    previous_env = {key: os.environ.get(key) for key in (
        "EPI_GATEWAY_STORAGE_DIR",
        "EPI_GATEWAY_BATCH_SIZE",
        "EPI_GATEWAY_BATCH_TIMEOUT",
        "EPI_GATEWAY_RETENTION_MODE",
        "EPI_GATEWAY_PROXY_FAILURE_MODE",
        "EPI_GATEWAY_ACCESS_TOKEN",
        "EPI_GATEWAY_USERS_FILE",
        "EPI_GATEWAY_WEBHOOK_URL",
        "EPI_GATEWAY_DID",
        "EPI_GATEWAY_WITNESS_URL",
        "EPI_GATEWAY_WITNESS_SECRET",
    )}

    os.environ["EPI_GATEWAY_STORAGE_DIR"] = str(storage_dir)
    os.environ["EPI_GATEWAY_BATCH_SIZE"] = str(batch_size)
    os.environ["EPI_GATEWAY_BATCH_TIMEOUT"] = str(batch_timeout)
    os.environ["EPI_GATEWAY_RETENTION_MODE"] = retention_mode
    os.environ["EPI_GATEWAY_PROXY_FAILURE_MODE"] = proxy_failure_mode
    if access_token:
        os.environ["EPI_GATEWAY_ACCESS_TOKEN"] = access_token
    else:
        os.environ.pop("EPI_GATEWAY_ACCESS_TOKEN", None)
    if users_file:
        os.environ["EPI_GATEWAY_USERS_FILE"] = str(users_file.resolve())
    else:
        os.environ.pop("EPI_GATEWAY_USERS_FILE", None)
    if webhook_url:
        os.environ["EPI_GATEWAY_WEBHOOK_URL"] = webhook_url
    else:
        os.environ.pop("EPI_GATEWAY_WEBHOOK_URL", None)
    for key, value in (
        ("EPI_GATEWAY_DID", did),
        ("EPI_GATEWAY_WITNESS_URL", witness_url),
        ("EPI_GATEWAY_WITNESS_SECRET", witness_secret),
    ):
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)

    console.print("[bold]Starting EPI Gateway[/bold]")
    console.print(f"[dim]Capture endpoint:[/dim] http://{host}:{port}/capture")
    console.print(f"[dim]Cases API:[/dim]      http://{host}:{port}/api/cases")
    console.print(f"[dim]Storage:[/dim] {storage_dir}")
    console.print(f"[dim]Retention:[/dim] {retention_mode}")
    console.print(f"[dim]Failure mode:[/dim] {proxy_failure_mode}")
    if users_file:
        auth_label = f"local users ({users_file.resolve()})"
    elif access_token:
        auth_label = "shared token"
    else:
        auth_label = "disabled"
    console.print(f"[dim]Auth:[/dim] {auth_label}")
    if webhook_url:
        console.print(f"[dim]Webhook:[/dim] {webhook_url}")
    console.print(f"[dim]DID:[/dim] {escape(did or 'none')}")
    # The witness secret is never printed.
    console.print(f"[dim]Witness:[/dim] {escape(witness_url or 'none')}")
    scheme = "https" if ssl_certfile else "http"
    if ssl_certfile:
        console.print(f"[dim]TLS:[/dim] enabled ({ssl_certfile})")
    console.print("[dim]This is the open capture layer and shared reviewer backend.[/dim]")
    console.print()
    console.print("[bold cyan]Zero-code proxy adoption[/bold cyan] — point your existing SDK at this gateway:")
    console.print(f"  [green]OPENAI_BASE_URL[/green]={scheme}://{host}:{port}/v1  [dim]python my_script.py[/dim]")
    console.print(f"  [green]ANTHROPIC_BASE_URL[/green]={scheme}://{host}:{port}   [dim]python my_script.py[/dim]")
    console.print("[dim]All LLM calls are captured automatically — no code changes needed.[/dim]")
    console.print()

    # factory=True: build the app now, after the env above is set, so every
    # flag passed here (including --access-token and --storage-dir) reaches
    # the running app. Never touch ``epi_gateway.main.app`` here: accessing it
    # would build a second gateway from the default settings.
    uvicorn_kwargs: dict = {"host": host, "port": port, "reload": reload, "factory": True}
    if ssl_certfile:
        uvicorn_kwargs["ssl_certfile"] = str(ssl_certfile.resolve())
    if ssl_keyfile:
        uvicorn_kwargs["ssl_keyfile"] = str(ssl_keyfile.resolve())

    try:
        uvicorn.run("epi_gateway.main:create_app", **uvicorn_kwargs)
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@app.command("export")
def export_case(
    case_id: str = typer.Option(..., "--case-id", help="Shared case ID to export."),
    out: Path = typer.Option(..., "--out", help="Output .epi path."),
    storage_dir: Path = typer.Option(
        Path("./evidence_vault"),
        "--storage-dir",
        help="Directory that contains the gateway spool and SQLite case store.",
    ),
    did: str | None = typer.Option(
        None,
        "--did",
        help="did:web identity bound into the export (manifest governance.did). Default: EPI_DID, "
        "else the DID `epi gateway serve` was started with on this storage dir.",
    ),
    witness_url: str | None = typer.Option(
        None,
        "--witness-url",
        help="Customer witness endpoint(s), comma-separated. Default: EPI_WITNESS_URL, else the "
        "witness URL `epi gateway serve` was started with on this storage dir.",
    ),
    witness_secret: str | None = typer.Option(
        None,
        "--witness-secret",
        help="HMAC secret for witness delivery. Default: EPI_WITNESS_SECRET.",
    ),
):
    """
    Export one shared gateway-backed case to a portable `.epi` artifact.
    """

    from epi_gateway.main import _build_gateway_signer, _build_settings_from_env
    from epi_gateway.worker import EvidenceWorker

    storage_dir = storage_dir.resolve()
    out = out.resolve()
    _require_case_store(storage_dir)
    did = _resolve_did(did)
    worker = EvidenceWorker(storage_dir=storage_dir)
    settings = _build_settings_from_env()
    signer = _build_gateway_signer(settings)
    witness_url = witness_url or settings.witness_url
    witness_secret = witness_secret or settings.witness_secret
    # Same identity and witness as the gateway serving this storage dir.
    _served = _load_serve_settings(storage_dir)
    if not did and _served.get("did"):
        did = _resolve_did(_served["did"])
        console.print("[dim]Using the DID from `epi gateway serve` on this storage dir.[/dim]")
    if not witness_url and _served.get("witness_url"):
        witness_url = _served["witness_url"]
        console.print("[dim]Using the witness URL from `epi gateway serve` on this storage dir.[/dim]")

    try:
        result = worker.export_case(case_id, out, signer_function=signer, did_web=did)
    except KeyError as exc:
        console.print(f"[red][FAIL][/red] Case not found: {case_id}")
        raise typer.Exit(1) from exc

    console.print(f"[green][OK][/green] Exported {case_id} to {result.output_path}")
    console.print(f"[dim]Signed:[/dim] {'yes' if result.signed else 'no'}")
    if not result.signed and not _signing_disabled():
        console.print('[yellow]Unsigned — run "epi keys generate" first so exports are signed.[/yellow]')
    console.print(f"DID: {did or 'none'}", markup=False, highlight=False, soft_wrap=True)
    console.print(
        _witness_export(Path(result.output_path), witness_url, witness_secret, case_id)
        if witness_url
        else "Witness: none (set EPI_WITNESS_URL or --witness-url)",
        markup=False,
        soft_wrap=True,
        highlight=False,
    )


@app.command("add-user")
def add_user(
    username: str = typer.Argument(..., help="Username for the new gateway user."),
    role: str = typer.Option("reviewer", "--role", "-r", help="User role: admin, reviewer, or auditor."),
    display_name: str = typer.Option("", "--display-name", help="Display name shown in the UI."),
    password: str = typer.Option("", "--password", "-p", help="Password (prompted if not given)."),
    storage_dir: Path = typer.Option(Path("./evidence_vault"), "--storage-dir"),
):
    """
    Add or update a local gateway user.

    The user is written directly into the gateway database so they can sign in
    at the browser UI without restarting the server.
    """
    from epi_core.auth_local import hash_password, normalize_role
    from epi_gateway.worker import EvidenceWorker

    try:
        role = normalize_role(role)
    except ValueError as exc:
        console.print(f"[red][FAIL][/red] {exc}")
        raise typer.Exit(1) from exc

    if not password:
        password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        console.print(f"[red][FAIL][/red] {exc}")
        raise typer.Exit(1) from exc

    storage_dir = storage_dir.resolve()
    worker = EvidenceWorker(storage_dir=storage_dir)
    worker.sync_auth_users(
        [
            {
                "username": username,
                "password_hash": password_hash,
                "role": role,
                "display_name": display_name or username,
            }
        ],
        source="cli",
    )
    console.print(f"[green][OK][/green] User '[bold]{username}[/bold]' added as [cyan]{role}[/cyan]")


@app.command("list-users")
def list_users(
    storage_dir: Path = typer.Option(Path("./evidence_vault"), "--storage-dir"),
):
    """List all local gateway users stored in the database."""
    from rich.table import Table
    from epi_gateway.worker import EvidenceWorker

    storage_dir = storage_dir.resolve()
    worker = EvidenceWorker(storage_dir=storage_dir)
    users = worker.list_auth_users()

    if not users:
        console.print("[dim]No users found.[/dim]")
        return

    table = Table(title="Gateway Users", show_header=True, header_style="bold cyan")
    table.add_column("Username", style="green")
    table.add_column("Role", style="yellow")
    table.add_column("Display Name")
    table.add_column("Source", style="dim")

    for user in users:
        table.add_row(
            user.get("username", ""),
            user.get("role", ""),
            user.get("display_name", ""),
            user.get("source", ""),
        )

    console.print(table)


@app.command("hash-password")
def hash_password_cmd(
    password: str = typer.Option("", "--password", "-p", help="Password (prompted if not given)."),
) -> None:
    """Hash a password for EPI_GATEWAY_USERS_FILE (pbkdf2_sha256, 200k iters)."""
    from epi_core.auth_local import hash_password as _hash

    if not password:
        password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    try:
        console.print(_hash(password))
    except ValueError as exc:
        console.print(f"[red][FAIL][/red] {exc}")
        raise typer.Exit(1) from exc


@app.command("backup")
def backup(
    out: Path = typer.Option(..., "--out", "-o", help="Output .zip backup file."),
    storage_dir: Path = typer.Option(Path("./evidence_vault"), "--storage-dir"),
):
    """
    Back up the gateway storage to a ZIP archive.

    The archive contains the SQLite case database and all append-only event
    batches.  Restore by unzipping into your evidence_vault directory.
    """
    import zipfile as _zipfile
    from epi_gateway.worker import EvidenceWorker

    storage_dir = storage_dir.resolve()
    worker = EvidenceWorker(storage_dir=storage_dir)

    out = out.resolve()
    files_added = 0
    with _zipfile.ZipFile(out, "w", _zipfile.ZIP_DEFLATED) as zf:
        if worker.db_path.exists():
            zf.write(worker.db_path, "cases.sqlite3")
            files_added += 1
        if worker.events_path.exists():
            for event_file in sorted(worker.events_path.iterdir()):
                if event_file.is_file():
                    zf.write(event_file, f"events/{event_file.name}")
                    files_added += 1

    size_kb = out.stat().st_size // 1024
    console.print(f"[green][OK][/green] Backup written: {out} ({size_kb} KB, {files_added} files)")
    console.print(f"[dim]Restore: unzip {out.name} -d ./evidence_vault[/dim]")


@app.command("export-all")
def export_all(
    out_dir: Path = typer.Option(..., "--out-dir", "-o", help="Output directory for .epi artifacts."),
    storage_dir: Path = typer.Option(Path("./evidence_vault"), "--storage-dir"),
    status: str = typer.Option("", "--status", help="Filter by status (e.g. resolved)."),
):
    """
    Export all gateway cases to individual .epi artifacts.

    Useful before a server migration or for periodic compliance archives.
    """
    from epi_gateway.main import _build_gateway_signer, _build_settings_from_env
    from epi_gateway.worker import EvidenceWorker

    storage_dir = storage_dir.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    worker = EvidenceWorker(storage_dir=storage_dir)
    settings = _build_settings_from_env()
    signer = _build_gateway_signer(settings)
    _served = _load_serve_settings(storage_dir)
    did = _resolve_did(None) or (_resolve_did(_served["did"]) if _served.get("did") else None)
    if not settings.witness_url and _served.get("witness_url"):
        settings.witness_url = _served["witness_url"]

    cases = worker.list_cases(status=status or None)
    if not cases:
        console.print("[yellow]No cases found.[/yellow]")
        return

    console.print(f"Exporting {len(cases)} cases...")
    exported = 0
    for case in cases:
        case_id = case.get("case_id") or case.get("id", "")
        if not case_id:
            continue
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in case_id)
        out_path = out_dir / f"{safe_name}.epi"
        try:
            worker.export_case(case_id, out_path, signer_function=signer, did_web=did)
            console.print(f"  [green][OK][/green] {case_id}.epi")
            exported += 1
            if settings.witness_url:
                console.print(
                    "    " + _witness_export(out_path, settings.witness_url, settings.witness_secret, case_id),
                    markup=False,
                    soft_wrap=True,
                    highlight=False,
                )
        except Exception as exc:
            console.print(f"  [red][FAIL][/red] {case_id}: {exc}")

    console.print(f"[green][OK][/green] Exported {exported} cases to {out_dir}")
