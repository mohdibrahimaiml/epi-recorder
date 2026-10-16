"""`epi cloud` — push selected runs to the EPI Cloud Evidence Room.

The open-source recorder, sealing, and verification stay free and offline.
This command only uploads runs the vendor *selects* (disputes, samples,
audit requests) to their Evidence Room; every run's full `.epi` belongs in
the customer's own bucket (M4), and every run is witness-reported regardless.

Credentials: flags win, then EPI_CLOUD_URL / EPI_CLOUD_ORG / EPI_CLOUD_API_KEY,
then `epi cloud login` (saved to ~/.epi/cloud.json, mode 0600).
"""

from __future__ import annotations

import hashlib
import json
import os
import zlib
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

app = typer.Typer(help="EPI Cloud Evidence Room: push selected runs, check status.")
console = Console()

MAX_FILE_BYTES = 25 * 1024 * 1024
CONFIG_NAME = "cloud.json"


def _state_dir() -> Path:
    override = os.getenv("EPI_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".epi"


def _config_path() -> Path:
    return _state_dir() / CONFIG_NAME


def load_config() -> dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_creds(url: str | None, org: str | None, api_key: str | None) -> dict[str, str]:
    """Flags > environment > saved login. Raises Exit(2) when incomplete.

    The saved file uses org_id/api_key (written by `login`); the legacy
    org/key spellings are still honored so older saved logins keep working.
    """
    cfg = load_config()
    final = {
        "url": (url or os.getenv("EPI_CLOUD_URL") or cfg.get("url") or "").rstrip("/"),
        "org": org or os.getenv("EPI_CLOUD_ORG") or cfg.get("org_id") or cfg.get("org") or "",
        "key": api_key
        or os.getenv("EPI_CLOUD_API_KEY")
        or cfg.get("api_key")
        or cfg.get("key")
        or "",
    }
    missing = [name for name in ("url", "org", "key") if not final[name]]
    if missing:
        console.print(
            f"[red][FAIL][/red] Missing {', '.join(missing)}. "
            "Pass flags, set EPI_CLOUD_URL/EPI_CLOUD_ORG/EPI_CLOUD_API_KEY, "
            "or run [cyan]epi cloud login[/cyan]."
        )
        raise typer.Exit(2)
    return final


def _client(creds: dict[str, str]):
    import httpx

    return httpx.Client(
        base_url=creds["url"],
        headers={"Authorization": f"Bearer {creds['key']}"},
        timeout=60.0,
    )


def file_hashes(path: Path) -> tuple[str, int, int]:
    """SHA-256 hex, CRC-32, and size of the file (streamed, never fully buffered)."""
    sha = hashlib.sha256()
    crc = 0
    size = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            sha.update(chunk)
            crc = zlib.crc32(chunk, crc)
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                raise ValueError(f"{path} is larger than 25 MB; the Evidence Room rejects it.")
    return sha.hexdigest(), crc & 0xFFFFFFFF, size


def read_manifest(path: Path) -> str:
    """Raw manifest.json text from the .epi container (client-extracted; the
    server never unzips, so a bad container fails here, not there)."""
    import zipfile

    try:
        with zipfile.ZipFile(path) as zf:
            return zf.read("manifest.json").decode("utf-8")
    except Exception as exc:
        raise ValueError(f"{path} is not a readable .epi container: {exc}") from exc


@app.command("login")
def login(
    url: str | None = typer.Option(
        None,
        "--url",
        help="EPI Cloud base URL (default EPI_CLOUD_URL or cloud.epilabs.org).",
    ),
    org: str | None = typer.Option(
        None, "--org", help="Organisation id (org_...). Omit for browser login."
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help="API key (epik_...). Flag version only; prompts when omitted.",
    ),
) -> None:
    """Save Evidence Room credentials (url/org_id/api_key) for push and status.

    No flags: browser device flow — this terminal shows a short code,
    you type it at cloud.epilabs.org/auth/device, and the CLI receives
    a push-only key automatically. With --org/--api-key: automation
    version (flags win).
    """
    base = (url or os.getenv("EPI_CLOUD_URL") or "https://cloud.epilabs.org").rstrip("/")
    # Flag/automation version: org + key supplied explicitly.
    if org:
        key = api_key or os.getenv("EPI_CLOUD_API_KEY")
        if not key:
            key = typer.prompt("API key", hide_input=True)
        if not key:
            console.print("[red][FAIL][/red] No API key given.")
            raise typer.Exit(2)
        _save_flag_login(base, org, key)
        return
    if api_key:
        console.print("[red][FAIL][/red] --api-key needs --org.")
        console.print("[dim]Or run [cyan]epi cloud login[/cyan] with no flags.[/dim]")
        raise typer.Exit(2)
    _device_login(base)


def _save_flag_login(base: str, org: str, api_key: str) -> None:
    creds = {"url": base, "org": org, "key": api_key}
    try:
        with _client(creds) as client:
            res = client.get(f"/v1/orgs/{org}/artifacts")
        if res.status_code == 401 or res.status_code == 403:
            console.print("[red][FAIL][/red] The key was rejected (check org and key).")
            raise typer.Exit(1)
        res.raise_for_status()
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Could not reach EPI Cloud: {escape(str(exc))}")
        raise typer.Exit(1) from exc
    _write_config(base, org, api_key)


def _write_config(base: str, org: str, api_key: str) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"url": base, "org_id": org, "api_key": api_key}, indent=2),
        encoding="utf-8",
    )
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    console.print(f"[green][OK][/green] Saved to {path} (mode 0600 where supported).")


def _device_login(base: str) -> None:
    """Browser device flow (RFC 8628): show a user code, poll for key.

    The short user code is typed on cloud.epilabs.org/auth/device by the
    person at this terminal. The long device secret never leaves this
    machine. Polls every 5 s on a dedicated rate-limit bucket and backs
    off on 429 so sign-in stays usable.
    """
    import time
    import webbrowser

    import httpx

    console.print("[bold]EPI Cloud login[/bold]")
    try:
        with httpx.Client(base_url=base, timeout=30.0) as client:
            res = client.post("/auth/device/start")
            res.raise_for_status()
            data = res.json()
    except Exception as exc:
        console.print(f"[red][FAIL][/red] No cloud at {escape(base)}.")
        console.print(f"[dim]{escape(str(exc))}[/dim]")
        raise typer.Exit(1) from exc
    code = data.get("device_code", "")
    user_code = data.get("user_code", "")
    verify_url = data.get("verification_url", f"{base}/auth/device")
    interval = int(data.get("interval", 5) or 5)
    if not code or not user_code:
        console.print("[red][FAIL][/red] Login failed (no device code).")
        raise typer.Exit(1)
    console.print("Enter this code in your browser (only this computer):")
    console.print(f"[bold cyan]{escape(str(user_code))}[/bold cyan]")
    console.print(f"[dim]Page:[/dim] {verify_url}")
    console.print("[dim]A browser window will open; type the code there.[/dim]")
    try:
        webbrowser.open(verify_url)
    except Exception:
        pass
    deadline = time.time() + 10 * 60
    org_id = ""
    raw_key = ""
    try:
        with httpx.Client(base_url=base, timeout=30.0) as client:
            while time.time() < deadline:
                try:
                    st = client.get(f"/auth/device/{code}/status")
                except Exception:
                    time.sleep(interval)
                    continue
                if st.status_code == 404:
                    console.print("[red][FAIL][/red] Device code unknown.")
                    console.print("[dim]Retry login.[/dim]")
                    raise typer.Exit(1)
                if st.status_code == 429:
                    wait = interval * 2
                    try:
                        retry = st.headers.get("retry-after")
                        if retry is not None:
                            wait = max(wait, int(retry))
                    except Exception:
                        pass
                    time.sleep(wait)
                    continue
                try:
                    body = st.json()
                except Exception:
                    time.sleep(interval)
                    continue
                if body.get("status") == "authorized":
                    if body.get("api_key"):
                        org_id = str(body.get("org_id", ""))
                        raw_key = str(body.get("api_key", ""))
                        break
                    console.print("[red][FAIL][/red] Key already retrieved.")
                    console.print("[dim]Run login again for a new code.[/dim]")
                    raise typer.Exit(1)
                if body.get("status") == "expired":
                    console.print("[red][FAIL][/red] Code expired. Retry login.")
                    raise typer.Exit(1)
                time.sleep(interval)
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Login polling failed: {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if not raw_key or not org_id:
        console.print("[red][FAIL][/red] Login did not complete in time.")
        raise typer.Exit(1)
    _write_config(base, org_id, raw_key)
    console.print("[green][OK][/green] This computer authorized (push-only key).")
    console.print(f"[dim]Org: {org_id} — revoke anytime from cloud.epilabs.org.[/dim]")


@app.command("push")
def push(
    file: Path = typer.Argument(..., help="Sealed .epi file to push (a selected run)."),
    agent: str | None = typer.Option(
        None, "--agent", help="Agent name as registered in EPI Cloud."
    ),
    reason: str = typer.Option("other", "--reason", help="dispute|sample|audit_request|other."),
    sample: float | None = typer.Option(
        None, "--sample", help="Push ~N%% of runs (deterministic per file hash), e.g. --sample 1."
    ),
    url: str | None = typer.Option(None, "--url"),
    org: str | None = typer.Option(None, "--org"),
    api_key: str | None = typer.Option(None, "--api-key"),
) -> None:
    """Push one selected .epi file to the Evidence Room (init + streamed PUT)."""
    if reason not in ("dispute", "sample", "audit_request", "other"):
        console.print("[red][FAIL][/red] --reason must be dispute|sample|audit_request|other.")
        raise typer.Exit(2)
    if not file.is_file():
        console.print(f"[red][FAIL][/red] No such file: {file}")
        raise typer.Exit(2)
    try:
        digest, crc, size = file_hashes(file)
        manifest_json = read_manifest(file)
    except ValueError as exc:
        console.print(f"[red][FAIL][/red] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if sample is not None:
        if not 0 < sample <= 100:
            console.print("[red][FAIL][/red] --sample must be between 0 (exclusive) and 100.")
            raise typer.Exit(2)
        if int(digest[:8], 16) % 100 >= sample:
            console.print(f"[dim]Skipped by --sample {sample}%% for this file.[/dim]")
            return
    creds = resolve_creds(url, org, api_key)
    try:
        with _client(creds) as client:
            init = client.post(
                f"/v1/orgs/{creds['org']}/artifacts/init",
                json={
                    "manifest_json": manifest_json,
                    "claimed_sha256": digest,
                    "claimed_crc32": crc,
                    "size_bytes": size,
                    "agent": agent,
                    "reason": reason,
                },
            )
            if init.status_code == 400:
                console.print(f"[red][FAIL][/red] Rejected: {escape(init.text[:300])}")
                raise typer.Exit(1)
            init.raise_for_status()
            created = init.json()
            if created.get("deduped"):
                console.print(f"[green][OK][/green] Already in the Evidence Room: {created['id']}")
                return
            put_url = created.get("put_url")
            if not put_url:
                console.print("[red][FAIL][/red] Server returned no upload URL.")
                raise typer.Exit(1)
            with file.open("rb") as fh:
                put = client.put(
                    put_url,
                    content=fh,
                    headers={"Content-Length": str(size)},
                )
            if put.status_code == 409:
                console.print(f"[green][OK][/green] Already stored: {created['id']}")
                return
            put.raise_for_status()
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Push failed: {escape(str(exc))}")
        raise typer.Exit(1) from exc
    console.print(f"[green][OK][/green] Pushed {file.name} as {created['id']}")
    console.print(
        f"[dim]Seal: {created.get('signature_check')} · "
        f"Witness: {created.get('witness_status')}[/dim]"
    )


@app.command("status")
def status(
    artifact_id: str | None = typer.Argument(None, help="Artifact id (default: list)."),
    url: str | None = typer.Option(None, "--url"),
    org: str | None = typer.Option(None, "--org"),
    api_key: str | None = typer.Option(None, "--api-key"),
) -> None:
    """List Evidence Room files, or show one artifact."""
    creds = resolve_creds(url, org, api_key)
    try:
        with _client(creds) as client:
            if artifact_id:
                res = client.get(f"/v1/orgs/{creds['org']}/artifacts/{artifact_id}")
                res.raise_for_status()
                data = res.json()
                console.print(f"[bold]{data.get('id')}[/bold] ({data.get('upload_state')})")
                for field in (
                    "workflow_id",
                    "goal",
                    "sealed_at",
                    "key_fingerprint",
                    "signature_check",
                    "witness_status",
                    "reason",
                    "size_bytes",
                    "retention_until",
                ):
                    console.print(f"  {field}: {escape(str(data.get(field)))}")
            else:
                res = client.get(f"/v1/orgs/{creds['org']}/artifacts")
                res.raise_for_status()
                rows = res.json().get("artifacts", [])
                if not rows:
                    console.print("[dim]Evidence Room is empty.[/dim]")
                    return
                cols = ("id", "goal", "signature_check", "witness_status", "reason")
                table = Table(title="Evidence Room")
                for col in cols:
                    table.add_column(col, overflow="fold")
                for row in rows:
                    table.add_row(*[str(row.get(col, ""))[:40] for col in cols])
                console.print(table)
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Status failed: {escape(str(exc))}")
        raise typer.Exit(1) from exc


storage_app = typer.Typer(help="Customer-owned bucket: target, probe, outbox.")
app.add_typer(storage_app, name="storage")


@storage_app.command("show")
def storage_show(
    url: str | None = typer.Option(None, "--url"),
    org: str | None = typer.Option(None, "--org"),
    api_key: str | None = typer.Option(None, "--api-key"),
) -> None:
    """Show the registered customer bucket and the local upload outbox."""
    from epi_core.storage_sink import pending_uploads, storage_outbox_path

    creds = resolve_creds(url, org, api_key)
    try:
        with _client(creds) as client:
            res = client.get(f"/v1/orgs/{creds['org']}/storage-target")
            res.raise_for_status()
            target = res.json().get("target")
            if not target:
                console.print("[dim]No bucket registered. Set one with:[/dim]")
                console.print("[cyan]epi cloud storage set --url s3://bucket/prefix[/cyan]")
            else:
                console.print("[bold]Customer bucket[/bold]")
                for field in (
                    "kind",
                    "endpoint",
                    "bucket",
                    "region",
                    "prefix",
                    "object_lock",
                    "last_check_at",
                    "last_check_ok",
                ):
                    console.print(f"  {field}: {escape(str(target.get(field)))}")
                console.print("[dim]Object Lock is vendor-reported.[/dim]")
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Show failed: {escape(str(exc))}")
        raise typer.Exit(1) from exc
    pending = pending_uploads()
    console.print(f"[dim]Local outbox ({storage_outbox_path()}): {len(pending)} pending.[/dim]")


@storage_app.command("set")
def storage_set(
    url: str = typer.Argument(..., help="s3://bucket[/prefix]."),
    endpoint: str | None = typer.Option(None, "--endpoint", help="Custom endpoint (MinIO/R2/GCS)."),
    region: str | None = typer.Option(None, "--region", help="Region (default us-east-1)."),
    object_lock: str = typer.Option(
        "unknown", "--object-lock", help="on|off|unknown (self-attested)."
    ),
    org: str | None = typer.Option(None, "--org"),
    api_key: str | None = typer.Option(None, "--api-key"),
    cloud_url: str | None = typer.Option(None, "--url"),
) -> None:
    """Register the customer-owned bucket (no credentials leave this machine)."""
    from epi_core.storage_sink import parse_storage_url

    if object_lock not in ("on", "off", "unknown"):
        console.print("[red][FAIL][/red] --object-lock must be on|off|unknown.")
        raise typer.Exit(2)
    try:
        target = parse_storage_url(url, region=region, endpoint=endpoint)
    except ValueError as exc:
        console.print(f"[red][FAIL][/red] {escape(str(exc))}")
        raise typer.Exit(2) from exc
    creds = resolve_creds(cloud_url, org, api_key)
    try:
        with _client(creds) as client:
            res = client.put(
                f"/v1/orgs/{creds['org']}/storage-target",
                json={
                    "kind": "r2" if "r2.cloudflarestorage.com" in target.endpoint else "s3",
                    "endpoint": target.endpoint,
                    "bucket": target.bucket,
                    "region": target.region,
                    "prefix": target.prefix or None,
                    "object_lock": object_lock,
                },
            )
            res.raise_for_status()
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Set failed: {escape(str(exc))}")
        raise typer.Exit(1) from exc
    console.print(f"[green][OK][/green] Bucket registered: {target.bucket} ({target.endpoint}).")
    console.print("[dim]Credentials stay in your environment; EPI Cloud never sees them.[/dim]")


@storage_app.command("test")
def storage_test() -> None:
    """Probe write access: PUTs and re-reads one tiny object (fixed key)."""
    import hashlib
    import os

    from epi_core.storage_sink import load_credentials, parse_storage_url, put_object

    raw_url = os.getenv("EPI_STORAGE_URL", "")
    if not raw_url:
        console.print("[red][FAIL][/red] EPI_STORAGE_URL is not set.")
        raise typer.Exit(2)
    try:
        target = parse_storage_url(raw_url)
        creds = load_credentials()
        probe = b"epi-cloud-storage-probe"
        key = "epi-cloud-probe.txt"
        put_object(probe, key, target, creds)
        digest = hashlib.sha256(probe).hexdigest()
        console.print(f"[green][OK][/green] Wrote probe object {key} (sha256 {digest[:16]}...).")
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Probe failed: {escape(str(exc))}")
        raise typer.Exit(1) from exc


@storage_app.command("flush")
def storage_flush() -> None:
    """Retry every queued customer-bucket upload."""
    from epi_core.storage_sink import flush_storage_outbox, pending_uploads

    if not pending_uploads():
        console.print("[dim]Nothing pending — every file reached the customer bucket.[/dim]")
        return
    result = flush_storage_outbox()
    console.print(f"[dim]Delivered {result['delivered']}, failed {result['failed']}.[/dim]")
    if result["failed"]:
        console.print("[dim]Fix the bucket/credentials/network and flush again.[/dim]")
        raise typer.Exit(1)
