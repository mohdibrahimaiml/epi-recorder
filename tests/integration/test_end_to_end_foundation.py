from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_core.container import EPIContainer
from epi_core.trust import verify_embedded_manifest_signature
from epi_gateway.main import GatewayRuntimeSettings, create_app
from epi_gateway.worker import EvidenceWorker
from epi_recorder.integrations.agt import export_agt_to_epi
from tests.helpers.artifacts import make_decision_epi


pytestmark = pytest.mark.integration
runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]


def _share_settings(tmp_path: Path) -> GatewayRuntimeSettings:
    return GatewayRuntimeSettings(
        storage_dir=str(tmp_path),
        share_enabled=True,
        share_ip_hmac_secret="test-share-secret",
        share_site_base_url="http://127.0.0.1:9999",
        share_api_base_url="http://127.0.0.1:9999",
        share_rate_limit_per_hour=100,
    )


def test_artifact_full_flow_capture_verify_view_export_share_download_offline(tmp_path: Path):
    artifact, _ = make_decision_epi(tmp_path, name="full-flow.epi", signed=True)
    extract_dir = tmp_path / "viewer"
    summary_path = tmp_path / "decision-record.html"

    verify = runner.invoke(cli_app, ["verify", "--json", str(artifact)])
    view = runner.invoke(cli_app, ["view", str(artifact), "--extract", str(extract_dir)])
    export = runner.invoke(
        cli_app,
        ["export-summary", "summary", str(artifact), "--out", str(summary_path)],
    )

    assert verify.exit_code == 0, verify.output
    assert json.loads(verify.stdout)["integrity_ok"] is True
    assert view.exit_code == 0, view.output
    assert export.exit_code == 0, export.output
    assert (extract_dir / "viewer.html").exists()
    assert "EPI Decision Record" in summary_path.read_text(encoding="utf-8")

    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    gateway = create_app(worker=worker, settings=_share_settings(tmp_path / "share"))
    with TestClient(gateway) as client:
        share_response = client.post(
            "/api/share",
            content=artifact.read_bytes(),
            headers={"Content-Type": "application/vnd.epi+zip", "X-EPI-Filename": artifact.name},
        )
        assert share_response.status_code == 201, share_response.text
        share_id = share_response.json()["id"]

        download = client.get(f"/api/share/{share_id}")
        assert download.status_code == 200

    downloaded = tmp_path / "downloaded.epi"
    downloaded.write_bytes(download.content)
    integrity_ok, mismatches = EPIContainer.verify_integrity(downloaded)
    signature_valid, signer, _ = verify_embedded_manifest_signature(
        EPIContainer.read_manifest(downloaded)
    )

    assert integrity_ok is True
    assert mismatches == {}
    assert signature_valid is True
    assert signer == "test"


def test_pytest_epi_keeps_failed_artifact_and_only_keeps_passed_with_flag(tmp_path: Path):
    test_file = tmp_path / "test_agent_regression.py"
    test_file.write_text(
        "def test_agent_failure():\n"
        "    assert False, 'agent regression'\n\n"
        "def test_agent_passes():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    evidence_dir = tmp_path / "evidence"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["EPI_HOME"] = str(tmp_path / "epi-home")
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

    failed_run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "pytest_epi.plugin",
            str(test_file),
            "--epi",
            "--epi-no-sign",
            f"--epi-dir={evidence_dir}",
            "-q",
            "-o",
            "addopts=",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert failed_run.returncode == 1, failed_run.stdout + failed_run.stderr
    kept = sorted(evidence_dir.glob("*.epi"))
    assert len(kept) == 1
    assert "test_agent_failure" in kept[0].name
    assert EPIContainer.count_steps(kept[0]) >= 2

    passing_file = tmp_path / "test_agent_pass_only.py"
    passing_file.write_text("def test_agent_pass_only():\n    assert True\n", encoding="utf-8")
    pass_evidence_dir = tmp_path / "pass-evidence"
    pass_run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "pytest_epi.plugin",
            str(passing_file),
            "--epi",
            "--epi-no-sign",
            "--epi-on-pass",
            f"--epi-dir={pass_evidence_dir}",
            "-q",
            "-o",
            "addopts=",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert pass_run.returncode == 0, pass_run.stdout + pass_run.stderr
    assert len(list(pass_evidence_dir.glob("*.epi"))) == 1


def test_governance_workflow_policy_violation_review_and_export(tmp_path: Path):
    artifact, _ = make_decision_epi(tmp_path, name="governance.epi", signed=True)

    policy_eval = EPIContainer.read_member_json(artifact, "policy_evaluation.json")
    review = EPIContainer.read_member_json(artifact, "review.json")
    summary_path = tmp_path / "governance-summary.html"
    result = runner.invoke(
        cli_app,
        ["export-summary", "summary", str(artifact), "--out", str(summary_path)],
    )

    assert policy_eval["artifact_review_required"] is True
    assert policy_eval["controls_failed"] == 1
    assert review["reviewed_by"] == "qa@example.com"
    assert result.exit_code == 0, result.output
    html = summary_path.read_text(encoding="utf-8")
    assert "Policy Compliance Summary" in html
    assert "Human reviewer approved" in html


def test_agt_to_epi_to_regulator_round_trip(tmp_path: Path):
    fixture = REPO_ROOT / "tests" / "fixtures" / "agt" / "combined_clean.json"
    output = tmp_path / "agt-case.epi"
    export_agt_to_epi(json.loads(fixture.read_text(encoding="utf-8")), output)

    verify = runner.invoke(cli_app, ["verify", "--json", str(output)])
    view = runner.invoke(cli_app, ["view", str(output), "--extract", str(tmp_path / "agt-view")])

    assert verify.exit_code == 0, verify.output
    assert json.loads(verify.stdout)["integrity_ok"] is True
    assert view.exit_code == 0, view.output
    assert "artifacts/agt/bundle.json" in EPIContainer.list_members(output)
    assert "artifacts/agt/mapping_report.json" in EPIContainer.list_members(output)


def test_share_link_expiry_returns_gone(tmp_path: Path):
    artifact, _ = make_decision_epi(tmp_path, name="expiry.epi", signed=True)
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    gateway = create_app(worker=worker, settings=_share_settings(tmp_path / "share"))

    with TestClient(gateway) as client:
        response = client.post(
            "/api/share",
            content=artifact.read_bytes(),
            headers={"Content-Type": "application/vnd.epi+zip"},
        )
        assert response.status_code == 201, response.text
        share_id = response.json()["id"]

        db_path = gateway.state.share_service.metadata_store.db_path
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE shares SET expires_at = ?, deleted_at = NULL WHERE share_id = ?",
                ("2000-01-01T00:00:00Z", share_id),
            )
            connection.commit()

        assert client.get(f"/api/share/{share_id}/meta").status_code == 410
        assert client.get(f"/api/share/{share_id}").status_code == 410
