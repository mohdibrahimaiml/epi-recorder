"""The homepage shows three real decision records, and the copy matches them.

The cards in the hero are hand-written markup; the artifacts they describe are
sealed and shipped. If either drifts, the page is advertising records that do
not say what the page says they say.
"""

from __future__ import annotations

import pathlib

import pytest

from epi_core.container import EPIContainer

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = REPO / "website" / "index.html"
EXAMPLE_DIR = REPO / "website" / "assets" / "demo"

# file, badge word, whether the record carries a human approval
VARIANTS = [
    ("decision-example.epi", "DENIED", True),
    ("decision-example-approved.epi", "APPROVED", True),
    ("decision-example-escalated.epi", "ESCALATED", True),
]


def _example(name: str) -> pathlib.Path:
    return EXAMPLE_DIR / name


def _steps(path: pathlib.Path) -> list[dict]:
    return EPIContainer.read_steps(path)


def _decision(path: pathlib.Path) -> dict:
    return [step for step in _steps(path) if step["kind"] == "agent.decision"][-1]["content"]


def _llm_response(path: pathlib.Path) -> dict:
    return [step for step in _steps(path) if step["kind"] == "llm.response"][-1]["content"]


def test_the_examples_are_shipped_everywhere_they_are_linked():
    for name, _badge, _approval in VARIANTS:
        example = _example(name)
        assert example.is_file(), f"the hero links to {name}, which is not in the repo"
        for mirror in ("site", "epi-official", "verify_portal/static"):
            copied = REPO / mirror / "assets" / "demo" / name
            assert copied.is_file(), f"{mirror} would 404 on /assets/demo/{name}"


def test_the_hero_cards_match_the_sealed_records():
    html = HOME.read_text(encoding="utf-8")
    assert "When your customer asks why your AI made a decision" in html
    assert "hand them a file they can check" in html
    assert "EPI records what your agent saw" in html

    for name, badge, _approval in VARIANTS:
        example = _example(name)
        manifest = EPIContainer.read_manifest(example)
        decision = _decision(example)
        served = _llm_response(example).get("served_model")

        assert str(manifest.goal) in html, f"the card must name the real case in {name}"
        assert str(decision["rationale"]) in html, f"the card must show the real reason in {name}"
        assert str(decision["basis"]["policy"]) in html, f"the card must show the rule in {name}"
        assert served and served in html, f"the card must show the served model in {name}"
        assert f"/assets/demo/{name}" in html, f"the card must link to {name}"
        assert badge in html, f"the card must label {name} as {badge}"


def test_the_three_outcomes_are_offered_as_tabs():
    html = HOME.read_text(encoding="utf-8")
    assert 'role="tablist"' in html
    for label in ("Denied", "Approved", "Escalated"):
        assert f">{label}</button>" in html, f"missing tab: {label}"
    for panel in ("panel-denied", "panel-approved", "panel-escalated"):
        assert f'id="{panel}"' in html, f"missing panel: {panel}"
    assert "/js/decision-tabs.js" in html, "the tabs need their script"


def test_the_rotation_advances_and_can_be_paused():
    """Three seconds per outcome, and an off switch the visitor controls."""
    html = HOME.read_text(encoding="utf-8")
    js = (REPO / "website" / "js" / "decision-tabs.js").read_text(encoding="utf-8")
    assert "AUTO_MS = 3000" in js
    assert "setInterval" in js
    assert "prefers-reduced-motion" in js, "motion-sensitive visitors must not be animated"
    assert "visibilitychange" in js, "a hidden tab must not keep rotating"
    assert 'id="decisionPause"' in html
    assert 'aria-label="Pause the example rotation"' in html
    assert "Pause" in html and "Play" in js


def test_the_approver_on_each_card_is_the_signed_one():
    from epi_core.review import verify_human_approvals

    html = HOME.read_text(encoding="utf-8")
    for name, _badge, must_have_approval in VARIANTS:
        example = _example(name)
        state = verify_human_approvals(example)
        approvals = state.get("approvals") or []
        if must_have_approval:
            assert approvals, f"{name} must carry a signed approval"
            approver = str(approvals[-1].get("approver_name") or "")
            assert approver
            assert approver.split("(")[0].strip().upper().startswith("DEMO KEY")
    assert "DEMO KEY" in html


def test_the_page_does_not_call_a_demo_approval_a_real_person():
    html = HOME.read_text(encoding="utf-8")
    assert "DEMO KEY" in html
    assert "Claims Adjuster" in html
    # The card must not present the demo signature as a named real approver.
    assert "not a real person" in html or "DEMO KEY" in html
