from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from epi_gateway.approval_notify import send_signed_webhook
from epi_gateway.main import GatewayRuntimeSettings, create_app
from epi_gateway.worker import EvidenceWorker


class _WebhookResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _make_worker(tmp_path: Path) -> EvidenceWorker:
    return EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)


def _approval_request_event() -> dict:
    return {
        "case_id": "case-approval-1",
        "workflow_id": "wf-approval-1",
        "workflow_name": "Insurance claim denial",
        "kind": "agent.approval.request",
        "content": {
            "approval_id": "approval-1",
            "action": "deny_claim",
            "reason": "Claim amount exceeds the manual review threshold.",
            "requested_from": "claims.manager@carrier.com",
            "timeout_minutes": 120,
        },
    }


def test_send_signed_webhook_adds_hmac_signature_header():
    captured = {}

    def _fake_urlopen(request, timeout=10):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return _WebhookResponse()

    with patch("epi_gateway.approval_notify.urllib.request.urlopen", side_effect=_fake_urlopen):
        send_signed_webhook(
            "https://hook.example/approval",
            {"event": "approval.requested", "workflow_id": "wf-1"},
            secret="top-secret",
            timeout_seconds=7,
        )

    assert captured["url"] == "https://hook.example/approval"
    assert captured["timeout"] == 7
    header_map = {key.lower(): value for key, value in captured["headers"].items()}
    assert header_map["x-epi-signature"].startswith("sha256=")


def test_approval_request_triggers_webhook_and_email_notifications(tmp_path):
    worker = _make_worker(tmp_path)
    settings = GatewayRuntimeSettings(
        storage_dir=str(tmp_path),
        approval_base_url="http://gateway.test",
        approval_webhook_url="https://hook.example/approval",
        approval_webhook_secret="pilot-secret",
        smtp_host="smtp.example.test",
        smtp_from="epi@example.test",
    )
    create_app(worker=worker, settings=settings)

    def _run_inline(func, *args, task_name=None, **kwargs):
        func(*args, **kwargs)

    with patch("epi_gateway.main._spawn_background_task", side_effect=_run_inline):
        with patch("epi_gateway.main.send_signed_webhook") as mock_webhook:
            with patch("epi_gateway.main.send_approval_email") as mock_email:
                worker.store_items([_approval_request_event()])

    mock_webhook.assert_called_once()
    webhook_args, webhook_kwargs = mock_webhook.call_args
    assert webhook_args[0] == "https://hook.example/approval"
    payload = webhook_args[1]
    assert payload["event"] == "approval.requested"
    assert payload["workflow_id"] == "wf-approval-1"
    assert payload["approval_id"] == "approval-1"
    assert payload["approve_url"].endswith("/api/approve/wf-approval-1/approval-1?decision=approve")
    assert payload["deny_url"].endswith("/api/approve/wf-approval-1/approval-1?decision=deny")
    assert webhook_kwargs["secret"] == "pilot-secret"

    mock_email.assert_called_once()
    assert mock_email.call_args.kwargs["to_address"] == "claims.manager@carrier.com"
    assert mock_email.call_args.kwargs["workflow_id"] == "wf-approval-1"


def test_approval_notification_failure_is_non_fatal(tmp_path):
    worker = _make_worker(tmp_path)
    settings = GatewayRuntimeSettings(
        storage_dir=str(tmp_path),
        approval_base_url="http://gateway.test",
        approval_webhook_url="https://hook.example/approval",
        approval_webhook_secret="pilot-secret",
    )
    create_app(worker=worker, settings=settings)

    def _run_inline(func, *args, task_name=None, **kwargs):
        func(*args, **kwargs)

    with patch("epi_gateway.main._spawn_background_task", side_effect=_run_inline):
        with patch("epi_gateway.approval_notify.urllib.request.urlopen", side_effect=OSError("refused")):
            with patch("time.sleep"):
                touched = worker.store_items([_approval_request_event()])

    assert touched == ["case-approval-1"]
    stored = worker.get_case("case-approval-1")
    assert stored is not None
    assert stored["id"] == "case-approval-1"


def test_approval_callback_records_response_and_stays_auth_free(tmp_path):
    worker = _make_worker(tmp_path)
    settings = GatewayRuntimeSettings(
        storage_dir=str(tmp_path),
        access_token="shared-secret",
        approval_base_url="http://gateway.test",
    )
    app = create_app(worker=worker, settings=settings)
    worker.store_items([_approval_request_event()])

    with TestClient(app) as client:
        unauthorized_cases = client.get("/api/cases")
        assert unauthorized_cases.status_code == 401

        response = client.post(
            "/api/approve/wf-approval-1/approval-1",
            params={
                "decision": "approve",
                "reviewer": "claims.manager@carrier.com",
                "reason": "Manager reviewed the denial evidence.",
            },
        )

    assert response.status_code == 200
    assert "Decision recorded for workflow" in response.text
    case = worker.get_case("case-approval-1")
    kinds = [step["kind"] for step in case["steps"]]
    assert "agent.approval.response" in kinds
    responses = [step for step in case["steps"] if step["kind"] == "agent.approval.response"]
    assert responses[-1]["content"]["approved"] is True
    assert responses[-1]["content"]["reviewer"] == "claims.manager@carrier.com"
    assert responses[-1]["content"]["response_source"] == "approval-link"


def test_worker_recovers_orphan_sessions_on_restart(tmp_path):
    worker = _make_worker(tmp_path)
    worker.store_items(
        [
            {
                "case_id": "case-recovery-1",
                "workflow_id": "wf-recovery-1",
                "workflow_name": "Insurance claim denial",
                "kind": "agent.run.start",
                "content": {"goal": "Review claim CLM-77"},
            }
        ]
    )

    restarted = _make_worker(tmp_path)
    restarted.start()
    try:
        recovered_case = restarted.get_case("case-recovery-1")
        open_sessions = restarted.case_store.list_open_sessions()
    finally:
        restarted.stop()

    assert recovered_case is not None
    assert recovered_case["status"] == "blocked"
    assert "agent.run.recovered" in [step["kind"] for step in recovered_case["steps"]]
    assert "session_recovered" in [item["kind"] for item in recovered_case["activity"]]
    assert open_sessions == []
