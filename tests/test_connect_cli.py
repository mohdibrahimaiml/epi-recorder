import json
import re
import threading
from pathlib import Path
from urllib import request as urlrequest

from typer.testing import CliRunner

from epi_cli.connect import app, create_connector_bridge_server, create_web_viewer_server, fetch_live_record


runner = CliRunner()


def _plain(output: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", output)


def _write_csv(path: Path) -> None:
    path.write_text(
        "case_id,summary,status\nrefund-001,High value refund,pending_review\nrefund-002,Duplicate order,approved\n",
        encoding="utf-8",
    )


def test_connect_serve_help_mentions_local_gateway():
    result = runner.invoke(app, ["serve", "--help"])
    output = _plain(result.output)

    assert result.exit_code == 0
    assert "shared epi gateway" in output.lower()
    assert "--port" in output


def test_connect_open_help_mentions_browser_app():
    result = runner.invoke(app, ["open", "--help"])
    output = _plain(result.output)

    assert result.exit_code == 0
    assert "decision ops app" in output.lower()
    assert "--bridge-port" in output
    assert "--web-port" in output


def test_fetch_live_record_reads_csv_export(tmp_path):
    csv_path = tmp_path / "source_export.csv"
    _write_csv(csv_path)

    record = fetch_live_record(
        "csv-export",
        {"csv_path": str(csv_path), "id_column": "case_id"},
        {"case_id": "refund-001"},
    )

    assert record["bridge_system"] == "csv-export"
    assert record["case_id"] == "refund-001"
    assert record["summary"] == "High value refund"
    assert record["decision_state"] == "pending_review"


def test_fetch_live_record_can_return_mock_preview_without_vendor_credentials():
    record = fetch_live_record(
        "zendesk",
        {"preview_mode": "sample"},
        {"case_id": "refund-001"},
    )

    assert record["bridge_system"] == "zendesk"
    assert record["is_mock"] is True
    assert record["bridge_mode"] == "mock"
    assert record["ticket_id"] == "refund-001"


def test_fetch_live_record_can_fallback_to_mock_when_real_connector_is_not_configured():
    record = fetch_live_record(
        "salesforce",
        {"allow_mock_fallback": True},
        {"case_id": "approval-7"},
    )

    assert record["bridge_system"] == "salesforce"
    assert record["is_mock"] is True
    assert record["bridge_mode"] == "mock-fallback"
    assert "Missing required connector field" in record["bridge_warning"]


def test_fetch_live_record_rejects_unknown_system():
    try:
        fetch_live_record("unknown-system", {}, {})
        raised = False
    except ValueError as exc:
        raised = True
        message = str(exc)

    assert raised
    assert "Unsupported connector system" in message


def test_connector_bridge_server_handles_health_and_fetch(tmp_path):
    csv_path = tmp_path / "source_export.csv"
    _write_csv(csv_path)

    server = create_connector_bridge_server("127.0.0.1", 0, storage_dir=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]

    try:
        with urlrequest.urlopen(f"http://{host}:{port}/health", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["ok"] is True
        assert payload["service"] == "epi-gateway"
        assert payload["capabilities"]["mock_records"] is True
        assert payload["capabilities"]["shared_workspace"] is True

        request = urlrequest.Request(
            f"http://{host}:{port}/api/fetch-record",
            data=json.dumps(
                {
                    "system": "csv-export",
                    "connector_profile": {
                        "csv_path": str(csv_path),
                        "id_column": "case_id",
                    },
                    "case_input": {
                        "case_id": "refund-002",
                        "workflow_name": "Refund approvals",
                    },
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlrequest.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["ok"] is True
        assert payload["record"]["bridge_system"] == "csv-export"
        assert payload["record"]["case_id"] == "refund-002"
        assert payload["record"]["summary"] == "Duplicate order"
        assert payload["case"]["preview_only"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_connector_bridge_server_persists_shared_cases_in_gateway_store(tmp_path):
    storage_dir = tmp_path / "shared-store"
    server = create_connector_bridge_server("127.0.0.1", 0, storage_dir=storage_dir)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]

    try:
        publish_request = urlrequest.Request(
            f"http://{host}:{port}/api/workspace/cases",
            data=json.dumps(
                {
                    "case": {
                        "id": "shared-case-1",
                        "source_name": "shared_case.epi",
                        "manifest": {
                            "created_at": "2026-03-27T10:00:00Z",
                            "workflow_name": "Refund approvals",
                        },
                        "steps": [],
                        "analysis": {"summary": "Shared case ready for team review", "review_required": True},
                        "integrity": {"ok": True, "checked": 0, "mismatches": []},
                        "signature": {"valid": False, "reason": "Unsigned manifest"},
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlrequest.urlopen(publish_request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["ok"] is True
        assert payload["case"]["id"] == "shared-case-1"
        assert payload["case"]["shared_workspace_case"] is True

        with urlrequest.urlopen(f"http://{host}:{port}/api/workspace/state", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["ok"] is True
        assert len(payload["cases"]) == 1
        assert payload["cases"][0]["id"] == "shared-case-1"
        assert (storage_dir / "cases.sqlite3").exists() is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_web_viewer_server_serves_index():
    server = create_web_viewer_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]

    try:
        with urlrequest.urlopen(f"http://{host}:{port}/web_viewer/index.html", timeout=5) as response:
            html = response.read().decode("utf-8")

        assert "EPI Case Viewer" in html
        assert 'id="epi-view-context"' in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_connect_open_starts_services_and_opens_browser(monkeypatch):
    class FakeServer:
        def __init__(self):
            self.shutdown_called = False
            self.server_close_called = False
            self.server_address = ("127.0.0.1", 8765)

        def serve_forever(self):
            return None

        def shutdown(self):
            self.shutdown_called = True

        def server_close(self):
            self.server_close_called = True

    bridge_server = FakeServer()
    web_server = FakeServer()
    web_server.server_address = ("127.0.0.1", 8000)
    opened_urls: list[str] = []

    monkeypatch.setattr("epi_cli.connect.create_connector_bridge_server", lambda host, port, **kwargs: bridge_server)
    monkeypatch.setattr("epi_cli.connect.create_web_viewer_server", lambda host, port: web_server)
    monkeypatch.setattr("epi_cli.connect._endpoint_ready", lambda url, timeout=2.0: True)
    monkeypatch.setattr("epi_cli.connect._open_workspace_in_browser", lambda url: opened_urls.append(url) or True)
    monkeypatch.setattr("epi_cli.connect.time.sleep", lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()))

    result = runner.invoke(app, ["open"])

    assert result.exit_code == 0
    assert "EPI is ready." in result.output
    assert "Opened the browser for you." in result.output
    assert opened_urls == ["http://127.0.0.1:8000/web_viewer/index.html?bridgeUrl=http%3A%2F%2F127.0.0.1%3A8765"]
    assert bridge_server.shutdown_called is True
    assert bridge_server.server_close_called is True
    assert web_server.shutdown_called is True
    assert web_server.server_close_called is True


def test_connect_open_passes_access_token_to_browser_session(monkeypatch):
    class FakeServer:
        def __init__(self):
            self.shutdown_called = False
            self.server_close_called = False
            self.server_address = ("127.0.0.1", 8765)

        def serve_forever(self):
            return None

        def shutdown(self):
            self.shutdown_called = True

        def server_close(self):
            self.server_close_called = True

    bridge_server = FakeServer()
    web_server = FakeServer()
    web_server.server_address = ("127.0.0.1", 8000)
    opened_urls: list[str] = []

    monkeypatch.setattr("epi_cli.connect.create_connector_bridge_server", lambda host, port, **kwargs: bridge_server)
    monkeypatch.setattr("epi_cli.connect.create_web_viewer_server", lambda host, port: web_server)
    monkeypatch.setattr("epi_cli.connect._endpoint_ready", lambda url, timeout=2.0: True)
    monkeypatch.setattr("epi_cli.connect._open_workspace_in_browser", lambda url: opened_urls.append(url) or True)
    monkeypatch.setattr("epi_cli.connect.time.sleep", lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()))

    result = runner.invoke(app, ["open", "--access-token", "shared-secret"])

    assert result.exit_code == 0
    assert opened_urls == ["http://127.0.0.1:8000/web_viewer/index.html?bridgeUrl=http%3A%2F%2F127.0.0.1%3A8765&accessToken=shared-secret"]
