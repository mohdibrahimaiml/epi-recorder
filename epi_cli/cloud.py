"""`epi cloud` — push selected runs to your EPI Cloud workspace.

The open-source recorder, sealing, and verification stay free and offline.
This command only uploads runs the vendor *selects* (disputes, samples,
audit requests) to their EPI Cloud workspace; every run's full `.epi` belongs in
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

app = typer.Typer(help="EPI Cloud: connect this computer, push runs to your workspace, check status.")
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
                raise ValueError(f"{path} is larger than 25 MB; EPI Cloud does not accept files that big.")
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


def _server_message(res: Any) -> str:
    """The server's own error message, if it sent one."""
    try:
        body = res.json()
    except Exception:
        return ""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or "").strip()
        if isinstance(err, str):
            return err.strip()
    return ""


def http_problem(res: Any) -> str:
    """One plain line for a failed EPI Cloud response (never raw httpx/MDN text)."""
    code = getattr(res, "status_code", None)
    msg = _server_message(res)
    if code == 401:
        return msg or (
            "This computer's key was revoked or is no longer valid. "
            "Reconnect with: epi cloud login"
        )
    if code == 403:
        return "This computer's key isn't allowed to do that" + (f" ({msg})" if msg else ".")
    if code == 402:
        return msg or "Your plan's limit was reached. See your workspace to upgrade."
    if code == 410:
        return msg or "That customer was closed in the dashboard. Pick another with: epi cloud login"
    if code == 413:
        return msg or "The file is too large for EPI Cloud."
    return f"EPI Cloud said no (HTTP {code})" + (f": {msg}" if msg else ".")


def friendly_error(exc: Exception, base: str | None = None) -> str:
    """Plain line for any exception from an EPI Cloud call."""
    res = getattr(exc, "response", None)
    if res is not None and getattr(res, "status_code", None):
        return http_problem(res)
    try:
        import httpx

        if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError)):
            where = f" at {base}" if base else ""
            return f"Could not reach EPI Cloud{where}. Check your connection and try again."
    except Exception:
        pass
    text = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
    return text[:200]


def _save_config_fields(**fields: Any) -> None:
    """Merge a few fields into cloud.json quietly (no 'Saved' line)."""
    path = _config_path()
    if not path.exists():
        return
    data = load_config()
    data.update(fields)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def register_signing_key(creds: dict[str, str] | None = None) -> bool:
    """Register this computer's PUBLIC signing key with the workspace, once.

    Silent and best-effort: returns True only when it was newly registered
    (the caller prints one line then). Never raises; never creates a key.
    """
    try:
        cfg = load_config()
        if creds is None:
            url = (os.getenv("EPI_CLOUD_URL") or cfg.get("url") or "").rstrip("/")
            org = os.getenv("EPI_CLOUD_ORG") or cfg.get("org_id") or cfg.get("org") or ""
            key = os.getenv("EPI_CLOUD_API_KEY") or cfg.get("api_key") or cfg.get("key") or ""
            creds = {"url": url, "org": org, "key": key}
        if not (creds.get("url") and creds.get("org") and creds.get("key")):
            return False
        from epi_core.keys import KeyManager

        km = KeyManager()
        if not km.has_key("default"):
            return False
        public_key = km.load_public_key("default").hex()
        marker = f"{creds['org']}:{public_key}"
        if cfg.get("signing_key_registered") == marker:
            return False
        with _client(creds) as client:
            res = client.post(
                f"/v1/orgs/{creds['org']}/keys",
                json={"public_key": public_key, "label": (_device_name() or "computer")[:80]},
            )
        if res.status_code in (200, 201):
            _save_config_fields(signing_key_registered=marker)
            return True
        if res.status_code == 409:
            _save_config_fields(signing_key_registered=marker)
        return False
    except Exception:
        return False


def _send_waiting_witness_reports() -> int:
    """After a fresh login: send reports queued for this computer's witness URL."""
    try:
        from epi_core.webhook import flush_outbox, outbox_path, read_outbox, split_witness_urls

        preset = saved_customer()
        urls = set(split_witness_urls(preset.get("witness_url")))
        secret = preset.get("witness_secret")
        if not urls or not secret:
            return 0
        if not any(set(e.get("pending") or []) & urls for e in read_outbox(outbox_path())):
            return 0
        result = flush_outbox(
            timeout_seconds=5,
            path=outbox_path(),
            secret_for_url=lambda u: secret if str(u) in urls else None,
        )
        return len([u for u in result.get("delivered") or [] if u in urls])
    except Exception:
        return 0


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
    auto_push: bool | None = typer.Option(
        None,
        "--auto-push/--no-auto-push",
        help="Auto-push every sealed run after recording (default off).",
    ),
) -> None:
    """Connect this computer to your EPI Cloud workspace (saved for push and status).

    No flags: browser device flow — this terminal shows a short code,
    you type it at cloud.epilabs.org/auth/device with the customer this
    computer records for, and the CLI receives a push-only key plus the
    witness settings automatically. With --org/--api-key: automation
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
        _save_flag_login(base, org, key, auto_push)
        return
    if api_key:
        console.print("[red][FAIL][/red] --api-key needs --org.")
        console.print("[dim]Or run [cyan]epi cloud login[/cyan] with no flags.[/dim]")
        raise typer.Exit(2)
    _device_login(base, auto_push)


def _save_flag_login(base: str, org: str, api_key: str, auto_push: bool | None = None) -> None:
    creds = {"url": base, "org": org, "key": api_key}
    rejected = "[red][FAIL][/red] The key was rejected (check the workspace id and key)."
    try:
        with _client(creds) as client:
            # whoami works for any valid key (push-only included).
            res = client.get(f"/v1/orgs/{org}/whoami")
            if res.status_code == 404:
                # Older server without whoami: a push-only key can't list
                # runs (403) but is still a valid key for this workspace.
                res = client.get(f"/v1/orgs/{org}/artifacts")
                if res.status_code == 403:
                    res = None
        if res is not None:
            if res.status_code in (401, 403):
                console.print(rejected)
                raise typer.Exit(1)
            res.raise_for_status()
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red][FAIL][/red] {escape(friendly_error(exc, base))}")
        raise typer.Exit(1) from exc
    _write_config(base, org, api_key)


def _write_config(base: str, org: str, api_key: str, extra: dict | None = None) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {"url": base, "org_id": org, "api_key": api_key}
    for key in ("witness_url", "witness_secret", "customer", "auto_push", "org_name"):
        if extra and extra.get(key) not in (None, ""):
            data[key] = extra[key]
        elif key == "auto_push" and extra and "auto_push" in extra and isinstance(extra["auto_push"], bool):
            data[key] = extra[key]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    console.print(f"[green][OK][/green] Saved to {path} (mode 0600 where supported).")


def saved_customer() -> dict:
    """Saved customer preset from login/use (url/secret never printed)."""
    try:
        cfg = load_config()
    except Exception:
        return {}
    out: dict = {}
    if isinstance(cfg.get("customer"), str) and cfg["customer"].strip():
        out["customer"] = cfg["customer"].strip()
    if isinstance(cfg.get("witness_url"), str) and cfg["witness_url"].strip():
        out["witness_url"] = cfg["witness_url"].strip()
    if cfg.get("witness_secret"):
        out["witness_secret"] = cfg["witness_secret"]
    if isinstance(cfg.get("auto_push"), bool):
        out["auto_push"] = cfg["auto_push"]
    return out


def _version_tuple(version: str) -> tuple:
    """Numeric tuple compare for dotted versions (stdlib only)."""
    parts: list = []
    for piece in str(version or "").split("."):
        num = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _warn_if_cli_outdated(min_cli_version: str | None) -> None:
    """Loud, friendly nudge when the cloud needs a newer CLI than this one."""
    if not min_cli_version:
        return
    try:
        from epi_core import __version__ as current
    except Exception:
        return
    try:
        if _version_tuple(current) < _version_tuple(min_cli_version):
            console.print(
                f"[yellow][WARN][/yellow] This cloud needs epi-recorder >= {min_cli_version} "
                f"(you have {current}). Run: [cyan]pip install -U epi-recorder[/cyan]"
            )
    except Exception:
        pass


def _check_server_version(client) -> None:
    """Warn when the cloud advertises a newer minimum CLI (non-fatal)."""
    try:
        res = client.get("/v1/version")
        if res.status_code != 200:
            return
        try:
            body = res.json()
        except Exception:
            return
        if isinstance(body, dict):
            _warn_if_cli_outdated(body.get("min_cli_version"))
    except Exception:
        pass


def _device_name() -> str | None:
    """Short name for this computer (shown in the dashboard's Computers tab)."""
    try:
        import platform

        name = (platform.node() or "").strip()[:64]
        return name or None
    except Exception:
        return None


def _device_login(base: str, auto_push: bool | None = None) -> None:
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
    start_body: dict[str, Any] = {"device_name": _device_name()}
    try:
        _prev = load_config()
        _prev_key = str(_prev.get("api_key") or _prev.get("key") or "")
        if _prev_key and str(_prev.get("url") or "").rstrip("/") == base:
            # Sending the full old key proves this computer owns it; the
            # server (which stores only its hash) revokes it once the new
            # one is authorized in the same workspace. Only ever sent to the
            # same configured URL it was issued by; never printed.
            start_body["replaces_key"] = _prev_key
    except Exception:
        pass
    try:
        with httpx.Client(base_url=base, timeout=30.0) as client:
            res = client.post("/auth/device/start", json=start_body)
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
    _warn_if_cli_outdated(data.get("min_cli_version"))
    console.print(f"Type the code and your customer's name at {verify_url}")
    console.print(f"[bold cyan]{escape(str(user_code))}[/bold cyan]")
    console.print("[dim]A browser window will open. The code works only for this computer.[/dim]")
    try:
        webbrowser.open(verify_url)
    except Exception:
        pass
    deadline = time.time() + 10 * 60
    started = time.time()
    hinted = False
    org_id = ""
    raw_key = ""
    witness_url: str | None = None
    witness_secret: str | None = None
    customer: str | None = None
    org_name: str | None = None
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
                        witness_url = str(body.get("witness_url") or "") or None
                        witness_secret = str(body.get("witness_secret") or "") or None
                        customer = str(body.get("customer_label") or "") or None
                        org_name = str(body.get("org_name") or "") or None
                        break
                    console.print("[red][FAIL][/red] Key already retrieved.")
                    console.print("[dim]Run login again for a new code.[/dim]")
                    raise typer.Exit(1)
                if body.get("status") == "expired":
                    console.print("[red][FAIL][/red] Code expired. Retry login.")
                    raise typer.Exit(1)
                # The browser may have shown an error (unknown code, plan
                # limit, closed customer) while this loop keeps polling a
                # row that will never authorize. Nudge once so the terminal
                # does not wait in silence for ten minutes.
                if not hinted and time.time() - started >= 30:
                    console.print("[dim]Still waiting for the browser — if it showed an error, fix it there and press Connect again.[/dim]")
                    hinted = True
                time.sleep(interval)
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Login polling failed: {escape(friendly_error(exc))}")
        raise typer.Exit(1) from exc
    if not raw_key or not org_id:
        console.print("[red][FAIL][/red] Login did not complete in time.")
        raise typer.Exit(1)
    previous = load_config()
    if auto_push is None:
        auto_push = bool(previous.get("auto_push", False))
    if not org_name:
        # Workspace name for the lines below and `epi cloud status` (best effort).
        try:
            with _client({"url": base, "org": org_id, "key": raw_key}) as client:
                who = client.get(f"/v1/orgs/{org_id}/whoami")
            if who.status_code == 200 and isinstance(who.json(), dict):
                org_name = str(who.json().get("org_name") or "") or None
        except Exception:
            org_name = None
    _write_config(base, org_id, raw_key, {"witness_url": witness_url, "witness_secret": witness_secret, "customer": customer, "auto_push": auto_push, "org_name": org_name})
    console.print("[green][OK][/green] This computer is connected to your EPI Cloud workspace.")
    console.print(f"[dim]Workspace: {escape(org_name or org_id)} — disconnect it anytime at {escape(base)}.[/dim]")
    if customer:
        console.print(f"[green][OK][/green] Recording for [bold]{escape(customer)}[/bold] — new runs are witnessed automatically, no secrets to copy.")
    else:
        console.print("[dim]Tip: run [cyan]epi cloud login[/cyan] again and type your customer's name on the Connect page.[/dim]")
    if auto_push:
        console.print("[dim]Auto-push is on: every sealed run will be pushed automatically.[/dim]")
    if register_signing_key({"url": base, "org": org_id, "key": raw_key}):
        console.print("[green][OK][/green] Signing key registered with your workspace.")
    sent = _send_waiting_witness_reports()
    if sent:
        console.print(f"[green][OK][/green] Sent {sent} waiting witness report(s).")


@app.command("use")
def use(
    customer: str = typer.Argument(..., help='Customer name, e.g. epi cloud use "Acme Bank".'),
) -> None:
    """Set the customer this computer records for (saved to ~/.epi/cloud.json)."""
    name = customer.strip()
    if not name:
        console.print("[red][FAIL][/red] Customer name is required.")
        raise typer.Exit(2)
    cfg = load_config()
    if not cfg.get("url") or not (cfg.get("org_id") or cfg.get("org")):
        console.print("[red][FAIL][/red] Not logged in. Run [cyan]epi cloud login[/cyan] first.")
        raise typer.Exit(2)
    base = str(cfg.get("url") or "").rstrip("/")
    org = str(cfg.get("org_id") or cfg.get("org") or "")
    key = str(cfg.get("api_key") or cfg.get("key") or "")
    current = str(cfg.get("customer") or "").strip()
    if current and current.casefold() == name.casefold():
        console.print(f"[green][OK][/green] This computer already records for {escape(current)}.")
        return
    switch_hint = (
        "To switch this computer to another customer, run: epi cloud login — "
        "and type the customer's name on the Connect page."
    )
    # Push keys never get witness secrets here (least privilege); the server
    # refuses them, so switching customers goes through the authorize page.
    try:
        creds = resolve_creds(base, org, key)
        with _client(creds) as client:
            res = client.post(
                f"/v1/orgs/{creds['org']}/inboxes/by-customer",
                json={"customer_label": name},
            )
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red][FAIL][/red] {escape(friendly_error(exc, base))}")
        raise typer.Exit(1) from exc
    if res.status_code == 403 and key.startswith("epik_"):
        if current:
            console.print(f"[yellow][!][/yellow] This computer records for {escape(current)}.")
        _plain(switch_hint)
        raise typer.Exit(1)
    if res.status_code == 404:
        msg = _server_message(res)
        console.print(f"[yellow][!][/yellow] No customer called '{escape(name)}' in this workspace.")
        if msg:
            console.print(f"[dim]{escape(msg)}[/dim]")
        _plain(f"See your customers at {base}. {switch_hint}")
        raise typer.Exit(1)
    if not 200 <= res.status_code < 300:
        console.print(f"[red][FAIL][/red] {escape(http_problem(res))}")
        _plain(switch_hint)
        raise typer.Exit(1)
    try:
        body = res.json()
    except Exception:
        body = {}
    extra: dict = {"customer": name}
    if body.get("url"):
        extra["witness_url"] = body["url"]
    if body.get("secret"):
        extra["witness_secret"] = body["secret"]
    for k in ("auto_push", "org_name"):
        if cfg.get(k) not in (None, ""):
            extra[k] = cfg[k]
    _write_config(base, org, key, extra)
    if body.get("secret"):
        console.print(f"[green][OK][/green] This computer now records for {escape(name)} (witness set up).")
    else:
        console.print(f"[green][OK][/green] This computer now records for {escape(name)}.")
        console.print("[dim]Witness not set up for this customer yet: run epi cloud login and type its name on the Connect page.[/dim]")


def _plain(text: str) -> None:
    console.print(text, markup=False, highlight=False, soft_wrap=True)


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
    """Upload one sealed .epi file to your EPI Cloud workspace (checks it, then sends it)."""
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
    effective_agent = agent or load_config().get("customer")
    try:
        with _client(creds) as client:
            _check_server_version(client)
            init = client.post(
                f"/v1/orgs/{creds['org']}/artifacts/init",
                json={
                    "manifest_json": manifest_json,
                    "claimed_sha256": digest,
                    "claimed_crc32": crc,
                    "size_bytes": size,
                    "agent": effective_agent,
                    "reason": reason,
                },
            )
            if init.status_code == 400:
                msg = _server_message(init) or init.text[:300]
                console.print(f"[red][FAIL][/red] Rejected: {escape(msg)}")
                raise typer.Exit(1)
            if init.status_code >= 400:
                console.print(f"[red][FAIL][/red] {escape(http_problem(init))}")
                raise typer.Exit(1)
            created = init.json()
            if created.get("deduped"):
                console.print(f"[green][OK][/green] Already in your EPI Cloud workspace: {created['id']}")
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
            if put.status_code >= 400:
                console.print(f"[red][FAIL][/red] {escape(http_problem(put))}")
                raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Push failed: {escape(friendly_error(exc, creds['url']))}")
        raise typer.Exit(1) from exc
    console.print(f"[green][OK][/green] Pushed {file.name} as {created['id']}")
    console.print(
        f"[dim]Seal: {created.get('signature_check')} · "
        f"Witness: {created.get('witness_status')}[/dim]"
    )


def _waiting_witness_reports() -> int:
    try:
        from epi_core.webhook import outbox_path, read_outbox

        return sum(1 for e in read_outbox(outbox_path()) if e.get("pending"))
    except Exception:
        return 0


def _print_this_computer(creds: dict[str, str], who: dict | None = None) -> None:
    """What this computer is set to (works for push-only keys)."""
    cfg = load_config()
    who = who or {}
    workspace = str(who.get("org_name") or who.get("name") or cfg.get("org_name") or "").strip()
    org_id = creds.get("org") or ""
    customer = str(cfg.get("customer") or who.get("customer_label") or "").strip()
    witness = bool(str(cfg.get("witness_url") or "").strip() and cfg.get("witness_secret")) or bool(
        os.getenv("EPI_WITNESS_URL")
    )
    waiting = _waiting_witness_reports()
    rows = [
        ("Workspace", f"{workspace} ({org_id})" if workspace else org_id),
        ("Customer", customer or "none yet — run epi cloud login"),
        ("Cloud", creds.get("url") or ""),
        ("Auto-push", "on" if cfg.get("auto_push") is True else "off"),
        ("Witness", "set up" if witness else "not set up — run epi cloud login"),
        ("Witness reports waiting", str(waiting) + (" (details: epi witness status)" if waiting else "")),
    ]
    console.print("[bold]This computer[/bold]")
    for label, value in rows:
        console.print(f"  {label + ':':<25}{escape(value)}")


@app.command("status")
def status(
    artifact_id: str | None = typer.Argument(None, help="Run id (default: list runs)."),
    url: str | None = typer.Option(None, "--url"),
    org: str | None = typer.Option(None, "--org"),
    api_key: str | None = typer.Option(None, "--api-key"),
) -> None:
    """Show what this computer is set to, and the runs in your workspace (when the key may list them)."""
    creds = resolve_creds(url, org, api_key)
    try:
        with _client(creds) as client:
            _check_server_version(client)
            if artifact_id:
                res = client.get(f"/v1/orgs/{creds['org']}/artifacts/{artifact_id}")
                if res.status_code >= 400:
                    console.print(f"[red][FAIL][/red] {escape(http_problem(res))}")
                    raise typer.Exit(1)
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
                return
            who: dict = {}
            try:
                w = client.get(f"/v1/orgs/{creds['org']}/whoami")
                if w.status_code == 200 and isinstance(w.json(), dict):
                    who = w.json()
                elif w.status_code == 401:
                    console.print(f"[red][FAIL][/red] {escape(http_problem(w))}")
                    raise typer.Exit(1)
            except typer.Exit:
                raise
            except Exception:
                who = {}
            _print_this_computer(creds, who)
            res = client.get(f"/v1/orgs/{creds['org']}/artifacts")
            if res.status_code == 403:
                # Push-only key (normal for a connected computer): it can't
                # list runs, and that's fine.
                console.print(f"[dim]See this workspace's runs at {escape(creds['url'])}.[/dim]")
                return
            if res.status_code >= 400:
                console.print(f"[red][FAIL][/red] {escape(http_problem(res))}")
                raise typer.Exit(1)
            rows = res.json().get("artifacts", [])
            if not rows:
                console.print("[dim]No runs in your EPI Cloud workspace yet.[/dim]")
                return
            cols = ("id", "goal", "signature_check", "witness_status", "reason")
            table = Table(title="Runs in your EPI Cloud workspace")
            for col in cols:
                table.add_column(col, overflow="fold")
            for row in rows:
                table.add_row(*[str(row.get(col, ""))[:40] for col in cols])
            console.print(table)
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Status failed: {escape(friendly_error(exc, creds['url']))}")
        raise typer.Exit(1) from exc


def _is_forbidden(exc: Exception) -> bool:
    """True when an HTTP client rejected the call with 403 (e.g. a push-only key listing runs)."""
    return getattr(getattr(exc, "response", None), "status_code", None) == 403


storage_app = typer.Typer(help="Customer-owned bucket: target, probe, outbox.")
app.add_typer(storage_app, name="storage")

keys_app = typer.Typer(help="Vendor public keys: register, list, revoke (public only).")
app.add_typer(keys_app, name="keys")


def _read_pubkey_file(path: Path) -> str:
    """Read a public key file. Only *.pub, only 64 hex chars.

    Refuses everything else: private keys, PEM blocks, junk. Registering
    the wrong material would mislabel the trust page, so this fails closed.
    """
    if path.suffix.lower() != ".pub":
        raise ValueError(f"Refusing {path}: only *.pub public-key files (never private keys).")
    try:
        text = path.read_text(encoding="utf-8").strip().lower()
    except Exception as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc
    import re as _re

    if not _re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError(
            f"Refusing {path}: not 64 hex chars of Ed25519 public key "
            "(export one with: epi keys export --format hex)."
        )
    return text


@keys_app.command("push")
def keys_push(
    pub: Path = typer.Argument(..., help="Public key file (*.pub only)."),
    label: str | None = typer.Option(None, "--label", help="Human label, e.g. prod-2026."),
    url: str | None = typer.Option(None, "--url"),
    org: str | None = typer.Option(None, "--org"),
    api_key: str | None = typer.Option(None, "--api-key"),
) -> None:
    """Register a vendor PUBLIC key (rotation = push the new one, revoke the old)."""
    try:
        public_key = _read_pubkey_file(pub)
    except ValueError as exc:
        console.print(f"[red][FAIL][/red] {escape(str(exc))}")
        raise typer.Exit(2) from exc
    creds = resolve_creds(url, org, api_key)
    try:
        with _client(creds) as client:
            res = client.post(
                f"/v1/orgs/{creds['org']}/keys", json={"public_key": public_key, "label": label}
            )
            if res.status_code == 409:
                console.print("[yellow]Already registered.[/yellow]")
                return
            res.raise_for_status()
            created = res.json()
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Register failed: {escape(friendly_error(exc))}")
        raise typer.Exit(1) from exc
    console.print("[green][OK][/green] Registered key " f"{created.get('fingerprint')}.")
    console.print("[dim]registration is informational only — reviewers pin keys out of band.[/dim]")


@keys_app.command("list")
def keys_list(
    url: str | None = typer.Option(None, "--url"),
    org: str | None = typer.Option(None, "--org"),
    api_key: str | None = typer.Option(None, "--api-key"),
) -> None:
    """List registered public keys with revocation state."""
    creds = resolve_creds(url, org, api_key)
    try:
        with _client(creds) as client:
            res = client.get(f"/v1/orgs/{creds['org']}/keys")
            res.raise_for_status()
            rows = res.json().get("keys", [])
            if not rows:
                console.print("[dim]No keys registered.[/dim]")
                return
            table = Table(title="Registered public keys (informational — not pins)")
            for col in ("fingerprint", "label", "valid_from", "revoked_at", "revoke_reason"):
                table.add_column(col, overflow="fold")
            for row in rows:
                table.add_row(*[str(row.get(col, "") or "")[:40] for col in
                                ("fingerprint", "label", "valid_from", "revoked_at", "revoke_reason")])
            console.print(table)
    except Exception as exc:
        console.print(f"[red][FAIL][/red] List failed: {escape(friendly_error(exc))}")
        raise typer.Exit(1) from exc


@keys_app.command("revoke")
def keys_revoke(
    fingerprint: str = typer.Argument(..., help="Key fingerprint (spaces optional)."),
    reason: str | None = typer.Option(None, "--reason", help="Why it was revoked."),
    url: str | None = typer.Option(None, "--url"),
    org: str | None = typer.Option(None, "--org"),
    api_key: str | None = typer.Option(None, "--api-key"),
) -> None:
    """Revoke a registered public key (history is kept, marked revoked)."""
    creds = resolve_creds(url, org, api_key)
    want = "".join(fingerprint.split()).lower()
    try:
        with _client(creds) as client:
            res = client.get(f"/v1/orgs/{creds['org']}/keys")
            res.raise_for_status()
            match = next(
                (k for k in res.json().get("keys", [])
                 if str(k.get("fingerprint", "")).lower() == want and not k.get("revoked_at")),
                None,
            )
            if not match:
                console.print("[red][FAIL][/red] No active registered key with that fingerprint.")
                raise typer.Exit(1)
            revoke = client.post(
                f"/v1/orgs/{creds['org']}/keys/{match['id']}/revoke", json={"reason": reason}
            )
            revoke.raise_for_status()
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Revoke failed: {escape(friendly_error(exc))}")
        raise typer.Exit(1) from exc
    console.print(f"[green][OK][/green] Revoked {want}. History is kept and marked revoked.")


@keys_app.command("unrevoke")
def keys_unrevoke(
    fingerprint: str = typer.Argument(..., help="Key fingerprint (spaces optional)."),
    url: str | None = typer.Option(None, "--url"),
    org: str | None = typer.Option(None, "--org"),
    api_key: str | None = typer.Option(None, "--api-key"),
) -> None:
    """Restore a mistakenly revoked key (clears the revocation mark)."""
    creds = resolve_creds(url, org, api_key)
    want = "".join(fingerprint.split()).lower()
    try:
        with _client(creds) as client:
            res = client.get(f"/v1/orgs/{creds['org']}/keys")
            res.raise_for_status()
            match = next(
                (k for k in res.json().get("keys", [])
                 if str(k.get("fingerprint", "")).lower() == want and k.get("revoked_at")),
                None,
            )
            if not match:
                console.print("[red][FAIL][/red] No revoked registered key with that fingerprint.")
                raise typer.Exit(1)
            restore = client.post(
                f"/v1/orgs/{creds['org']}/keys/{match['id']}/unrevoke"
            )
            restore.raise_for_status()
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Unrevoke failed: {escape(friendly_error(exc))}")
        raise typer.Exit(1) from exc
    console.print(f"[green][OK][/green] Restored {want}.")


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
        console.print(f"[red][FAIL][/red] Show failed: {escape(friendly_error(exc))}")
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
        console.print(f"[red][FAIL][/red] Set failed: {escape(friendly_error(exc))}")
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
        console.print(f"[red][FAIL][/red] Probe failed: {escape(friendly_error(exc))}")
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
