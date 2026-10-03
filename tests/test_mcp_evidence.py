"""Tests for the EPI evidence MCP package (seal/verify/export)."""

from __future__ import annotations

import pytest

from epi_mcp import export_summary, seal_record, verify_artifact


@pytest.fixture
def isolated_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    return tmp_path


def _events():
    return [
        {"kind": "user.task", "content": {"text": "Refund order ORD-9001?"}},
        {"kind": "tool.call", "content": {"tool": "lookup_order", "input": {"order": "ORD-9001"}}},
        {"kind": "agent.decision", "content": {"decision": "escalate"}},
    ]


def test_seal_then_verify_round_trip(isolated_keys, tmp_path):
    sealed = seal_record(_events(), goal="test refund", output_path=tmp_path / "r.epi")
    assert sealed["steps_sealed"] == 3
    assert sealed["scope"] == "caller-provided"

    report = verify_artifact(sealed["epi_path"])
    assert report["integrity_ok"] is True
    assert report["signature_valid"] is True


def test_seal_rejects_empty(isolated_keys):
    with pytest.raises(ValueError):
        seal_record([])


def test_seal_rejects_non_object_event(isolated_keys, tmp_path):
    with pytest.raises(ValueError):
        seal_record(["not-an-object"], output_path=tmp_path / "x.epi")


def test_export_summary_reads_timeline(isolated_keys, tmp_path):
    sealed = seal_record(_events(), output_path=tmp_path / "r.epi")
    summary = export_summary(sealed["epi_path"])
    assert summary["steps_total"] == 3
    assert [s["kind"] for s in summary["timeline"]] == ["user.task", "tool.call", "agent.decision"]


def test_verify_missing_file():
    with pytest.raises(FileNotFoundError):
        verify_artifact("does-not-exist.epi")


def test_server_tools_registered():
    pytest.importorskip("mcp.server.mcpserver")
    import epi_mcp.server as srv

    registered = {fn.__name__ for fn in (srv.epi_seal_record, srv.epi_verify, srv.epi_export_summary)}
    assert registered == {"epi_seal_record", "epi_verify", "epi_export_summary"}
