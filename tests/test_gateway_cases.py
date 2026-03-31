import json
import time
import zipfile

from fastapi.testclient import TestClient

from epi_gateway.main import GatewayRuntimeSettings, create_app
from epi_gateway.worker import EvidenceWorker


def test_gateway_case_api_review_and_export(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
    app = create_app(worker=worker)

    with TestClient(app) as client:
        worker.store_items(
            [
                {
                    "kind": "llm.request",
                    "content": {"messages": [{"role": "user", "content": "Approve this refund?"}]},
                    "meta": {"decision_id": "decision-1", "trace_id": "trace-1", "workflow_name": "Refund approvals"},
                },
                {
                    "kind": "llm.response",
                    "content": {"output_text": "Escalate for approval"},
                    "meta": {"decision_id": "decision-1", "trace_id": "trace-1", "workflow_name": "Refund approvals"},
                },
            ]
        )

        list_payload = client.get("/api/cases").json()
        assert list_payload["ok"] is True
        assert len(list_payload["cases"]) == 1
        case_id = list_payload["cases"][0]["id"]

        detail_payload = client.get(f"/api/cases/{case_id}").json()
        assert detail_payload["ok"] is True
        assert detail_payload["case"]["backend_case"] is True
        assert detail_payload["case"]["source_trust_state"]["code"] == "verify-source"

        review_payload = {
            "review_version": "1.0.0",
            "reviewed_by": "qa@epilabs.org",
            "reviewed_at": "2026-03-27T12:00:00Z",
            "reviews": [
                {
                    "outcome": "confirmed_fault",
                    "notes": "Manual review completed.",
                    "reviewer": "qa@epilabs.org",
                    "timestamp": "2026-03-27T12:00:00Z",
                }
            ],
        }
        reviewed = client.post(f"/api/cases/{case_id}/reviews", json=review_payload).json()
        assert reviewed["ok"] is True
        assert reviewed["case"]["review"]["reviewed_by"] == "qa@epilabs.org"

        export_response = client.post(f"/api/cases/{case_id}/export")
        assert export_response.status_code == 200
        export_path = tmp_path / "exported.epi"
        export_path.write_bytes(export_response.content)
        assert zipfile.is_zipfile(export_path) is True
        with zipfile.ZipFile(export_path, "r") as archive:
            names = set(archive.namelist())
        assert "manifest.json" in names
        assert "review.json" in names


def test_gateway_fetch_record_creates_preview_case(tmp_path):
    csv_path = tmp_path / "records.csv"
    csv_path.write_text(
        "case_id,summary,status\nrefund-001,High value refund,pending_review\n",
        encoding="utf-8",
    )
    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
    app = create_app(worker=worker)

    with TestClient(app) as client:
        response = client.post(
            "/api/fetch-record",
            json={
                "system": "csv-export",
                "connector_profile": {
                    "csv_path": str(csv_path),
                    "id_column": "case_id",
                },
                "case_input": {
                    "case_id": "refund-001",
                    "workflow_name": "Refund approvals",
                },
            },
        )

        payload = response.json()
        assert response.status_code == 200
        assert payload["ok"] is True
        assert payload["record"]["bridge_system"] == "csv-export"
        assert payload["case"]["preview_only"] is True
        assert payload["case"]["source_trust_state"]["code"] == "source-not-proven"

        workspace_state = client.get("/api/workspace/state").json()
        assert workspace_state["ok"] is True
        assert len(workspace_state["cases"]) == 1


def test_gateway_case_workflow_patch_comments_and_filters(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
    app = create_app(worker=worker)

    with TestClient(app) as client:
        worker.store_items(
            [
                {
                    "kind": "policy.check",
                    "content": {"allowed": False, "rule_id": "R002"},
                    "meta": {"decision_id": "decision-2", "trace_id": "trace-2", "workflow_name": "Claims review"},
                }
            ]
        )

        deadline = time.time() + 2.0
        cases = []
        while time.time() < deadline:
            cases = client.get("/api/cases").json()["cases"]
            if cases:
                break
            time.sleep(0.05)
        assert cases
        case_id = cases[0]["id"]

        patched = client.patch(
            f"/api/cases/{case_id}",
            json={
                "status": "assigned",
                "assignee": "reviewer@epilabs.org",
                "due_at": "2026-03-20",
                "updated_by": "lead@epilabs.org",
                "reason": "Daily triage",
            },
        ).json()
        assert patched["ok"] is True
        assert patched["case"]["status"] == "assigned"
        assert patched["case"]["assignee"] == "reviewer@epilabs.org"
        assert patched["case"]["due_at"] == "2026-03-20"

        status_only = client.patch(
            f"/api/cases/{case_id}",
            json={
                "status": "in_review",
                "updated_by": "reviewer@epilabs.org",
                "reason": "Started review",
            },
        ).json()
        assert status_only["ok"] is True
        assert status_only["case"]["status"] == "in_review"
        assert status_only["case"]["assignee"] == "reviewer@epilabs.org"
        assert status_only["case"]["due_at"] == "2026-03-20"

        commented = client.post(
            f"/api/cases/{case_id}/comments",
            json={"author": "reviewer@epilabs.org", "body": "Waiting on claim documents."},
        ).json()
        assert commented["ok"] is True
        assert len(commented["case"]["comments"]) == 1

        comments = client.get(f"/api/cases/{case_id}/comments").json()
        assert comments["ok"] is True
        assert comments["comments"][0]["author"] == "reviewer@epilabs.org"

        filtered = client.get(
            "/api/cases",
            params={"status": "in_review", "assignee": "reviewer@epilabs.org", "overdue": "true"},
        ).json()
        assert filtered["ok"] is True
        assert len(filtered["cases"]) == 1
        assert filtered["cases"][0]["is_overdue"] is True

        detail = client.get(f"/api/cases/{case_id}").json()
        assert detail["ok"] is True
        assert len(detail["case"]["comments"]) == 1
        activity_kinds = [item["kind"] for item in detail["case"]["activity"]]
        assert "assignment_changed" in activity_kinds
        assert "status_changed" in activity_kinds
        assert "due_date_changed" in activity_kinds
        assert "comment_added" in activity_kinds


def test_gateway_ready_and_auth_protect_shared_case_api(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
    settings = GatewayRuntimeSettings(access_token="shared-secret")
    app = create_app(worker=worker, settings=settings)

    with TestClient(app) as client:
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["ok"] is True
        assert ready.json()["auth_required"] is True

        unauthorized = client.get("/api/cases")
        assert unauthorized.status_code == 401
        assert unauthorized.json()["ok"] is False

        authorized = client.get("/api/cases", headers={"Authorization": "Bearer shared-secret"})
        assert authorized.status_code == 200
        assert authorized.json()["ok"] is True


def test_gateway_auth_protects_capture_and_proxy_paths_when_enabled(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
    settings = GatewayRuntimeSettings(access_token="shared-secret")
    app = create_app(worker=worker, settings=settings)

    with TestClient(app) as client:
        capture_unauthorized = client.post(
            "/capture",
            json={"kind": "session.start", "content": {"workflow": "Claims review"}},
        )
        assert capture_unauthorized.status_code == 401

        proxy_unauthorized = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert proxy_unauthorized.status_code == 401

        capture_authorized = client.post(
            "/capture",
            json={"kind": "session.start", "content": {"workflow": "Claims review"}},
            headers={"Authorization": "Bearer shared-secret"},
        )
        assert capture_authorized.status_code == 202


def test_gateway_local_user_login_session_and_roles(tmp_path):
    users_path = tmp_path / "gateway-users.json"
    users_path.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "username": "reviewer@epilabs.org",
                        "password": "reviewer-pass",
                        "role": "reviewer",
                        "display_name": "Primary Reviewer",
                    },
                    {
                        "username": "auditor@epilabs.org",
                        "password": "auditor-pass",
                        "role": "auditor",
                        "display_name": "Audit Reviewer",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
    settings = GatewayRuntimeSettings(users_file=str(users_path))
    app = create_app(worker=worker, settings=settings)

    with TestClient(app) as client:
        ready = client.get("/ready").json()
        assert ready["auth_mode"] == "local-users"
        assert ready["local_user_auth_enabled"] is True
        assert ready["local_user_count"] == 2

        worker.store_items(
            [
                {
                    "kind": "policy.check",
                    "content": {"allowed": False, "rule_id": "R900"},
                    "meta": {"decision_id": "decision-auth", "workflow_name": "Refund approvals"},
                }
            ]
        )
        time.sleep(0.1)

        unauthorized = client.get("/api/cases")
        assert unauthorized.status_code == 401

        login = client.post(
            "/api/auth/login",
            json={"username": "reviewer@epilabs.org", "password": "reviewer-pass"},
        )
        assert login.status_code == 200
        login_payload = login.json()
        assert login_payload["ok"] is True
        assert login_payload["session"]["role"] == "reviewer"
        token = login_payload["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        session = client.get("/api/auth/session", headers=headers)
        assert session.status_code == 200
        assert session.json()["session"]["username"] == "reviewer@epilabs.org"

        cases = client.get("/api/cases", headers=headers).json()["cases"]
        assert len(cases) == 1
        case_id = cases[0]["id"]

        patched = client.patch(
            f"/api/cases/{case_id}",
            json={"status": "assigned", "assignee": "reviewer@epilabs.org"},
            headers=headers,
        )
        assert patched.status_code == 200
        assert patched.json()["case"]["assignee"] == "reviewer@epilabs.org"

        auditor_login = client.post(
            "/api/auth/login",
            json={"username": "auditor@epilabs.org", "password": "auditor-pass"},
        )
        auditor_token = auditor_login.json()["access_token"]
        auditor_headers = {"Authorization": f"Bearer {auditor_token}"}

        forbidden = client.patch(
            f"/api/cases/{case_id}",
            json={"status": "blocked"},
            headers=auditor_headers,
        )
        assert forbidden.status_code == 403

        auditor_export = client.post(f"/api/cases/{case_id}/export", headers=auditor_headers)
        assert auditor_export.status_code == 200

        logout = client.post("/api/auth/logout", headers=headers)
        assert logout.status_code == 200
        post_logout = client.get("/api/cases", headers=headers)
        assert post_logout.status_code == 401


def test_gateway_capture_llm_redacts_bodies_by_default(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
    settings = GatewayRuntimeSettings(retention_mode="redacted_hashes")
    app = create_app(worker=worker, settings=settings)

    with TestClient(app) as client:
        response = client.post(
            "/capture/llm",
            json={
                "provider": "openai-compatible",
                "request": {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "Approve refund REF-100 for $900"}],
                },
                "response": {
                    "model": "gpt-4o-mini",
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "Escalate the refund"},
                            "finish_reason": "stop",
                        }
                    ],
                },
                "meta": {"decision_id": "decision-redacted", "workflow_name": "Refund approvals"},
            },
        )
        assert response.status_code == 202

        deadline = time.time() + 2.0
        cases = []
        while time.time() < deadline:
            cases = client.get("/api/cases").json()["cases"]
            if cases:
                break
            time.sleep(0.05)
        assert cases
        case_id = cases[0]["id"]
        detail = None
        deadline = time.time() + 2.0
        while time.time() < deadline:
            detail = client.get(f"/api/cases/{case_id}").json()["case"]
            if len(detail.get("steps") or []) >= 3:
                break
            time.sleep(0.05)
        assert detail is not None
        request_step = next(step for step in detail["steps"] if step.get("kind") == "llm.request")
        response_step = next(step for step in detail["steps"] if step.get("kind") == "llm.response")
        message_content = request_step["content"]["messages"][0]["content"]
        output_text = response_step["content"]["output_text"]

        assert message_content.startswith("[redacted sha256=")
        assert output_text.startswith("[redacted sha256=")


def test_gateway_proxy_fail_open_returns_upstream_response_when_capture_fails(monkeypatch, tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
    settings = GatewayRuntimeSettings(proxy_failure_mode="fail-open")
    app = create_app(worker=worker, settings=settings)

    class _ProxyResult:
        status_code = 200
        body = {"id": "resp_1", "choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        headers = {"content-type": "application/json"}

    capture_request = {
        "provider": "openai-compatible",
        "request": {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]},
        "response": {"model": "gpt-4o-mini", "choices": [{"message": {"role": "assistant", "content": "ok"}}]},
    }

    monkeypatch.setattr("epi_gateway.main.relay_openai_chat_completions", lambda payload, headers: (_ProxyResult(), capture_request))
    monkeypatch.setattr("epi_gateway.main._enqueue_llm_capture", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk full")))

    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]})

    assert response.status_code == 200
    assert response.headers["x-epi-capture-status"] == "failed-open"
    assert response.json()["id"] == "resp_1"


def test_gateway_proxy_fail_closed_blocks_upstream_response_when_capture_fails(monkeypatch, tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
    settings = GatewayRuntimeSettings(proxy_failure_mode="fail-closed")
    app = create_app(worker=worker, settings=settings)

    class _ProxyResult:
        status_code = 200
        body = {"id": "resp_1", "choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        headers = {"content-type": "application/json"}

    capture_request = {
        "provider": "openai-compatible",
        "request": {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]},
        "response": {"model": "gpt-4o-mini", "choices": [{"message": {"role": "assistant", "content": "ok"}}]},
    }

    monkeypatch.setattr("epi_gateway.main.relay_openai_chat_completions", lambda payload, headers: (_ProxyResult(), capture_request))
    monkeypatch.setattr("epi_gateway.main._enqueue_llm_capture", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk full")))

    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]})

    assert response.status_code == 502
    assert response.headers["x-epi-capture-status"] == "failed-closed"
    assert "could not persist the capture" in response.json()["detail"].lower()
