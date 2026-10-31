"""The homepage shows a real decision record, and the copy matches the artifact.

The card in the hero is hand-written markup; the artifact it describes is sealed
and shipped. If either drifts, the page is advertising a record that does not
say what the page says it says.
"""

from __future__ import annotations

import pathlib

import pytest

from epi_core.container import EPIContainer

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = REPO / "website" / "index.html"
EXAMPLE = REPO / "website" / "assets" / "demo" / "decision-example.epi"


def _steps() -> list[dict]:
    return EPIContainer.read_steps(EXAMPLE)


def _decision() -> dict:
    return [step for step in _steps() if step["kind"] == "agent.decision"][-1]["content"]


def _llm_response() -> dict:
    return [step for step in _steps() if step["kind"] == "llm.response"][-1]["content"]


def test_the_example_artifact_is_shipped_everywhere_it_is_linked():
    assert EXAMPLE.is_file(), "the hero links to a file that is not in the repo"
    for mirror in ("site", "epi-official", "verify_portal/static"):
        copied = REPO / mirror / "assets" / "demo" / "decision-example.epi"
        assert copied.is_file(), f"{mirror} would 404 on the download link"


def test_the_hero_card_matches_the_sealed_record():
    html = HOME.read_text(encoding="utf-8")
    manifest = EPIContainer.read_manifest(EXAMPLE)
    decision = _decision()
    served = _llm_response().get("served_model")

    assert "When your customer asks why your AI made a decision" in html
    assert "hand them a file they can check" in html
    assert "EPI records what your agent saw" in html
    assert str(manifest.goal) in html, "the card must name the real case"
    assert str(decision["rationale"]) in html, "the card must show the real reason"
    assert str(decision["basis"]["policy"]) in html, "the card must show the rule relied on"
    assert served and served in html, "the card must show the served model"
    assert "/assets/demo/decision-example.epi" in html
    assert "/verify" in html


def test_the_approver_on_the_card_is_the_signed_one():
    from epi_core.review import verify_human_approvals

    state = verify_human_approvals(EXAMPLE)
    approvals = state.get("approvals") or []
    assert approvals, "the example must carry a signed approval"
    approver = str(approvals[-1].get("approver_name") or "")
    assert approver
    html = HOME.read_text(encoding="utf-8")
    # The card shortens the demo label; the fingerprint-free prefix must match.
    assert approver.split("(")[0].strip().upper().startswith("DEMO KEY")
    assert "DEMO KEY" in html
