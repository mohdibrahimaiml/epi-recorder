"""Gateway capture-manifest E2E: proxy -> case -> export -> manifest + verifier."""
import json
import os
import time
from pathlib import Path

os.environ["EPI_NOTARIZE"] = "0"

from fastapi.testclient import TestClient

from epi_core.container import EPIContainer
from epi_gateway.main import GatewayRuntimeSettings, create_app
from epi_gateway.worker import EvidenceWorker

import epi_gateway.main as gwmain
from epi_core.llm_capture import LLMCaptureRequest


class _ProxyResult:
    status_code = 200
    body = {"id": "resp_1", "choices": [{"message": {"role": "assistant", "content": "ok"}}]}
    headers = {"content-type": "application/json"}


def _capture_request():
    return LLMCaptureRequest.model_validate({
        "provider": "openai-compatible",
        "request": {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]},
        "response": {"model": "gpt-4o-mini", "choices": [{"message": {"role": "assistant", "content": "ok"}}]},
    })


def _drive_proxy(tmp_path: Path, monkeypatch, *, headers: dict | None = None) -> Path:
    monkeypatch.setattr(
        gwmain, "relay_openai_chat_completions",
        lambda payload, hdrs: (_ProxyResult(), _capture_request()),
    )
    worker = EvidenceWorker(storage_dir=tmp_path / "vault", batch_size=1, batch_timeout=0.1)
    settings = GatewayRuntimeSettings(
        proxy_failure_mode="fail-closed",
        storage_dir=str(tmp_path / "vault"),
    )
    app = create_app(worker=worker, settings=settings)
    with TestClient(app) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]},
            headers=headers or {},
        )
        assert resp.status_code == 200
        deadline = time.time() + 15
        cases: list = []
        while time.time() < deadline:
            cases = client.get("/api/cases").json().get("cases", [])
            if cases:
                break
            time.sleep(0.2)
        assert cases, "no gateway case was projected"
        # Export the case with the most steps (request+response may split cases).
        best_id, best_n = None, -1
        for c in cases:
            detail = client.get(f"/api/cases/{c['id']}").json()
            n = len((detail.get("case") or {}).get("steps", []))
            if n > best_n:
                best_id, best_n = c["id"], n
        exp = client.post(f"/api/cases/{best_id}/export")
        assert exp.status_code == 200
        out = tmp_path / "gw.epi"
        out.write_bytes(exp.content)
        return out


def test_gateway_export_manifest_labels_gateway_path(tmp_path, monkeypatch):
    out = _drive_proxy(tmp_path, monkeypatch)
    data = EPIContainer.read_member_json(out, "artifacts/manifest.json")
    assert data["capture_path"] == "gateway"
    assert data["gateway_enforcement"] == "fail_closed"
    assert data["fail_open_events"] == []
    assert data["segments"], "mixed/empty segments hide the capture path"
    assert {s["capture_path"] for s in data["segments"]} == {"gateway"}
    assert len(data["known_gaps"]) > 0


def test_gateway_client_header_cannot_downgrade_fail_closed(tmp_path, monkeypatch):
    out = _drive_proxy(tmp_path, monkeypatch, headers={"x-epi-failure-mode": "fail-open"})
    data = EPIContainer.read_member_json(out, "artifacts/manifest.json")
    assert data["gateway_enforcement"] == "fail_closed"
    assert data["fail_open_events"] == []

    from typer.testing import CliRunner
    from epi_cli.main import app as cli_app

    result = CliRunner().invoke(cli_app, ["verify", str(out), "--json"])
    report = json.loads(result.output)
    assert report["enforcement_downgraded"] is False


def test_event_to_step_carries_capture_tags():
    from epi_core.capture import CaptureEventModel
    from epi_core.case_store import _event_to_step

    event = CaptureEventModel(
        kind="llm.request",
        content={"messages": []},
        meta={"_epi_capture": {
            "capture_path": "gateway",
            "gateway_enforcement": "fail_closed",
            "streaming": False,
        }},
    )
    step = _event_to_step(event, 0)
    cap = step["content"]["_epi_capture"]
    assert cap["capture_path"] == "gateway"
    assert cap["gateway_enforcement"] == "fail_closed"
    assert cap["event_id"] == event.event_id
