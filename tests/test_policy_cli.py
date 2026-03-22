import json
import os
import shutil
import uuid
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import click

from epi_cli.policy import init, show


def _tmp_workspace() -> Path:
    root = Path(__file__).resolve().parent.parent / ".tmp-policy-cli-tests"
    root.mkdir(exist_ok=True)
    path = root / f"workspace-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def test_policy_init_guided_profile_creates_policy_with_profile_id():
    tmpdir = _tmp_workspace()
    original = os.getcwd()
    try:
        os.chdir(tmpdir)
        with patch("epi_cli.policy.console", MagicMock()), \
             patch(
                 "epi_cli.policy.Prompt.ask",
                 side_effect=[
                     "finance-approval",
                     "loan-review-agent",
                     "1.0",
                     "10000",
                 ],
             ), \
             patch("epi_cli.policy.Confirm.ask", side_effect=[True, True, True, True]):
            init(output="epi_policy.json")
    finally:
        os.chdir(original)

    data = json.loads((tmpdir / "epi_policy.json").read_text(encoding="utf-8"))
    assert data["profile_id"] == "finance.loan-underwriting"
    assert any(rule["id"] == "R003" for rule in data["rules"])
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_policy_init_yes_defaults_to_profile():
    tmpdir = _tmp_workspace()
    original = os.getcwd()
    try:
        os.chdir(tmpdir)
        with patch("epi_cli.policy.console", MagicMock()):
            init(output="epi_policy.json", yes=True)
    finally:
        os.chdir(original)

    data = json.loads((tmpdir / "epi_policy.json").read_text(encoding="utf-8"))
    assert data["profile_id"] == "finance.loan-underwriting"
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_policy_show_prints_summary_without_raw_json_by_default():
    tmpdir = _tmp_workspace()
    policy_path = tmpdir / "epi_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "system_name": "refund-agent",
                "system_version": "1.0",
                "policy_version": "2026-03-18",
                "profile_id": "finance.refund-agent",
                "rules": [
                    {
                        "id": "R001",
                        "name": "Verify Identity Before Refund",
                        "severity": "critical",
                        "description": "Identity verification must happen before any refund.",
                        "type": "sequence_guard",
                        "required_before": "refund",
                        "must_call": "verify_identity",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    mock_console = MagicMock()
    with patch("epi_cli.policy.console", mock_console):
        show(policy_file=str(policy_path), raw=False)

    printed = "\n".join(str(call.args[0]) for call in mock_console.print.call_args_list if call.args)
    assert "refund-agent" in printed
    assert "Raw Policy JSON" not in printed
    assert any("refund-agent" in str(call.args[0]) for call in mock_console.print.call_args_list if call.args)
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_policy_show_raw_prints_json_after_summary():
    tmpdir = _tmp_workspace()
    policy_path = tmpdir / "epi_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "system_name": "refund-agent",
                "system_version": "1.0",
                "policy_version": "2026-03-18",
                "rules": [],
            }
        ),
        encoding="utf-8",
    )

    mock_console = MagicMock()
    with patch("epi_cli.policy.console", mock_console):
        show(policy_file=str(policy_path), raw=True)

    assert any(call.args and hasattr(call.args[0], "code") for call in mock_console.print.call_args_list)
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_policy_show_reads_embedded_policy_from_epi_artifact():
    tmpdir = _tmp_workspace()
    artifact_path = tmpdir / "review_case.epi"
    policy_payload = {
        "system_name": "refund-agent",
        "system_version": "1.0",
        "policy_version": "2026-03-22",
        "profile_id": "finance.refund-agent",
        "rules": [
            {
                "id": "R002",
                "name": "Verify Identity Before Refund",
                "severity": "critical",
                "description": "Identity verification must happen before any refund.",
                "type": "sequence_guard",
                "required_before": "refund",
                "must_call": "verify_identity",
            }
        ],
    }
    with zipfile.ZipFile(artifact_path, "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip")
        zf.writestr("policy.json", json.dumps(policy_payload))

    mock_console = MagicMock()
    with patch("epi_cli.policy.console", mock_console):
        show(policy_file=str(artifact_path), raw=False)

    printed = "\n".join(str(call.args[0]) for call in mock_console.print.call_args_list if call.args)
    assert "refund-agent" in printed
    assert "embedded policy" in printed
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_policy_show_missing_embedded_policy_exits_1():
    tmpdir = _tmp_workspace()
    artifact_path = tmpdir / "no_policy.epi"
    with zipfile.ZipFile(artifact_path, "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip")
        zf.writestr("manifest.json", "{}")

    code = None
    try:
        with patch("epi_cli.policy.console", MagicMock()):
            show(policy_file=str(artifact_path), raw=False)
        code = 0
    except (SystemExit, click.exceptions.Exit) as exc:
        code = getattr(exc, "code", getattr(exc, "exit_code", 1))

    assert code == 1
    shutil.rmtree(tmpdir, ignore_errors=True)
