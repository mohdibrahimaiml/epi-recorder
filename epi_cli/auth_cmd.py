"""CLI commands for EPI cloud identity: login, logout, whoami.

Authentication is strictly optional. Core local workflows never require it.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import typer
from http.server import BaseHTTPRequestHandler, HTTPServer
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


def save_auth(token: str, user_id: str, org: str | None = None) -> None:
    path = _auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"token": token, "user_id": user_id, "org": org or "", "saved_at": _utc_now_iso()},
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
def login() -> None:
    """Log in to EPI Cloud via GitHub OAuth."""
    port = _find_free_port()
    state = secrets.token_urlsafe(16)
    server = _start_local_server(port)
    _CallbackHandler.result = None

    console.print("[bold]EPI Cloud Login[/bold]")
    console.print("A browser window will open for GitHub authentication.")
    _open_login_url(port, state)

    try:
        for _ in range(600):  # wait up to 60 seconds
            if _CallbackHandler.result is not None:
                break
            import time
            time.sleep(0.1)
    finally:
        server.shutdown()

    result = _CallbackHandler.result
    if not result or not result.get("token") or not result.get("user_id"):
        console.print("[red][FAIL][/red] Login did not complete in time.")
        raise typer.Exit(1)

    save_auth(result["token"], result["user_id"], result.get("org"))
    console.print(f"[green][OK][/green] Logged in as {result['user_id']}")
    if result.get("org"):
        console.print(f"[dim]Organization: {result['org']}[/dim]")


@app.command("logout")
def logout() -> None:
    """Log out of EPI Cloud locally."""
    auth = load_auth()
    if auth and auth.get("token"):
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{_base_portal_url()}/api/auth/logout",
                data=b"",
                headers={"Authorization": f"Bearer {auth['token']}"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5.0)
        except Exception:
            pass
    clear_auth()
    console.print("[green][OK][/green] Logged out")


@app.command("whoami")
def whoami() -> None:
    """Show the currently logged-in EPI Cloud user."""
    auth = load_auth()
    if not auth:
        console.print("[dim]Not logged in. Run [cyan]epi login[/cyan] to connect.[/dim]")
        return

    try:
        import urllib.request
        req = urllib.request.Request(
            f"{_base_portal_url()}/api/auth/me",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        console.print("[bold]Logged in[/bold]")
        console.print(f"  User ID: {data.get('id')}")
        console.print(f"  GitHub:  {data.get('login') or 'unknown'}")
        console.print(f"  Email:   {data.get('email') or 'private'}")
        console.print(f"  Org:     {data.get('org') or 'not set'}")
    except Exception as exc:
        console.print(f"[yellow]Could not fetch profile:[/yellow] {exc}")
        console.print("[dim]Your local session may have expired. Run [cyan]epi login[/cyan].[/dim]")
