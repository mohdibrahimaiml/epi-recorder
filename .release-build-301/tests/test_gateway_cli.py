import re

from typer.testing import CliRunner

from epi_cli.main import app


runner = CliRunner()


def _plain(output: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", output)


def test_gateway_help_mentions_shared_backend():
    result = runner.invoke(app, ["gateway", "serve", "--help"])
    output = _plain(result.output)

    assert result.exit_code == 0
    assert "--storage-dir" in output
    assert "--batch-timeout" in output
    assert "--retention-mode" in output
    assert "--proxy-failure-mode" in output
    assert "--users-file" in output


def test_gateway_serve_runs_uvicorn_with_shared_case_store(monkeypatch, tmp_path):
    recorded = {}

    def _fake_run(target, host, port, reload):  # noqa: ANN001 - monkeypatch stub
        recorded["target"] = target
        recorded["host"] = host
        recorded["port"] = port
        recorded["reload"] = reload

    monkeypatch.setattr("uvicorn.run", _fake_run)

    result = runner.invoke(
        app,
        [
            "gateway",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            "9901",
            "--storage-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "Starting EPI Gateway" in result.output
    assert "Cases API" in result.output
    assert "Retention:" in result.output
    assert "Failure mode:" in result.output
    assert recorded == {
        "target": "epi_gateway.main:app",
        "host": "127.0.0.1",
        "port": 9901,
        "reload": False,
    }


def test_gateway_export_writes_epi_artifact(tmp_path):
    storage_dir = tmp_path / "storage"
    output_path = tmp_path / "case.epi"

    from epi_gateway.worker import EvidenceWorker

    worker = EvidenceWorker(storage_dir=storage_dir, batch_size=1, batch_timeout=0.1)
    case_id = worker.store_items(
        [
            {
                "kind": "llm.request",
                "content": {"messages": [{"role": "user", "content": "Approve refund"}]},
                "meta": {"decision_id": "decision-export", "workflow_name": "Refund approvals"},
            },
            {
                "kind": "llm.response",
                "content": {"output_text": "Escalate for review"},
                "meta": {"decision_id": "decision-export", "workflow_name": "Refund approvals"},
            },
        ]
    )[0]

    result = runner.invoke(
        app,
        [
            "gateway",
            "export",
            "--case-id",
            case_id,
            "--out",
            str(output_path),
            "--storage-dir",
            str(storage_dir),
        ],
    )

    assert result.exit_code == 0
    assert output_path.exists() is True
    assert "Exported" in result.output
