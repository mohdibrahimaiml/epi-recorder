"""CLI commands for EPI cloud identity: login, logout, whoami.

Authentication is strictly optional. Core local workflows never require it.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import typer
from rich.console import Console

from epi_core.telemetry import telemetry_url

app = typer.Typer(help="EPI cloud identity (optional).")
console = Console()


def _state_dir() -> Path:
    override = os.getenv("EPI_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".epi"


def _auth_path() -> Path:
    return _state_dir() / "auth.json"


def _base_portal_url() -> str:
    return telemetry_url().replace("/api/telemetry/events", "")


def save_auth(
    token: str,
    user_id: str,
    org: str | None = None,
    *,
    local: bool = False,
) -> None:
    path = _auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "token": token,
                "user_id": user_id,
                "org": org or "",
                "local": bool(local),
                "saved_at": _utc_now_iso(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def load_auth() -> dict[str, Any] | None:
    path = _auth_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("token") and data.get("user_id"):
            return data
    except Exception:
        pass
    return None


def clear_auth() -> None:
    path = _auth_path()
    if path.exists():
        path.unlink()


def _utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _CallbackHandler(BaseHTTPRequestHandler):
    result: dict[str, Any] | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = dict(pair.split("=", 1) for pair in parsed.query.split("&") if "=" in pair)
        _CallbackHandler.result = {
            "token": params.get("token"),
            "user_id": params.get("user_id"),
            "org": params.get("org", ""),
        }
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"""<!DOCTYPE html>
<html><head><title>EPI Login</title></head>
<body style="font-family: system-ui; text-align: center; padding-top: 4rem;">
  <h1>EPI login complete</h1>
  <p>You can close this tab and return to the terminal.</p>
</body></html>"""
        )

    def log_message(self, format, *args):
        pass


def _start_local_server(port: int) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _open_login_url(port: int, state: str) -> None:
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    params = {"state": state, "redirect_uri": redirect_uri}
    url = f"{_base_portal_url()}/api/auth/github/start?{urlencode(params)}"
    console.print(f"[dim]Opening browser to:[/dim] {url}")
    try:
        webbrowser.open(url)
    except Exception:
        console.print("[yellow]Could not open browser automatically.[/yellow]")
        console.print(f"[cyan]Please open this URL:[/cyan] {url}")


@app.command("login")
def login(
    local: bool = typer.Option(
        False,
        "--local",
        help="Create a local-only development session without contacting EPI Cloud.",
    ),
) -> None:
    """Log in (single account system: EPI Cloud).

    This is an alias of `epi cloud login` (browser device flow, push-only
    key). The old Render login is retired.
    """
    if local:
        token = "dev-" + secrets.token_urlsafe(32)
        save_auth(token, "local-dev", "local", local=True)
        console.print("[green][OK][/green] Local development session created")
        console.print("[dim]User ID: local-dev[/dim]")
        console.print(
            "[yellow][!][/yellow] This session is local-only and cannot access EPI Cloud features."
        )
        return

    console.print("[dim]epi auth login is now epi cloud login (one account system).[/dim]")
    import os as _os

    from epi_cli.cloud import _device_login

    base = (_os.getenv("EPI_CLOUD_URL") or "https://cloud.epilabs.org").rstrip("/")
    _device_login(base)


@app.command("logout")
def logout() -> None:
    """Log out locally (clears old session and EPI Cloud key)."""
    clear_auth()
    try:
        from epi_cli.cloud import _config_path as _cloud_path

        p = _cloud_path()
        if p.exists():
            p.unlink()
    except Exception:
        pass
    console.print("[green][OK][/green] Logged out")


@app.command("whoami")
def whoami() -> None:
    """Show login status (single account system: EPI Cloud)."""
    # New system first: ~/.epi/cloud.json from `epi cloud login`.
    try:
        from epi_cli.cloud import load_config as _load_cloud

        cfg = _load_cloud()
        if cfg.get("org_id") and cfg.get("api_key"):
            console.print("[bold]Logged in (EPI Cloud)[/bold]")
            console.print(f"  URL: {cfg.get('url')}")
            console.print(f"  Org: {cfg.get('org_id')}")
            console.print("[dim]Manage at https://cloud.epilabs.org/[/dim]")
            return
    except Exception:
        pass
    auth = load_auth()
    if not auth:
        console.print("[dim]Not logged in. Run [cyan]epi cloud login[/cyan] to connect.[/dim]")
        return
    if auth.get("local"):
        console.print("[bold]Local-only session[/bold] (no cloud access).")
        return
    console.print("[dim]Old Render login is retired. Run [cyan]epi cloud login[/cyan].[/dim]")
