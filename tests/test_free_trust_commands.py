"""The checker and the approver must not need a licence.

These commands are the customer side of the trust story: pin the approver's
key, sign the approval, read the customer's own record, and verify the
company's key history offline. They stay in the free, MIT core.
"""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from epi_cli.main import app
from epi_core.keys import key_fingerprint

GOLDEN = Path(__file__).resolve().parent / "goldens" / "spec-4.4.3.epi"


def _no_licence(monkeypatch):
    monkeypatch.delenv("EPI_LICENSE_FILE", raising=False)


def test_free_commands_are_present_without_a_licence(monkeypatch):
    _no_licence(monkeypatch)
    runner = CliRunner()
    for args in (
        ["approvers", "--help"],
        ["review", "--help"],
        ["oversight", "report", "--help"],
        ["org", "bundle", "verify", "--help"],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, (args, result.output)


def test_customer_can_pin_an_approver_key_for_free(monkeypatch, tmp_path):
    _no_licence(monkeypatch)
    monkeypatch.setenv("EPI_TRUSTED_APPROVERS_DIR", str(tmp_path / "approvers"))

    key = Ed25519PrivateKey.generate()
    public_hex = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    public_file = tmp_path / "alice.pub"
    public_file.write_text(public_hex, encoding="utf-8")
    fingerprint = key_fingerprint(public_hex)

    result = CliRunner().invoke(
        app,
        [
            "approvers",
            "add",
            str(public_file),
            "--name",
            "alice@bank.com",
            "--fingerprint",
            fingerprint,
        ],
    )
    assert result.exit_code == 0, result.output
    assert "alice@bank.com" in result.output


def test_customer_can_run_oversight_for_free(monkeypatch, tmp_path):
    _no_licence(monkeypatch)
    cases = tmp_path / "cases"
    cases.mkdir()
    result = CliRunner().invoke(
        app,
        ["oversight", "report", "--cases", str(cases), "--since", "2026-01-01"],
    )
    assert result.exit_code == 0, result.output


def test_approver_can_open_review_for_free(monkeypatch):
    _no_licence(monkeypatch)
    result = CliRunner().invoke(app, ["review", str(GOLDEN), "show"])
    assert result.exit_code == 0, result.output


def test_verify_keeps_the_free_human_approval_flag(monkeypatch):
    _no_licence(monkeypatch)
    result = CliRunner().invoke(app, ["verify", str(GOLDEN), "--require-human-approval"])
    assert "No such option" not in result.output
    assert result.exit_code in (0, 1), result.output
