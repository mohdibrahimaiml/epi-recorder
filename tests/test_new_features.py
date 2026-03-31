"""
Tests for the 6 new EPI features and reliability upgrades.

Features covered:
  1. epi gateway add-user / list-users
  2. Webhook on needs_review
  3. epi gateway backup
  4. epi gateway export-all
  5. epi export-summary (text + HTML)
  6. epi verify --report
  + Rate limiting
  + Brute-force login protection
  + Webhook retry
  + Schema versioning
"""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_gateway.main import GatewayRuntimeSettings, _LoginThrottle, _SlidingWindowRateLimiter, create_app
from epi_gateway.worker import EvidenceWorker

runner = CliRunner()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_worker(tmp_path: Path) -> EvidenceWorker:
    return EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)


def _seed_case(worker: EvidenceWorker) -> str:
    """Insert one LLM event pair and return the case_id."""
    ids = worker.store_items(
        [
            {
                "kind": "llm.request",
                "content": {"messages": [{"role": "user", "content": "Approve this refund?"}]},
                "meta": {
                    "decision_id": "dec-test-001",
                    "trace_id": "trace-test-001",
                    "workflow_name": "Refund Approval",
                },
            },
            {
                "kind": "llm.response",
                "content": {"output_text": "Approved."},
                "meta": {
                    "decision_id": "dec-test-001",
                    "trace_id": "trace-test-001",
                    "workflow_name": "Refund Approval",
                },
            },
        ]
    )
    return ids[0]


# ──────────────────────────────────────────────────────────────────────────────
# Feature 1: add-user / list-users
# ──────────────────────────────────────────────────────────────────────────────

class TestAddUser:
    def test_add_user_creates_user_in_db(self, tmp_path):
        result = runner.invoke(
            cli_app,
            [
                "gateway", "add-user", "alice",
                "--role", "reviewer",
                "--password", "s3cr3t!",
                "--storage-dir", str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "alice" in result.output
        assert "reviewer" in result.output

        worker = _make_worker(tmp_path)
        users = worker.list_auth_users()
        assert any(u["username"] == "alice" for u in users)

    def test_add_user_rejects_invalid_role(self, tmp_path):
        result = runner.invoke(
            cli_app,
            [
                "gateway", "add-user", "bob",
                "--role", "superuser",
                "--password", "pw",
                "--storage-dir", str(tmp_path),
            ],
        )
        assert result.exit_code != 0
        assert "superuser" in result.output or "role" in result.output.lower()

    def test_add_user_default_role_is_reviewer(self, tmp_path):
        result = runner.invoke(
            cli_app,
            [
                "gateway", "add-user", "carol",
                "--password", "pw123",
                "--storage-dir", str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        worker = _make_worker(tmp_path)
        users = worker.list_auth_users()
        carol = next(u for u in users if u["username"] == "carol")
        assert carol["role"] == "reviewer"

    def test_add_user_admin_role(self, tmp_path):
        result = runner.invoke(
            cli_app,
            [
                "gateway", "add-user", "dave",
                "--role", "admin",
                "--password", "pw123",
                "--storage-dir", str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        worker = _make_worker(tmp_path)
        users = worker.list_auth_users()
        dave = next(u for u in users if u["username"] == "dave")
        assert dave["role"] == "admin"


class TestListUsers:
    def test_list_users_shows_table(self, tmp_path):
        worker = _make_worker(tmp_path)
        from epi_core.auth_local import hash_password
        worker.sync_auth_users(
            [{"username": "eve", "password_hash": hash_password("pw"), "role": "auditor", "display_name": "Eve"}],
            source="test",
        )
        result = runner.invoke(
            cli_app,
            ["gateway", "list-users", "--storage-dir", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "eve" in result.output
        assert "auditor" in result.output

    def test_list_users_empty(self, tmp_path):
        result = runner.invoke(
            cli_app,
            ["gateway", "list-users", "--storage-dir", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "No users" in result.output

    def test_list_users_multiple(self, tmp_path):
        from epi_core.auth_local import hash_password
        worker = _make_worker(tmp_path)
        worker.sync_auth_users(
            [
                {"username": "alice", "password_hash": hash_password("pw"), "role": "reviewer", "display_name": "alice"},
                {"username": "bob", "password_hash": hash_password("pw"), "role": "admin", "display_name": "bob"},
                {"username": "carol", "password_hash": hash_password("pw"), "role": "auditor", "display_name": "carol"},
            ],
            source="test",
        )
        result = runner.invoke(
            cli_app,
            ["gateway", "list-users", "--storage-dir", str(tmp_path)],
        )
        assert "alice" in result.output
        assert "bob" in result.output
        assert "carol" in result.output


# ──────────────────────────────────────────────────────────────────────────────
# Feature 2: Webhook on needs_review
# ──────────────────────────────────────────────────────────────────────────────

class TestWebhook:
    def _make_app(self, tmp_path: Path, webhook_url: str):
        worker = _make_worker(tmp_path)
        settings = GatewayRuntimeSettings(
            storage_dir=str(tmp_path),
            webhook_url=webhook_url,
            capture_rate_limit=0,
        )
        return create_app(worker=worker, settings=settings), worker

    def _make_review_required_case(self, worker: EvidenceWorker) -> str:
        """Create a case that results in 'unassigned' (review_required=True)."""
        case_id = _seed_case(worker)
        # Push a workspace case with analysis.review_required so status becomes "unassigned"
        worker.upsert_case_payload({
            "case_id": case_id,
            "title": "Refund needs review",
            "analysis": {"review_required": True},
        })
        return case_id

    def test_webhook_fired_when_case_needs_review(self, tmp_path):
        fired = []

        def fake_fire(url, payload):
            fired.append((url, payload))

        app, worker = self._make_app(tmp_path, "http://webhook.test/hook")
        case_id = self._make_review_required_case(worker)

        with TestClient(app) as client:
            with patch("epi_gateway.main._fire_webhook", side_effect=fake_fire):
                resp = client.post(
                    "/api/workspace/cases",
                    json={"case": {
                        "case_id": case_id,
                        "title": "Test case",
                        "analysis": {"review_required": True},
                    }},
                )
        assert resp.status_code == 200
        assert len(fired) == 1
        url, payload = fired[0]
        assert url == "http://webhook.test/hook"
        assert payload["event"] == "case.needs_review"

    def test_webhook_not_fired_for_other_statuses(self, tmp_path):
        fired = []

        def fake_fire(url, payload):
            fired.append(payload)

        app, worker = self._make_app(tmp_path, "http://webhook.test/hook")
        case_id = _seed_case(worker)

        with TestClient(app) as client:
            with patch("epi_gateway.main._fire_webhook", side_effect=fake_fire):
                # Upsert without review_required → status "resolved" → no webhook
                client.post(
                    "/api/workspace/cases",
                    json={"case": {"case_id": case_id, "title": "Test"}},
                )
        assert len(fired) == 0

    def test_webhook_not_fired_when_no_url_configured(self, tmp_path):
        fired = []

        def fake_fire(url, payload):
            fired.append(payload)

        worker = _make_worker(tmp_path)
        settings = GatewayRuntimeSettings(storage_dir=str(tmp_path), capture_rate_limit=0)
        app = create_app(worker=worker, settings=settings)
        case_id = self._make_review_required_case(worker)

        with TestClient(app) as client:
            with patch("epi_gateway.main._fire_webhook", side_effect=fake_fire):
                client.post(
                    "/api/workspace/cases",
                    json={"case": {"case_id": case_id, "title": "Test", "analysis": {"review_required": True}}},
                )
        assert len(fired) == 0

    def test_webhook_payload_has_required_fields(self, tmp_path):
        captured = []

        def fake_fire(url, payload):
            captured.append(payload)

        app, worker = self._make_app(tmp_path, "http://example.com/hook")
        case_id = self._make_review_required_case(worker)

        with TestClient(app) as client:
            with patch("epi_gateway.main._fire_webhook", side_effect=fake_fire):
                client.post(
                    "/api/workspace/cases",
                    json={"case": {"case_id": case_id, "title": "Refund case", "analysis": {"review_required": True}}},
                )

        assert captured
        p = captured[0]
        assert "event" in p
        assert "case_id" in p
        assert "created_at" in p
        assert "gateway_url" in p


# ──────────────────────────────────────────────────────────────────────────────
# Feature 3: backup
# ──────────────────────────────────────────────────────────────────────────────

class TestBackup:
    def test_backup_creates_zip(self, tmp_path):
        storage = tmp_path / "vault"
        _seed_case(_make_worker(storage))
        out = tmp_path / "backup.zip"

        result = runner.invoke(
            cli_app,
            ["gateway", "backup", "--out", str(out), "--storage-dir", str(storage)],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert zipfile.is_zipfile(out)

    def test_backup_contains_database(self, tmp_path):
        storage = tmp_path / "vault"
        _seed_case(_make_worker(storage))
        out = tmp_path / "backup.zip"

        runner.invoke(cli_app, ["gateway", "backup", "--out", str(out), "--storage-dir", str(storage)])

        with zipfile.ZipFile(out, "r") as zf:
            names = set(zf.namelist())
        assert "cases.sqlite3" in names

    def test_backup_contains_events(self, tmp_path):
        storage = tmp_path / "vault"
        _seed_case(_make_worker(storage))
        out = tmp_path / "backup.zip"

        runner.invoke(cli_app, ["gateway", "backup", "--out", str(out), "--storage-dir", str(storage)])

        with zipfile.ZipFile(out, "r") as zf:
            names = zf.namelist()
        event_files = [n for n in names if n.startswith("events/")]
        assert len(event_files) > 0

    def test_backup_prints_size_and_restore_hint(self, tmp_path):
        storage = tmp_path / "vault"
        _seed_case(_make_worker(storage))
        out = tmp_path / "backup.zip"

        result = runner.invoke(
            cli_app,
            ["gateway", "backup", "--out", str(out), "--storage-dir", str(storage)],
        )
        assert "Backup written" in result.output
        assert "Restore" in result.output

    def test_backup_empty_vault(self, tmp_path):
        """Backup an empty vault — should succeed with just the DB."""
        storage = tmp_path / "vault"
        storage.mkdir(parents=True)
        out = tmp_path / "empty_backup.zip"

        result = runner.invoke(
            cli_app,
            ["gateway", "backup", "--out", str(out), "--storage-dir", str(storage)],
        )
        assert result.exit_code == 0
        assert out.exists()


# ──────────────────────────────────────────────────────────────────────────────
# Feature 4: export-all
# ──────────────────────────────────────────────────────────────────────────────

class TestExportAll:
    def test_export_all_creates_epi_per_case(self, tmp_path):
        storage = tmp_path / "vault"
        worker = _make_worker(storage)
        _seed_case(worker)
        out_dir = tmp_path / "exports"

        result = runner.invoke(
            cli_app,
            ["gateway", "export-all", "--out-dir", str(out_dir), "--storage-dir", str(storage)],
        )
        assert result.exit_code == 0, result.output
        assert "[FAIL]" not in result.output, f"Export failed:\n{result.output}"
        assert "Exporting" in result.output, f"No cases found:\n{result.output}"
        epi_files = list(out_dir.glob("*.epi"))
        assert len(epi_files) >= 1, f"No .epi files created. Output:\n{result.output}"

    def test_export_all_prints_progress(self, tmp_path):
        storage = tmp_path / "vault"
        _seed_case(_make_worker(storage))
        out_dir = tmp_path / "exports"

        result = runner.invoke(
            cli_app,
            ["gateway", "export-all", "--out-dir", str(out_dir), "--storage-dir", str(storage)],
        )
        assert "Exporting" in result.output
        assert "Exported" in result.output

    def test_export_all_no_cases(self, tmp_path):
        storage = tmp_path / "vault"
        storage.mkdir(parents=True)
        out_dir = tmp_path / "exports"

        result = runner.invoke(
            cli_app,
            ["gateway", "export-all", "--out-dir", str(out_dir), "--storage-dir", str(storage)],
        )
        assert result.exit_code == 0
        assert "No cases" in result.output

    def test_export_all_creates_output_dir(self, tmp_path):
        storage = tmp_path / "vault"
        _seed_case(_make_worker(storage))
        out_dir = tmp_path / "deep" / "nested" / "exports"

        runner.invoke(
            cli_app,
            ["gateway", "export-all", "--out-dir", str(out_dir), "--storage-dir", str(storage)],
        )
        assert out_dir.exists()

    def test_export_all_epi_files_are_valid_zips(self, tmp_path):
        storage = tmp_path / "vault"
        _seed_case(_make_worker(storage))
        out_dir = tmp_path / "exports"

        runner.invoke(
            cli_app,
            ["gateway", "export-all", "--out-dir", str(out_dir), "--storage-dir", str(storage)],
        )
        for epi_file in out_dir.glob("*.epi"):
            assert zipfile.is_zipfile(epi_file), f"{epi_file} is not a valid ZIP"


# ──────────────────────────────────────────────────────────────────────────────
# Feature 5: export-summary
# ──────────────────────────────────────────────────────────────────────────────

def _make_epi_file(tmp_path: Path) -> Path:
    """Export a real case to a .epi file and return its path."""
    storage = tmp_path / "vault"
    worker = _make_worker(storage)
    case_id = _seed_case(worker)
    out = tmp_path / "test_case.epi"
    worker.export_case(case_id, out, signer_function=None)
    return out


class TestExportSummary:
    def test_text_output_contains_headers(self, tmp_path):
        epi = _make_epi_file(tmp_path)
        result = runner.invoke(cli_app, ["export-summary", "summary", str(epi), "--text"])
        assert result.exit_code == 0, result.output
        assert "EPI DECISION RECORD" in result.output
        assert "CASE OVERVIEW" in result.output
        assert "POLICY COMPLIANCE" in result.output
        assert "CRYPTOGRAPHIC PROOF" in result.output

    def test_text_output_shows_workflow(self, tmp_path):
        epi = _make_epi_file(tmp_path)
        result = runner.invoke(cli_app, ["export-summary", "summary", str(epi), "--text"])
        assert result.exit_code == 0
        assert "Workflow:" in result.output

    def test_html_output_written_to_default_path(self, tmp_path):
        epi = _make_epi_file(tmp_path)
        result = runner.invoke(cli_app, ["export-summary", "summary", str(epi)])
        assert result.exit_code == 0, result.output
        expected = epi.parent / f"{epi.stem}_summary.html"
        assert expected.exists()

    def test_html_output_is_valid_html(self, tmp_path):
        epi = _make_epi_file(tmp_path)
        html_out = tmp_path / "report.html"
        result = runner.invoke(cli_app, ["export-summary", "summary", str(epi), "--out", str(html_out)])
        assert result.exit_code == 0
        content = html_out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "EPI Decision Record" in content

    def test_html_output_contains_text_content(self, tmp_path):
        epi = _make_epi_file(tmp_path)
        html_out = tmp_path / "report.html"
        runner.invoke(cli_app, ["export-summary", "summary", str(epi), "--out", str(html_out)])
        content = html_out.read_text(encoding="utf-8")
        assert "Policy Compliance Summary" in content
        assert "Cryptographic Proof and Verification" in content

    def test_missing_file_exits_nonzero(self, tmp_path):
        result = runner.invoke(cli_app, ["export-summary", "summary", "nonexistent.epi", "--text"])
        assert result.exit_code != 0


# ──────────────────────────────────────────────────────────────────────────────
# Feature 6: verify --report
# ──────────────────────────────────────────────────────────────────────────────

class TestVerifyReport:
    def test_report_written_when_flag_given(self, tmp_path):
        epi = _make_epi_file(tmp_path)
        report_path = tmp_path / "verification_report.txt"

        result = runner.invoke(
            cli_app,
            ["verify", str(epi), "--report", str(report_path)],
        )
        assert result.exit_code == 0, result.output
        assert report_path.exists()

    def test_report_contains_required_sections(self, tmp_path):
        epi = _make_epi_file(tmp_path)
        report_path = tmp_path / "report.txt"

        runner.invoke(cli_app, ["verify", str(epi), "--report", str(report_path)])
        content = report_path.read_text(encoding="utf-8")

        assert "EPI VERIFICATION REPORT" in content
        assert "RESULT:" in content
        assert "Integrity Check:" in content
        assert "Signature Check:" in content
        assert "ARTIFACT DETAILS" in content
        assert "Workflow:" in content
        assert "epi verify" in content

    def test_report_not_written_without_flag(self, tmp_path):
        epi = _make_epi_file(tmp_path)
        default_report = epi.parent / f"{epi.stem}_verification.txt"

        runner.invoke(cli_app, ["verify", str(epi)])
        # Without --report the file should NOT be auto-written
        assert not default_report.exists()

    def test_report_shows_in_cli_output(self, tmp_path):
        epi = _make_epi_file(tmp_path)
        report_path = tmp_path / "r.txt"

        result = runner.invoke(cli_app, ["verify", str(epi), "--report", str(report_path)])
        assert "Verification report written" in result.output

    def test_report_trust_level_present(self, tmp_path):
        epi = _make_epi_file(tmp_path)
        report_path = tmp_path / "r.txt"

        runner.invoke(cli_app, ["verify", str(epi), "--report", str(report_path)])
        content = report_path.read_text(encoding="utf-8")
        assert "Trust Level:" in content


# ──────────────────────────────────────────────────────────────────────────────
# Reliability: rate limiting
# ──────────────────────────────────────────────────────────────────────────────

class TestRateLimiting:
    def test_sliding_window_allows_under_limit(self):
        limiter = _SlidingWindowRateLimiter(max_requests=10, window_seconds=60.0)
        for _ in range(10):
            assert limiter.is_allowed("client-a") is True

    def test_sliding_window_blocks_over_limit(self):
        limiter = _SlidingWindowRateLimiter(max_requests=3, window_seconds=60.0)
        for _ in range(3):
            limiter.is_allowed("client-b")
        assert limiter.is_allowed("client-b") is False

    def test_sliding_window_per_key_independent(self):
        limiter = _SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
        limiter.is_allowed("a")
        limiter.is_allowed("a")
        # a is now at limit, b should still be allowed
        assert limiter.is_allowed("b") is True

    def test_rate_limit_returns_429(self, tmp_path):
        worker = _make_worker(tmp_path)
        settings = GatewayRuntimeSettings(
            storage_dir=str(tmp_path),
            capture_rate_limit=2,
        )
        app = create_app(worker=worker, settings=settings)

        with TestClient(app) as client:
            for _ in range(2):
                client.post("/capture", json={
                    "kind": "llm.request",
                    "content": {},
                    "meta": {"decision_id": "d1"},
                })
            response = client.post("/capture", json={
                "kind": "llm.request",
                "content": {},
                "meta": {"decision_id": "d1"},
            })
        assert response.status_code == 429

    def test_rate_limit_disabled_when_zero(self, tmp_path):
        worker = _make_worker(tmp_path)
        settings = GatewayRuntimeSettings(
            storage_dir=str(tmp_path),
            capture_rate_limit=0,
        )
        app = create_app(worker=worker, settings=settings)

        with TestClient(app) as client:
            for _ in range(20):
                r = client.post("/capture", json={
                    "kind": "llm.request",
                    "content": {},
                    "meta": {"decision_id": "d1"},
                })
                assert r.status_code != 429


# ──────────────────────────────────────────────────────────────────────────────
# Reliability: brute-force login protection
# ──────────────────────────────────────────────────────────────────────────────

class TestBruteForceProtection:
    def test_lockout_after_max_failures(self):
        throttle = _LoginThrottle()
        throttle.MAX_FAILURES = 3  # type: ignore[attr-defined]
        for _ in range(3):
            throttle.record_failure("user@test.com")
        assert throttle.is_locked_out("user@test.com") is True

    def test_no_lockout_under_max_failures(self):
        throttle = _LoginThrottle()
        for _ in range(_LoginThrottle.MAX_FAILURES - 1):
            throttle.record_failure("safe@test.com")
        assert throttle.is_locked_out("safe@test.com") is False

    def test_success_clears_failures(self):
        throttle = _LoginThrottle()
        for _ in range(4):
            throttle.record_failure("user2@test.com")
        throttle.record_success("user2@test.com")
        assert throttle.is_locked_out("user2@test.com") is False

    def test_api_returns_429_on_lockout(self, tmp_path):
        import json as _json
        from epi_core.auth_local import hash_password
        from epi_gateway.main import _load_gateway_users

        # Create a real users.json file so the lifespan can load it
        users_file = tmp_path / "users.json"
        users_file.write_text(
            _json.dumps([{"username": "target", "password": "correct", "role": "reviewer"}]),
            encoding="utf-8",
        )

        worker = _make_worker(tmp_path)
        settings = GatewayRuntimeSettings(
            storage_dir=str(tmp_path),
            users_file=str(users_file),
            capture_rate_limit=0,
        )
        app = create_app(worker=worker, settings=settings)

        from epi_gateway.main import _login_throttle
        # Saturate the throttle for "target"
        for _ in range(_LoginThrottle.MAX_FAILURES):
            _login_throttle.record_failure("target")

        try:
            with TestClient(app) as client:
                resp = client.post("/api/auth/login", json={"username": "target", "password": "correct"})
            assert resp.status_code == 429
        finally:
            _login_throttle.record_success("target")


# ──────────────────────────────────────────────────────────────────────────────
# Reliability: request body size limit
# ──────────────────────────────────────────────────────────────────────────────

class TestRequestSizeLimit:
    def test_oversized_request_returns_413(self, tmp_path):
        worker = _make_worker(tmp_path)
        settings = GatewayRuntimeSettings(
            storage_dir=str(tmp_path),
            max_request_body_bytes=2048,  # 2 KB limit
            capture_rate_limit=0,
        )
        app = create_app(worker=worker, settings=settings)
        # Payload larger than 2 KB
        big_payload = ("x" * 3000).encode()

        with TestClient(app) as client:
            resp = client.post(
                "/capture",
                content=big_payload,
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 413

    def test_normal_request_passes_size_check(self, tmp_path):
        worker = _make_worker(tmp_path)
        settings = GatewayRuntimeSettings(
            storage_dir=str(tmp_path),
            max_request_body_bytes=10 * 1024 * 1024,
            capture_rate_limit=0,
        )
        app = create_app(worker=worker, settings=settings)

        with TestClient(app) as client:
            resp = client.post("/capture", json={
                "kind": "llm.request",
                "content": {},
                "meta": {"decision_id": "d1"},
            })
        assert resp.status_code != 413


# ──────────────────────────────────────────────────────────────────────────────
# Reliability: webhook retry
# ──────────────────────────────────────────────────────────────────────────────

class TestWebhookRetry:
    def test_fire_webhook_retries_on_failure(self):
        from epi_gateway.main import _fire_webhook

        call_count = [0]

        def failing_urlopen(req, timeout):
            call_count[0] += 1
            if call_count[0] < 3:
                raise OSError("connection refused")
            # 3rd attempt succeeds (returns a mock)
            return MagicMock()

        with patch("urllib.request.urlopen", side_effect=failing_urlopen):
            with patch("time.sleep"):  # skip real sleeps in test
                _fire_webhook("http://example.com/hook", {"event": "test"})

        assert call_count[0] == 3

    def test_fire_webhook_logs_warning_on_all_failures(self):
        from epi_gateway.main import _fire_webhook

        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            with patch("time.sleep"):
                with patch("epi_gateway.main.logger") as mock_logger:
                    _fire_webhook("http://example.com/hook", {"event": "test"})

        assert mock_logger.warning.called


# ──────────────────────────────────────────────────────────────────────────────
# Reliability: schema versioning
# ──────────────────────────────────────────────────────────────────────────────

class TestSchemaVersioning:
    def test_schema_version_table_exists(self, tmp_path):
        import sqlite3
        worker = _make_worker(tmp_path)
        conn = sqlite3.connect(worker.db_path)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert "schema_version" in tables

    def test_schema_version_is_stamped(self, tmp_path):
        import sqlite3
        worker = _make_worker(tmp_path)
        conn = sqlite3.connect(worker.db_path)
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_version ORDER BY version")]
        conn.close()
        assert len(versions) >= 1
        assert versions[-1] == 3  # current version (3 = open_sessions migration)

    def test_schema_version_idempotent_on_second_init(self, tmp_path):
        """Opening the same DB twice should not duplicate schema_version rows."""
        import sqlite3
        from epi_core.case_store import CaseStore
        db_path = tmp_path / "cases.sqlite3"
        CaseStore(db_path)
        CaseStore(db_path)
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT version FROM schema_version WHERE version = 2").fetchall()
        conn.close()
        # Should be exactly one row for version 2
        assert len(rows) == 1
