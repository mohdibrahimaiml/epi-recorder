"""
epi connect - local launcher for the shared Decision Ops workspace.

This command starts the real local EPI gateway plus the browser app so teams
can fetch source records, review shared cases, and export portable proof
without managing the backend pieces manually.
"""

from __future__ import annotations

import asyncio
import base64
import csv
import json
import os
import socket
import threading
import time
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

import typer
from rich.console import Console

from epi_core import __version__

app = typer.Typer(help="Launch the local Decision Ops app and shared EPI gateway.")
console = Console()

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_WEB_PORT = 8000
REPO_ROOT = Path(__file__).resolve().parents[1]
VIEWER_PATH = "/web_viewer/index.html"
DEFAULT_STORAGE_DIR = REPO_ROOT / ".epi-shared-workspace"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "sample", "mock"}


def _required(mapping: dict[str, Any], *keys: str) -> list[str]:
    missing = [key for key in keys if not _clean(mapping.get(key))]
    if missing:
        raise ValueError(f"Missing required connector field(s): {', '.join(missing)}")
    return [_clean(mapping.get(key)) for key in keys]


def _http_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    basic_auth: tuple[str, str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    final_headers = {"Accept": "application/json"}
    if headers:
        final_headers.update(headers)

    if basic_auth is not None:
        username, password = basic_auth
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        final_headers["Authorization"] = f"Basic {token}"

    request = urlrequest.Request(url, headers=final_headers, method="GET")
    try:
        with urlrequest.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{exc.code} {exc.reason}: {detail}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Received non-JSON response from {url}") from exc


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _mock_zendesk_record(case_input: dict[str, Any]) -> dict[str, Any]:
    ticket_id = _clean(case_input.get("ticket_id") or case_input.get("case_id") or "12345")
    return {
        "status": "loaded",
        "ticket_id": ticket_id,
        "subject": "High-value refund request needs approval",
        "priority": "high",
        "raw_status": "open",
        "source_system": "Zendesk",
        "decision_state": "pending_review",
    }


def _mock_salesforce_record(case_input: dict[str, Any]) -> dict[str, Any]:
    record_id = _clean(case_input.get("record_id") or case_input.get("case_id") or "500000000000001")
    return {
        "status": "loaded",
        "record_id": record_id,
        "object_name": _clean(case_input.get("object_name") or "Case"),
        "subject": "Policy exception requires approval",
        "priority": "High",
        "owner_id": "005000000000001",
        "source_system": "Salesforce",
        "decision_state": "pending_review",
    }


def _mock_servicenow_record(case_input: dict[str, Any]) -> dict[str, Any]:
    sys_id = _clean(case_input.get("sys_id") or case_input.get("case_id") or "46d44b40db7f2010a8d75f48dc9619f4")
    return {
        "status": "loaded",
        "sys_id": sys_id,
        "table": _clean(case_input.get("table") or "incident"),
        "number": "INC0012456",
        "short_description": "Access request requires manual verification",
        "assignment_group": "Security operations",
        "source_system": "ServiceNow",
        "decision_state": "pending_review",
    }


def _mock_internal_app_record(case_input: dict[str, Any]) -> dict[str, Any]:
    record_id = _clean(case_input.get("record_id") or case_input.get("case_id") or "approval-123")
    return {
        "status": "loaded",
        "record_id": record_id,
        "decision_state": "awaiting_human_review",
        "summary": "Internal approval request exceeds the automatic threshold",
        "source_system": "Internal app",
    }


def _mock_csv_export_record(case_input: dict[str, Any]) -> dict[str, Any]:
    case_id = _clean(case_input.get("case_id") or "refund-001")
    return {
        "status": "loaded",
        "case_id": case_id,
        "summary": "Imported CSV row needs review before it moves forward",
        "decision_state": "pending_review",
        "source_system": "CSV export",
    }


def build_mock_record(system: str, case_input: dict[str, Any], *, reason: str | None = None, mode: str = "mock") -> dict[str, Any]:
    system_name = _clean(system).lower()
    builders = {
        "zendesk": _mock_zendesk_record,
        "salesforce": _mock_salesforce_record,
        "servicenow": _mock_servicenow_record,
        "internal-app": _mock_internal_app_record,
        "csv-export": _mock_csv_export_record,
    }
    if system_name not in builders:
        raise ValueError(f"Unsupported connector system: {system}")

    record = builders[system_name](case_input or {})
    record["bridge_mode"] = mode
    record["is_mock"] = True
    if reason:
        record["bridge_warning"] = reason
    return record


def _fetch_zendesk(connector_profile: dict[str, Any], case_input: dict[str, Any]) -> dict[str, Any]:
    subdomain, email, api_token = _required(connector_profile, "subdomain", "email", "api_token")
    ticket_id = _clean(case_input.get("ticket_id") or case_input.get("case_id"))
    if not ticket_id:
        raise ValueError("sample_input.json must include ticket_id or case_id for Zendesk")

    payload = _http_json(
        f"https://{subdomain}.zendesk.com/api/v2/tickets/{ticket_id}.json",
        basic_auth=(f"{email}/token", api_token),
    )
    ticket = payload.get("ticket") or {}
    return {
        "status": "loaded",
        "ticket_id": ticket.get("id"),
        "subject": ticket.get("subject"),
        "priority": ticket.get("priority"),
        "raw_status": ticket.get("status"),
        "source_system": "Zendesk",
    }


def _fetch_salesforce(connector_profile: dict[str, Any], case_input: dict[str, Any]) -> dict[str, Any]:
    instance_url, access_token = _required(connector_profile, "instance_url", "access_token")
    api_version = _clean(connector_profile.get("api_version") or "v61.0")
    record_id = _clean(case_input.get("record_id") or case_input.get("case_id"))
    object_name = _clean(case_input.get("object_name") or "Case")
    if not record_id:
        raise ValueError("sample_input.json must include record_id or case_id for Salesforce")

    payload = _http_json(
        f"{instance_url.rstrip('/')}/services/data/{api_version}/sobjects/{object_name}/{record_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    return {
        "status": "loaded",
        "record_id": payload.get("Id"),
        "object_name": object_name,
        "subject": payload.get("Subject") or payload.get("Name"),
        "priority": payload.get("Priority"),
        "owner_id": payload.get("OwnerId"),
        "source_system": "Salesforce",
    }


def _fetch_servicenow(connector_profile: dict[str, Any], case_input: dict[str, Any]) -> dict[str, Any]:
    instance_url, username, password = _required(connector_profile, "instance_url", "username", "password")
    table = _clean(case_input.get("table") or "incident")
    sys_id = _clean(case_input.get("sys_id") or case_input.get("case_id"))
    if not sys_id:
        raise ValueError("sample_input.json must include sys_id or case_id for ServiceNow")

    payload = _http_json(
        f"{instance_url.rstrip('/')}/api/now/table/{table}/{sys_id}",
        basic_auth=(username, password),
    )
    record = payload.get("result") or {}
    return {
        "status": "loaded",
        "sys_id": record.get("sys_id"),
        "table": table,
        "number": record.get("number"),
        "short_description": record.get("short_description"),
        "assignment_group": record.get("assignment_group"),
        "source_system": "ServiceNow",
    }


def _fetch_internal_app(connector_profile: dict[str, Any], case_input: dict[str, Any]) -> dict[str, Any]:
    (base_url,) = _required(connector_profile, "base_url")
    bearer_token = _clean(connector_profile.get("bearer_token"))
    api_path = _clean(case_input.get("api_path") or connector_profile.get("api_path") or "/api/v1/records")
    record_id = _clean(case_input.get("record_id") or case_input.get("case_id"))
    if not record_id:
        raise ValueError("sample_input.json must include record_id or case_id for the internal app connector")

    headers = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    payload = _http_json(
        f"{base_url.rstrip('/')}{api_path.rstrip('/')}/{record_id}",
        headers=headers,
    )
    return {
        "status": "loaded",
        "record_id": payload.get("id") or payload.get("record_id"),
        "decision_state": payload.get("status") or payload.get("decision_state"),
        "summary": payload.get("summary") or payload.get("title"),
        "source_system": "Internal app",
    }


def _fetch_csv_export(connector_profile: dict[str, Any], case_input: dict[str, Any]) -> dict[str, Any]:
    csv_path = Path(_clean(case_input.get("csv_path") or connector_profile.get("csv_path") or "source_export.csv"))
    id_column = _clean(case_input.get("id_column") or connector_profile.get("id_column") or "case_id")
    case_id = _clean(case_input.get("case_id"))
    if not case_id:
        raise ValueError("sample_input.json must include case_id for CSV imports")
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if _clean(row.get(id_column)) == case_id:
                return {
                    "status": "loaded",
                    "case_id": row.get("case_id") or row.get("id"),
                    "summary": row.get("summary") or row.get("title"),
                    "decision_state": row.get("status") or row.get("decision_state"),
                    "source_system": "CSV export",
                }

    raise ValueError(f"No row found for {case_id!r} using column {id_column!r}")


def fetch_live_record(system: str, connector_profile: dict[str, Any], case_input: dict[str, Any]) -> dict[str, Any]:
    system_name = _clean(system).lower()
    handlers = {
        "zendesk": _fetch_zendesk,
        "salesforce": _fetch_salesforce,
        "servicenow": _fetch_servicenow,
        "internal-app": _fetch_internal_app,
        "csv-export": _fetch_csv_export,
    }
    if system_name not in handlers:
        raise ValueError(f"Unsupported connector system: {system}")

    connector_profile = connector_profile or {}
    case_input = case_input or {}
    requested_preview_mode = _clean(case_input.get("preview_mode") or connector_profile.get("preview_mode")).lower()
    allow_mock_fallback = _truthy(case_input.get("allow_mock_fallback") or connector_profile.get("allow_mock_fallback"))

    if requested_preview_mode in {"mock", "sample", "safe-sample"}:
        record = build_mock_record(system_name, case_input, mode="mock")
    else:
        try:
            record = handlers[system_name](connector_profile, case_input)
            record["bridge_mode"] = "live"
            record["is_mock"] = False
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            if not allow_mock_fallback:
                raise
            record = build_mock_record(system_name, case_input, reason=str(exc), mode="mock-fallback")

    record["bridge_system"] = system_name
    return record


def _resolve_storage_dir(path: Path | None) -> Path:
    resolved = Path(path or DEFAULT_STORAGE_DIR)
    if resolved.suffix.lower() == ".json":
        resolved = resolved.parent
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


class ManagedGatewayServer:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        storage_dir: Path,
        batch_size: int = 50,
        batch_timeout: float = 2.0,
    ):
        self.host = host
        self.port = port
        self.storage_dir = _resolve_storage_dir(storage_dir)
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((host, port))
        self.socket.listen(2048)
        self.server_address = self.socket.getsockname()
        self._server = None

    def serve_forever(self) -> None:
        import uvicorn

        from epi_gateway.main import create_app
        from epi_gateway.worker import EvidenceWorker

        worker = EvidenceWorker(
            storage_dir=self.storage_dir,
            batch_size=self.batch_size,
            batch_timeout=self.batch_timeout,
        )
        config = uvicorn.Config(
            create_app(worker=worker),
            host=self.server_address[0],
            port=self.server_address[1],
            log_level="warning",
        )
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None
        self._server = server
        asyncio.run(server.serve(sockets=[self.socket]))

    def shutdown(self) -> None:
        if self._server is not None:
            self._server.should_exit = True

    def server_close(self) -> None:
        try:
            self.socket.close()
        except Exception:
            pass


def _default_workspace_state() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": None,
        "cases": {},
    }


def _resolve_workspace_file(path: Path | None) -> Path:
    resolved = Path(path or (DEFAULT_STORAGE_DIR / "workspace-state.json"))
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if not resolved.exists():
        resolved.write_text(json.dumps(_default_workspace_state(), indent=2), encoding="utf-8")
    return resolved


def _read_workspace_state(path: Path) -> dict[str, Any]:
    workspace_file = _resolve_workspace_file(path)
    try:
        payload = json.loads(workspace_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = _default_workspace_state()

    payload.setdefault("version", 1)
    payload.setdefault("updated_at", None)
    payload.setdefault("cases", {})
    if not isinstance(payload["cases"], dict):
        payload["cases"] = {}
    return payload


def _write_workspace_state(path: Path, state: dict[str, Any]) -> None:
    workspace_file = _resolve_workspace_file(path)
    workspace_file.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _list_workspace_cases(path: Path) -> list[dict[str, Any]]:
    state = _read_workspace_state(path)
    cases = list(state.get("cases", {}).values())
    return sorted(cases, key=lambda item: item.get("shared_updated_at") or "", reverse=True)


def _upsert_workspace_case(path: Path, case_payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(case_payload, dict):
        raise ValueError("Shared workspace case payload must be an object")

    case_id = _clean(case_payload.get("id"))
    if not case_id:
        raise ValueError("Shared workspace case payload must include id")

    state = _read_workspace_state(path)
    stored_case = dict(case_payload)
    stored_case["shared_workspace_case"] = True
    stored_case["shared_updated_at"] = _utc_now()
    state["cases"][case_id] = stored_case
    state["updated_at"] = stored_case["shared_updated_at"]
    _write_workspace_state(path, state)
    return stored_case


def _handler_factory(workspace_file: Path):
    class ConnectorBridgeHandler(BaseHTTPRequestHandler):
        server_version = "EPIConnectorBridge/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003 - stdlib signature
            return

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            try:
                return json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError as exc:
                raise ValueError("Request body must be valid JSON") from exc

        def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib signature
            self._send_json(200, {"ok": True})

        def do_GET(self) -> None:  # noqa: N802 - stdlib signature
            parsed = urlparse.urlparse(self.path)
            if parsed.path == "/health":
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "service": "epi-connector-bridge",
                        "version": __version__,
                        "capabilities": {
                            "mock_records": True,
                            "shared_workspace": True,
                        },
                        "workspace_file": str(workspace_file),
                    },
                )
                return
            if parsed.path == "/api/workspace/state":
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "cases": _list_workspace_cases(workspace_file),
                        "workspace_file": str(workspace_file),
                    },
                )
                return
            self._send_json(404, {"ok": False, "error": "Not found"})

        def do_POST(self) -> None:  # noqa: N802 - stdlib signature
            parsed = urlparse.urlparse(self.path)
            if parsed.path == "/api/fetch-record":
                try:
                    payload = self._read_json_body()
                    system = payload.get("system")
                    record = fetch_live_record(
                        system=system,
                        connector_profile=payload.get("connector_profile") or {},
                        case_input=payload.get("case_input") or {},
                    )
                except (ValueError, FileNotFoundError) as exc:
                    self._send_json(400, {"ok": False, "error": str(exc)})
                    return
                except Exception as exc:  # pragma: no cover - exercised via endpoint tests
                    self._send_json(500, {"ok": False, "error": str(exc)})
                    return

                self._send_json(200, {"ok": True, "record": record})
                return

            if parsed.path == "/api/workspace/cases":
                try:
                    payload = self._read_json_body()
                    stored_case = _upsert_workspace_case(workspace_file, payload.get("case") or {})
                except ValueError as exc:
                    self._send_json(400, {"ok": False, "error": str(exc)})
                    return
                except Exception as exc:  # pragma: no cover - exercised via endpoint tests
                    self._send_json(500, {"ok": False, "error": str(exc)})
                    return

                self._send_json(200, {"ok": True, "case": stored_case})
                return

            self._send_json(404, {"ok": False, "error": "Not found"})

    return ConnectorBridgeHandler


def create_connector_bridge_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    workspace_file: Path | None = None,
    *,
    storage_dir: Path | None = None,
    batch_size: int = 50,
    batch_timeout: float = 2.0,
) -> ManagedGatewayServer:
    return ManagedGatewayServer(
        host,
        port,
        storage_dir=_resolve_storage_dir(storage_dir or workspace_file),
        batch_size=batch_size,
        batch_timeout=batch_timeout,
    )


def create_web_viewer_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_WEB_PORT,
    directory: Path | None = None,
) -> ThreadingHTTPServer:
    root = Path(directory or REPO_ROOT)
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    return ThreadingHTTPServer((host, port), handler)


def _endpoint_ready(url: str, *, timeout: float = 2.0) -> bool:
    request = urlrequest.Request(url, method="GET")
    try:
        with urlrequest.urlopen(request, timeout=timeout) as response:
            return 200 <= getattr(response, "status", 200) < 400
    except Exception:
        return False


def _start_server_thread(server: Any, name: str) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True, name=name)
    thread.start()
    return thread


def _shutdown_servers(servers: list[Any]) -> None:
    for server in servers:
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass


def _open_workspace_in_browser(url: str) -> bool:
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


@app.command("serve")
def serve(
    host: str = typer.Option(DEFAULT_HOST, "--host", help="Host to bind. Use 127.0.0.1 for local-only access."),
    port: int = typer.Option(DEFAULT_PORT, "--port", help="Port to bind for the local shared EPI gateway."),
    storage_dir: Path | None = typer.Option(
        None,
        "--storage-dir",
        "--workspace-file",
        help="Directory for the gateway event spool and shared case store.",
    ),
    access_token: str | None = typer.Option(
        None,
        "--access-token",
        help="Optional shared bearer token for the browser reviewer APIs.",
    ),
    users_file: Path | None = typer.Option(
        None,
        "--users-file",
        help="Optional JSON file with local gateway users for browser sign-in.",
    ),
) -> None:
    """
    Start the shared local EPI gateway for the browser Decision Ops flow.
    """
    previous_access_token = os.environ.get("EPI_GATEWAY_ACCESS_TOKEN")
    previous_users_file = os.environ.get("EPI_GATEWAY_USERS_FILE")
    if access_token:
        os.environ["EPI_GATEWAY_ACCESS_TOKEN"] = access_token
    elif previous_access_token is not None:
        os.environ.pop("EPI_GATEWAY_ACCESS_TOKEN", None)
    if users_file:
        os.environ["EPI_GATEWAY_USERS_FILE"] = str(users_file.resolve())
    elif previous_users_file is not None:
        os.environ.pop("EPI_GATEWAY_USERS_FILE", None)

    server = create_connector_bridge_server(host, port, storage_dir=storage_dir)
    bound_host, bound_port = server.server_address[:2]
    console.print(f"[green][OK][/green] EPI gateway running at http://{bound_host}:{bound_port}")
    console.print(f"[dim]Shared store:[/dim] {_resolve_storage_dir(storage_dir)}")
    console.print("[dim]Cases API:[/dim]  /api/cases")
    if users_file:
        auth_label = f"local users ({users_file.resolve()})"
    elif access_token:
        auth_label = "shared token"
    else:
        auth_label = "disabled"
    console.print(f"[dim]Auth:[/dim] {auth_label}")
    console.print("[dim]Press Ctrl+C to stop the gateway.[/dim]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping EPI gateway[/yellow]")
    finally:
        server.shutdown()
        server.server_close()
        if previous_access_token is None:
            os.environ.pop("EPI_GATEWAY_ACCESS_TOKEN", None)
        else:
            os.environ["EPI_GATEWAY_ACCESS_TOKEN"] = previous_access_token
        if previous_users_file is None:
            os.environ.pop("EPI_GATEWAY_USERS_FILE", None)
        else:
            os.environ["EPI_GATEWAY_USERS_FILE"] = previous_users_file


@app.command("serve-viewer")
def serve_viewer(
    host: str = typer.Option(DEFAULT_HOST, "--host", help="Host to bind. Use 127.0.0.1 for local-only access."),
    port: int = typer.Option(DEFAULT_WEB_PORT, "--port", help="Port to bind for the local Decision Ops web app."),
) -> None:
    """
    Start a local web server for the browser Decision Ops app.
    """
    server = create_web_viewer_server(host, port)
    bound_host, bound_port = server.server_address[:2]
    console.print(f"[green][OK][/green] EPI Decision Ops viewer running at http://{bound_host}:{bound_port}{VIEWER_PATH}")
    console.print("[dim]Press Ctrl+C to stop the local viewer server.[/dim]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping viewer server[/yellow]")
    finally:
        server.server_close()


@app.command("open")
def open_workspace(
    host: str = typer.Option(DEFAULT_HOST, "--host", help="Host to bind. Leave this as 127.0.0.1 for local-only use."),
    bridge_port: int = typer.Option(DEFAULT_PORT, "--bridge-port", help="Port for the local shared EPI gateway."),
    web_port: int = typer.Option(DEFAULT_WEB_PORT, "--web-port", help="Port for the local Decision Ops web app."),
    storage_dir: Path | None = typer.Option(
        None,
        "--storage-dir",
        "--workspace-file",
        help="Directory for the gateway event spool and shared case store.",
    ),
    access_token: str | None = typer.Option(
        None,
        "--access-token",
        help="Optional shared bearer token for the browser reviewer APIs.",
    ),
    users_file: Path | None = typer.Option(
        None,
        "--users-file",
        help="Optional JSON file with local gateway users for browser sign-in.",
    ),
    no_browser: bool = typer.Option(False, "--no-browser", help="Start the local services without opening the browser."),
) -> None:
    """
    Start the local gateway and Decision Ops app together, then open the browser.
    """
    servers: list[Any] = []
    viewer_url = f"http://{host}:{web_port}{VIEWER_PATH}"
    query = {"bridgeUrl": f"http://{host}:{bridge_port}"}
    effective_access_token = _clean(access_token) or _clean(os.getenv("EPI_GATEWAY_ACCESS_TOKEN"))
    if effective_access_token:
        query["accessToken"] = effective_access_token
    viewer_open_url = f"{viewer_url}?{urlparse.urlencode(query)}"
    bridge_url = f"http://{host}:{bridge_port}/ready"

    try:
        previous_access_token = os.environ.get("EPI_GATEWAY_ACCESS_TOKEN")
        previous_users_file = os.environ.get("EPI_GATEWAY_USERS_FILE")
        if access_token:
            os.environ["EPI_GATEWAY_ACCESS_TOKEN"] = access_token
        elif previous_access_token is not None:
            os.environ.pop("EPI_GATEWAY_ACCESS_TOKEN", None)
        if users_file:
            os.environ["EPI_GATEWAY_USERS_FILE"] = str(users_file.resolve())
        elif previous_users_file is not None:
            os.environ.pop("EPI_GATEWAY_USERS_FILE", None)
        try:
            bridge_server = create_connector_bridge_server(host, bridge_port, storage_dir=storage_dir)
        except OSError as exc:
            if not _endpoint_ready(bridge_url):
                console.print(f"[red][FAIL][/red] Port {bridge_port} is busy and no EPI gateway is responding there.")
                raise typer.Exit(1) from exc
            bridge_server = None
            console.print(f"[dim]Using the existing EPI gateway at http://{host}:{bridge_port}[/dim]")
        else:
            servers.append(bridge_server)
            _start_server_thread(bridge_server, "epi-gateway")
            console.print(f"[green][OK][/green] Started EPI gateway at http://{host}:{bridge_port}")

        try:
            web_server = create_web_viewer_server(host, web_port)
        except OSError as exc:
            if not _endpoint_ready(viewer_url):
                console.print(f"[red][FAIL][/red] Port {web_port} is busy and no EPI Decision Ops viewer is responding there.")
                raise typer.Exit(1) from exc
            web_server = None
            console.print(f"[dim]Using the existing Decision Ops viewer at http://{host}:{web_port}[/dim]")
        else:
            servers.append(web_server)
            _start_server_thread(web_server, "epi-decision-ops-viewer")
            console.print(f"[green][OK][/green] Started Decision Ops viewer at {viewer_url}")

        deadline = time.time() + 5.0
        while time.time() < deadline:
            if _endpoint_ready(bridge_url) and _endpoint_ready(viewer_url):
                break
            time.sleep(0.1)

        if not _endpoint_ready(bridge_url):
            console.print("[red][FAIL][/red] The EPI gateway did not become ready in time.")
            raise typer.Exit(1)
        if not _endpoint_ready(viewer_url):
            console.print("[red][FAIL][/red] The local Decision Ops viewer did not become ready in time.")
            raise typer.Exit(1)

        console.print()
        console.print("[bold green]EPI is ready.[/bold green]")
        console.print(f"[dim]Viewer:[/dim]  {viewer_url}")
        console.print(f"[dim]Gateway:[/dim] http://{host}:{bridge_port}")
        console.print(f"[dim]Shared:[/dim]  {_resolve_storage_dir(storage_dir)}")
        if users_file:
            auth_label = f"local users ({users_file.resolve()})"
        elif effective_access_token:
            auth_label = "shared token"
        else:
            auth_label = "disabled"
        console.print(f"[dim]Auth:[/dim] {auth_label}")
        console.print("[dim]The browser app will load the shared inbox from the gateway when it opens.[/dim]")

        if not no_browser:
            opened = _open_workspace_in_browser(viewer_open_url)
            if opened:
                console.print("[dim]Opened the browser for you.[/dim]")
            else:
                console.print("[yellow][!][/yellow] Could not open the browser automatically.")

        console.print("[dim]Leave this command running while you use the app. Press Ctrl+C to stop both services.[/dim]")
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping EPI local workspace[/yellow]")
    finally:
        _shutdown_servers(servers)
        if 'previous_access_token' in locals():
            if previous_access_token is None:
                os.environ.pop("EPI_GATEWAY_ACCESS_TOKEN", None)
            else:
                os.environ["EPI_GATEWAY_ACCESS_TOKEN"] = previous_access_token
        if 'previous_users_file' in locals():
            if previous_users_file is None:
                os.environ.pop("EPI_GATEWAY_USERS_FILE", None)
            else:
                os.environ["EPI_GATEWAY_USERS_FILE"] = previous_users_file
