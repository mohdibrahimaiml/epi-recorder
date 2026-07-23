"""Workflow display title should not stay 'untitled' when goal/path exist."""

from pathlib import Path

from epi_recorder.api import EpiRecorderSession, _resolve_workflow_display_name


def test_resolve_prefers_goal_over_untitled():
    assert (
        _resolve_workflow_display_name("untitled", goal="Real LLM refund ORD-9001")
        == "Real LLM refund ORD-9001"
    )


def test_resolve_prefers_path_stem():
    name = _resolve_workflow_display_name(None, output_path="real_llm_refund_case.epi")
    assert "real llm refund case" == name.lower()


def test_session_uses_goal_as_workflow_name(tmp_path: Path):
    out = tmp_path / "case.epi"
    session = EpiRecorderSession(
        out,
        workflow_name=None,
        goal="Approve refund ORD-9001 via live LLM",
        auto_sign=False,
    )
    assert session.workflow_name == "Approve refund ORD-9001 via live LLM"


def test_viewer_js_has_resolve_display_title():
    js = Path("web_viewer/app.js").read_text(encoding="utf-8")
    assert "function resolveDisplayTitle" in js
    assert "untitled" in js  # placeholder filter
    assert "function resolveVerifyFileName" in js
