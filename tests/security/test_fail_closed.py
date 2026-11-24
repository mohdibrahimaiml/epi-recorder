"""Fail-closed regression tests for verification error handling (risk T3)."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import typer
from typer.testing import CliRunner

import epi_core.trust as trust_mod
from epi_cli.main import app
from epi_cli.verify import _fail_closed, verify_command
from epi_core.container import _bake_signature_status
from epi_core.trust import TrustRegistry
from tests.helpers.artifacts import make_decision_epi

KEY = "ab" * 32


def test_fail_closed_overrides_pass():
    report = {"decision": {"status": "PASS", "reason": "Integrity verified"}}
    _fail_closed(report, "boom")
    assert report["decision"]["status"] == "FAIL"
    assert "boom" in report["decision"]["reason"]


def test_fail_closed_repairs_missing_decision():
    for report in ({}, {"decision": None}, {"decision": "PASS"}):
        _fail_closed(report, "boom")
        assert report["decision"]["status"] == "FAIL"


def _registry(tmp_path):
    (tmp_path / "vendor.pub").write_text(KEY)
    (tmp_path / "vendor.revoked").mkdir()  # exists but cannot be read as a file
    return TrustRegistry(trusted_keys_dir=tmp_path)


def test_unreadable_revocation_blocks_trust(tmp_path):
    trusted, _name, _detail, source = _registry(tmp_path).verify_key_trust_with_source(KEY)
    assert trusted is False
    assert source == "revoked"


def test_unreadable_revocation_blocks_local_pin(tmp_path):
    assert _registry(tmp_path)._is_locally_pinned(KEY) is False


def test_bake_signature_error_is_invalid_not_unsigned(monkeypatch):
    def _raise(_manifest):
        raise RuntimeError("cannot check")

    monkeypatch.setattr(trust_mod, "verify_embedded_manifest_signature", _raise)
    assert _bake_signature_status(SimpleNamespace(signature="sig")) is False


def test_bake_signature_absent_is_none():
    assert _bake_signature_status(SimpleNamespace(signature=None)) is None


def _unpinned_signed_epi(tmp_path, monkeypatch, name: str):
    """A valid seal whose signer is not pinned: standard policy returns WARN."""
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    artifact, _key = make_decision_epi(tmp_path, signed=True, name=name)
    return artifact


def test_warn_exits_zero_unless_fail_on_warn(tmp_path, monkeypatch):
    artifact = _unpinned_signed_epi(tmp_path, monkeypatch, "warn.epi")
    runner = CliRunner()

    plain = runner.invoke(app, ["verify", "--json", str(artifact)])
    assert plain.exit_code == 0, plain.output
    report = json.loads(plain.stdout)
    assert report["decision"]["status"] == "WARN"
    # The human note must not be appended to JSON stdout.
    json.loads(plain.output)

    human = runner.invoke(app, ["verify", str(artifact)])
    assert human.exit_code == 0, human.output
    note = (human.stderr or "") + (human.output or "")
    assert "exit code is 0" in note

    flagged = runner.invoke(app, ["verify", "--json", "--fail-on-warn", str(artifact)])
    assert flagged.exit_code == 1, flagged.output
    flagged_report = json.loads(flagged.stdout)
    assert flagged_report["decision"]["status"] == "WARN"


def test_direct_call_does_not_treat_fail_on_warn_as_enabled(tmp_path, monkeypatch):
    artifact = _unpinned_signed_epi(tmp_path, monkeypatch, "direct.epi")
    try:
        verify_command(ctx=MagicMock(), epi_file=artifact)
    except typer.Exit as exc:
        assert exc.exit_code in (0, None)
        return
    # A normal return is exit 0.
