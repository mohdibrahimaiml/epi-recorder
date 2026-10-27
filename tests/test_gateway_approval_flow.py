from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
import typer
from fastapi.testclient import TestClient

from epi_cli.verify import verify_command
from epi_core.approval_links import UNVERIFIED_REVIEWER
from epi_core.review import verify_human_approvals
from epi_gateway.approval_notify import send_approval_email, send_signed_webhook
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
    # The link now opens the confirmation page and carries a single-use token;
    # the decision is chosen there, never taken straight from the URL.
    approve = urlparse(payload["approve_url"])
    deny = urlparse(payload["deny_url"])
    assert approve.path == "/api/approve/wf-approval-1/approval-1"
    assert deny.path == "/api/approve/wf-approval-1/approval-1"
    approve_qs = parse_qs(approve.query)
    deny_qs = parse_qs(deny.query)
    assert approve_qs["decision"] == ["approve"]
    assert deny_qs["decision"] == ["deny"]
    assert approve_qs["token"] == deny_qs["token"]
    assert len(approve_qs["token"][0]) >= 32
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


def _mint(
    worker: EvidenceWorker,
    workflow_id="wf-approval-1",
    approval_id="approval-1",
    ttl_hours=72.0,
) -> str:
    return worker.create_approval_link(workflow_id, approval_id, ttl_hours=ttl_hours)


def _responses(worker: EvidenceWorker, case_id: str = "case-approval-1") -> list[dict]:
    case = worker.get_case(case_id) or {}
    return [step for step in case.get("steps", []) if step["kind"] == "agent.approval.response"]


def _app(tmp_path, *, access_token=None):
    worker = _make_worker(tmp_path)
    settings = GatewayRuntimeSettings(
        storage_dir=str(tmp_path),
        access_token=access_token,
        approval_base_url="http://gateway.test",
    )
    return worker, create_app(worker=worker, settings=settings)


def test_approval_callback_records_response_and_stays_auth_free(tmp_path):
    worker, app = _app(tmp_path, access_token="shared-secret")
    worker.store_items([_approval_request_event()])
    token = _mint(worker)

    with TestClient(app) as client:
        unauthorized_cases = client.get("/api/cases")
        assert unauthorized_cases.status_code == 401

        response = client.post(
            "/api/approve/wf-approval-1/approval-1",
            data={
                "token": token,
                "decision": "approve",
                "reason": "Manager reviewed the denial evidence.",
            },
        )

    assert response.status_code == 200
    assert "Decision recorded for workflow" in response.text
    responses = _responses(worker)
    assert responses[-1]["content"]["approved"] is True
    assert responses[-1]["content"]["response_source"] == "approval-link"
    # A link click is unsigned and never claims to be a person: no principal was
    # presented, and the query string cannot supply one.
    assert responses[-1]["content"]["reviewer"] == UNVERIFIED_REVIEWER
    assert responses[-1]["content"]["reviewer_verified"] is False
    assert responses[-1]["content"]["approval_source"] == "gateway_link_unsigned"


def test_get_confirmation_page_records_nothing_and_spends_nothing(tmp_path):
    worker, app = _app(tmp_path)
    worker.store_items([_approval_request_event()])
    token = _mint(worker)

    with TestClient(app) as client:
        response = client.get(
            "/api/approve/wf-approval-1/approval-1", params={"token": token}
        )

    assert response.status_code == 200
    assert "link click, not a signed approval" in response.text
    assert "epi review" in response.text
    assert "deny_claim" in response.text
    assert _responses(worker) == []
    # The GET must not spend the token, or the person could never confirm.
    assert worker.check_approval_link("wf-approval-1", "approval-1", token) == "ok"


def test_post_records_once_then_replay_is_403(tmp_path):
    worker, app = _app(tmp_path)
    worker.store_items([_approval_request_event()])
    token = _mint(worker)

    with TestClient(app) as client:
        first = client.post(
            "/api/approve/wf-approval-1/approval-1",
            data={"token": token, "decision": "approve"},
        )
        replay = client.post(
            "/api/approve/wf-approval-1/approval-1",
            data={"token": token, "decision": "approve"},
        )

    assert first.status_code == 200
    assert replay.status_code == 403
    assert len(_responses(worker)) == 1


def test_expired_token_is_403(tmp_path):
    worker, app = _app(tmp_path)
    worker.store_items([_approval_request_event()])
    token = _mint(worker, ttl_hours=0.001)
    with worker.case_store._connect() as connection:
        connection.execute(
            "UPDATE approval_link_tokens SET expires_at = ?",
            ("2000-01-01T00:00:00+00:00",),
        )
        connection.commit()

    with TestClient(app) as client:
        get_response = client.get(
            "/api/approve/wf-approval-1/approval-1", params={"token": token}
        )
        post_response = client.post(
            "/api/approve/wf-approval-1/approval-1",
            data={"token": token, "decision": "approve"},
        )

    assert get_response.status_code == 403
    assert post_response.status_code == 403
    assert _responses(worker) == []


def test_token_for_another_workflow_is_403(tmp_path):
    worker, app = _app(tmp_path)
    worker.store_items([_approval_request_event()])
    token = _mint(worker, workflow_id="wf-approval-1", approval_id="approval-1")

    with TestClient(app) as client:
        response = client.post(
            "/api/approve/wf-someone-else/approval-1",
            data={"token": token, "decision": "approve"},
        )

    assert response.status_code == 403
    assert _responses(worker) == []
    # The mismatch did not burn the token it was minted for.
    assert worker.check_approval_link("wf-approval-1", "approval-1", token) == "ok"


def test_a_bad_decision_does_not_burn_the_token(tmp_path):
    worker, app = _app(tmp_path)
    worker.store_items([_approval_request_event()])
    token = _mint(worker)

    with TestClient(app) as client:
        bad = client.post(
            "/api/approve/wf-approval-1/approval-1",
            data={"token": token, "decision": "maybe"},
        )
        good = client.post(
            "/api/approve/wf-approval-1/approval-1",
            data={"token": token, "decision": "approve"},
        )

    assert bad.status_code == 400
    assert good.status_code == 200
    assert len(_responses(worker)) == 1


def test_pre_upgrade_link_without_a_token_is_403(tmp_path):
    """A link issued before the upgrade carries no token: it must stop working."""
    worker, app = _app(tmp_path)
    worker.store_items([_approval_request_event()])

    with TestClient(app) as client:
        old_get = client.get(
            "/api/approve/wf-approval-1/approval-1", params={"decision": "approve"}
        )
        old_post = client.post(
            "/api/approve/wf-approval-1/approval-1", data={"decision": "approve"}
        )

    assert old_get.status_code == 403
    assert old_post.status_code == 403
    assert _responses(worker) == []


def test_refusals_share_one_body_and_reviewer_query_is_ignored(tmp_path):
    worker, app = _app(tmp_path)
    worker.store_items([_approval_request_event()])
    token = _mint(worker)
    other_token = _mint(worker, approval_id="approval-2")

    with TestClient(app) as client:
        missing = client.get("/api/approve/wf-approval-1/approval-1")
        wrong = client.get(
            "/api/approve/wf-approval-1/approval-1", params={"token": "not-a-token"}
        )
        mismatched = client.get(
            "/api/approve/wf-approval-1/approval-1", params={"token": other_token}
        )
        # ?reviewer=ceo must never decide who approved.
        recorded = client.post(
            "/api/approve/wf-approval-1/approval-1",
            params={"reviewer": "ceo@bank.com"},
            data={"token": token, "decision": "approve"},
        )

    assert missing.status_code == wrong.status_code == mismatched.status_code == 403
    assert missing.text == wrong.text == mismatched.text
    assert recorded.status_code == 200
    assert _responses(worker)[-1]["content"]["reviewer"] == UNVERIFIED_REVIEWER


def test_action_and_reason_are_escaped_in_the_pages(tmp_path):
    worker, app = _app(tmp_path)
    worker.store_items(
        [
            {
                "case_id": "case-xss-1",
                "workflow_id": "wf-xss-1",
                "workflow_name": "XSS",
                "kind": "agent.approval.request",
                "content": {
                    "approval_id": "approval-x",
                    "action": "<script>alert('action')</script>",
                    "reason": "<script>alert('reason')</script>",
                },
            }
        ]
    )
    token = _mint(worker, workflow_id="wf-xss-1", approval_id="approval-x")

    with TestClient(app) as client:
        page = client.get("/api/approve/wf-xss-1/approval-x", params={"token": token})
        recorded = client.post(
            "/api/approve/wf-xss-1/approval-x",
            data={
                "token": token,
                "decision": "approve",
                "reason": "<script>alert('note')</script>",
            },
        )

    assert page.status_code == 200
    assert "<script>alert" not in page.text
    assert "&lt;script&gt;alert(&#x27;action&#x27;)&lt;/script&gt;" in page.text
    assert recorded.status_code == 200
    assert "<script>alert" not in recorded.text


def test_approval_email_escapes_captured_content():
    sent = {}

    class _FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, *args):
            pass

        def send_message(self, message):
            sent["html"] = message.get_payload(0).get_payload(decode=True).decode("utf-8")

    with patch("epi_gateway.approval_notify.smtplib.SMTP", _FakeSMTP):
        send_approval_email(
            to_address="claims.manager@carrier.com",
            workflow_id="wf-<script>",
            action="<script>alert('action')</script>",
            reason="<script>alert('reason')</script>",
            approve_url="http://gateway.test/api/approve/x/y?token=t",
            deny_url="http://gateway.test/api/approve/x/y?token=t",
            case_url=None,
            smtp_host="smtp.example.test",
            smtp_from="epi@example.test",
        )

    assert "<script>" not in sent["html"]
    assert "&lt;script&gt;" in sent["html"]


@pytest.mark.parametrize(
    ("headers", "expected_source", "expected_verified"),
    [
        ({}, "gateway_link_unsigned", False),
        ({"Authorization": "Bearer shared-secret"}, "gateway_link_authenticated", True),
    ],
)
def test_gateway_link_click_never_satisfies_require_human_approval(
    tmp_path, headers, expected_source, expected_verified
):
    """A link click is agent/system-reported — anonymous or authenticated."""
    worker, app = _app(tmp_path, access_token="shared-secret")
    worker.store_items([_approval_request_event()])
    token = _mint(worker)

    with TestClient(app) as client:
        response = client.post(
            "/api/approve/wf-approval-1/approval-1",
            headers=headers,
            data={"token": token, "decision": "approve"},
        )
    assert response.status_code == 200

    content = _responses(worker)[-1]["content"]
    assert content["approval_source"] == expected_source
    assert content["reviewer_verified"] is expected_verified

    exported = tmp_path / "approved-by-link.epi"
    worker.case_store.export_case_to_artifact("case-approval-1", exported)

    state = verify_human_approvals(exported)
    assert state["agent_reported_approvals"] == 1
    assert state["status"] != "verified"
    assert state["requirement_met"] is False
    with pytest.raises(typer.Exit):
        verify_command(ctx=MagicMock(), epi_file=exported, require_human_approval=True)


def test_approval_pages_set_no_store_and_locking_headers(tmp_path):
    worker, app = _app(tmp_path)
    worker.store_items([_approval_request_event()])
    token = _mint(worker)

    with TestClient(app) as client:
        confirmation = client.get(
            "/api/approve/wf-approval-1/approval-1", params={"token": token}
        )
        recorded = client.post(
            "/api/approve/wf-approval-1/approval-1",
            data={"token": token, "decision": "approve"},
        )
        refused = client.get(
            "/api/approve/wf-approval-1/approval-1", params={"token": "nope"}
        )

    assert confirmation.status_code == 200
    assert recorded.status_code == 200
    assert refused.status_code == 403
    for response in (confirmation, recorded, refused):
        # The token is in the GET URL: no caches, no Referer, no framing.
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-frame-options"] == "DENY"
        csp = response.headers["content-security-policy"]
        assert "default-src 'none'" in csp
        assert "form-action 'self'" in csp
        assert "frame-ancestors 'none'" in csp


def _request_without_approval_id(reason: str) -> dict:
    return {
        "case_id": "case-no-id",
        "workflow_id": "wf-no-id",
        "workflow_name": "No approval id",
        "kind": "agent.approval.request",
        "content": {"action": "deny_claim", "reason": reason},
    }


def test_requests_without_an_approval_id_get_distinct_ids_and_tokens(tmp_path):
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

    payloads: list[dict] = []

    def _capture(url, payload, **kwargs):
        payloads.append(payload)

    with patch("epi_gateway.main._spawn_background_task", side_effect=_run_inline):
        with patch("epi_gateway.main.send_signed_webhook", side_effect=_capture):
            worker.store_items(
                [
                    _request_without_approval_id("first"),
                    _request_without_approval_id("second"),
                ]
            )

    assert len(payloads) == 2
    ids = {payload["approval_id"] for payload in payloads}
    tokens = {
        parse_qs(urlparse(payload["approve_url"]).query)["token"][0]
        for payload in payloads
    }
    # Never the action name: two requests share it, so they would share one id
    # (and approving one would approve both).
    assert "deny_claim" not in ids
    assert len(ids) == 2
    assert len(tokens) == 2


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
