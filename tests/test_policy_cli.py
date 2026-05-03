import json
import os
import shutil
import uuid
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
from epi_core import __version__ as core_version

from epi_cli.policy import _create_policy_editor_html, init, show, validate


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


def test_policy_init_custom_starter_rules_use_shared_templates():
    tmpdir = _tmp_workspace()
    original = os.getcwd()
    try:
        os.chdir(tmpdir)
        with patch("epi_cli.policy.console", MagicMock()):
            init(
                output="epi_policy.json",
                starter_rule=["approval_guard", "tool_permission_guard"],
                yes=True,
            )
    finally:
        os.chdir(original)

    data = json.loads((tmpdir / "epi_policy.json").read_text(encoding="utf-8"))
    assert data["profile_id"] == "custom.guided"
    assert [rule["type"] for rule in data["rules"]] == ["approval_guard", "tool_permission_guard"]
    assert data["rules"][0]["approved_by"] == "manager"
    assert data["rules"][1]["allowed_tools"] == ["lookup_order", "verify_identity"]
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_policy_init_insurance_claim_profile_has_expected_rules():
    tmpdir = _tmp_workspace()
    original = os.getcwd()
    try:
        os.chdir(tmpdir)
        with patch("epi_cli.policy.console", MagicMock()):
            init(output="epi_policy.json", profile="insurance.claim-denial", yes=True)
    finally:
        os.chdir(original)

    data = json.loads((tmpdir / "epi_policy.json").read_text(encoding="utf-8"))
    assert data["profile_id"] == "insurance.claim-denial"
    rule_names = {rule["name"] for rule in data["rules"]}
    assert "Run Fraud Check Before Claim Denial" in rule_names
    assert "Check Coverage Before Claim Denial" in rule_names
    assert "High-Value Claims Require Human Approval" in rule_names
    assert "Record Denial Reason Before Claim Denial" in rule_names
    assert "Never Output PII In Claim Notices" in rule_names
    threshold_rule = next(rule for rule in data["rules"] if rule["id"] == "R003")
    assert threshold_rule["threshold_field"] == "amount"
    assert threshold_rule["watch_for"] == ["amount", "claim_amount"]
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_policy_init_guided_insurance_claim_can_customize_threshold():
    tmpdir = _tmp_workspace()
    original = os.getcwd()
    try:
        os.chdir(tmpdir)
        with patch("epi_cli.policy.console", MagicMock()), \
             patch(
                 "epi_cli.policy.Prompt.ask",
                 side_effect=[
                     "insurance-claim",
                     "claim-denial-agent",
                     "1.0",
                     "1250",
                 ],
             ), \
             patch("epi_cli.policy.Confirm.ask", side_effect=[True, True, True, True]):
            init(output="epi_policy.json")
    finally:
        os.chdir(original)

    data = json.loads((tmpdir / "epi_policy.json").read_text(encoding="utf-8"))
    threshold_rule = next(rule for rule in data["rules"] if rule["id"] == "R003")
    assert data["profile_id"] == "insurance.claim-denial"
    assert threshold_rule["threshold_value"] == 1250.0
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_policy_editor_html_preloads_rules_workspace():
    tmpdir = _tmp_workspace()
    policy_path = tmpdir / "epi_policy.json"
    policy_payload = {
        "policy_format_version": "2.0",
        "policy_id": "refund-agent-prod",
        "system_name": "refund-agent",
        "system_version": "1.0",
        "policy_version": "2026-03-26",
        "scope": {"workflow": "refund-approval"},
        "rules": [
            {
                "id": "R001",
                "name": "Require approval",
                "severity": "critical",
                "description": "Require approval for large refunds.",
                "type": "approval_guard",
                "action": "approve_refund",
                "approved_by": "manager",
            }
        ],
    }
    policy_path.write_text(json.dumps(policy_payload), encoding="utf-8")

    html = _create_policy_editor_html(policy_payload, policy_path)

    assert 'id="epi-preloaded-cases"' in html
    assert '"view": "rules"' in html
    assert "EPI Forensic Artifact Viewer" in html
    assert 'id="document-root"' in html
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_policy_init_open_editor_writes_browser_workspace():
    tmpdir = _tmp_workspace()
    editor_dir = tmpdir / "editor-session"
    editor_dir.mkdir(exist_ok=True)
    original = os.getcwd()
    try:
        os.chdir(tmpdir)
        with patch("epi_cli.policy.console", MagicMock()), \
             patch("epi_cli.policy._make_temp_dir", return_value=editor_dir), \
             patch("epi_cli.policy._open_in_browser") as open_browser, \
             patch("epi_cli.policy._cleanup_after_delay") as cleanup_after_delay:
            init(
                output="epi_policy.json",
                starter_rule=["approval_guard"],
                yes=True,
                open_editor=True,
            )
    finally:
        os.chdir(original)

    viewer_path = editor_dir / "policy_editor.html"
    html = viewer_path.read_text(encoding="utf-8")
    assert viewer_path.exists()
    assert '"view": "rules"' in html
    assert "epi-preloaded-cases" in html
    assert "approval_guard" in html
    open_browser.assert_called_once_with(viewer_path)
    cleanup_after_delay.assert_called_once_with(editor_dir, 30.0)
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


def test_policy_show_open_editor_writes_browser_workspace():
    tmpdir = _tmp_workspace()
    editor_dir = tmpdir / "editor-session"
    editor_dir.mkdir(exist_ok=True)
    policy_path = tmpdir / "epi_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "policy_format_version": "2.0",
                "policy_id": "refund-agent-prod",
                "system_name": "refund-agent",
                "system_version": "1.0",
                "policy_version": "2026-03-26",
                "rules": [
                    {
                        "id": "R001",
                        "name": "Require approval",
                        "severity": "critical",
                        "description": "Require approval for large refunds.",
                        "type": "approval_guard",
                        "action": "approve_refund",
                        "approved_by": "manager",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with patch("epi_cli.policy.console", MagicMock()), \
         patch("epi_cli.policy._make_temp_dir", return_value=editor_dir), \
         patch("epi_cli.policy._open_in_browser") as open_browser, \
         patch("epi_cli.policy._cleanup_after_delay") as cleanup_after_delay:
        show(policy_file=str(policy_path), raw=False, open_editor=True)

    viewer_path = editor_dir / "policy_editor.html"
    html = viewer_path.read_text(encoding="utf-8")
    assert viewer_path.exists()
    assert '"view": "rules"' in html
    assert "epi-preloaded-cases" in html
    assert "refund-agent-prod" in html
    open_browser.assert_called_once_with(viewer_path)
    cleanup_after_delay.assert_called_once_with(editor_dir, 30.0)
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


def test_policy_validate_reads_embedded_policy_from_epi_artifact():
    tmpdir = _tmp_workspace()
    artifact_path = tmpdir / "policy_case.epi"
    policy_payload = {
        "policy_format_version": "2.0",
        "policy_id": "finance-refunds-prod",
        "system_name": "refund-agent",
        "system_version": core_version,
        "policy_version": "2026-03-24",
        "scope": {"environment": "prod"},
        "rules": [],
    }
    with zipfile.ZipFile(artifact_path, "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip")
        zf.writestr("policy.json", json.dumps(policy_payload))

    mock_console = MagicMock()
    with patch("epi_cli.policy.console", mock_console):
        validate(policy_file=str(artifact_path))

    printed = "\n".join(str(call.args[0]) for call in mock_console.print.call_args_list if call.args)
    assert "Valid policy" in printed
    assert "embedded policy" in printed
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_policy_validate_reports_json_line_and_column():
    tmpdir = _tmp_workspace()
    policy_path = tmpdir / "broken_policy.json"
    policy_path.write_text('{"system_name": "refund-agent",\n', encoding="utf-8")

    mock_console = MagicMock()
    code = None
    try:
        with patch("epi_cli.policy.console", mock_console):
            validate(policy_file=str(policy_path))
        code = 0
    except (SystemExit, click.exceptions.Exit) as exc:
        code = getattr(exc, "code", getattr(exc, "exit_code", 1))

    printed = "\n".join(str(call.args[0]) for call in mock_console.print.call_args_list if call.args)
    assert code == 1
    assert "Invalid JSON" in printed
    assert "Could not parse policy file" in printed
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_policy_validate_reports_schema_field_errors():
    tmpdir = _tmp_workspace()
    policy_path = tmpdir / "invalid_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "system_name": "refund-agent",
                "system_version": core_version,
                "policy_version": "2026-03-24",
                "rules": [
                    {
                        "id": "R001",
                        "name": "Missing severity",
                        "description": "Broken rule",
                        "type": "sequence_guard",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    mock_console = MagicMock()
    code = None
    try:
        with patch("epi_cli.policy.console", mock_console):
            validate(policy_file=str(policy_path))
        code = 0
    except (SystemExit, click.exceptions.Exit) as exc:
        code = getattr(exc, "code", getattr(exc, "exit_code", 1))

    printed = "\n".join(str(call.args[0]) for call in mock_console.print.call_args_list if call.args)
    assert code == 1
    assert "Policy schema is invalid" in printed
    assert "Validation Errors" in printed
    shutil.rmtree(tmpdir, ignore_errors=True)
