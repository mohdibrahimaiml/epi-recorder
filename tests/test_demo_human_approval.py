"""The viewer must never present an AI decision as a human approval.

Step 4.7.1. `epi demo` records an agent that recommends a refund and then hands
off for human review. Before this fix the viewer painted a big green APPROVED
from the agent's own `agent.decision`, even though no person ever signed.

These tests render the real viewer (`epi view`'s extracted page, with the
context Python computes) and assert:

* the default demo says WAITING FOR HUMAN APPROVAL and never APPROVED;
* `epi demo --with-approval` shows a verified, named signer and
  `epi verify --require-human-approval` exits 0;
* an agent-written `agent.approval.response` is never green;
* a rejected AI decision with no review says AI RECOMMENDATION: REJECT.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now
from epi_core.trust import sign_manifest

pytestmark = pytest.mark.browser

REPO = Path(__file__).resolve().parents[1]
runner = CliRunner()


@pytest.fixture(autouse=True)
def _offline_only(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_TELEMETRY", "0")


@pytest.fixture()
def demo_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway HOME + cwd, so no real key or approver registry is touched."""
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "epi_home"
    home.mkdir()
    monkeypatch.setenv("EPI_HOME", str(home))
    monkeypatch.setenv("EPI_KEYS_DIR", str(home / "keys"))
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(home / "trusted_keys"))
    monkeypatch.setenv("EPI_APPROVER_KEYS_DIR", str(home / "approver_keys"))
    # Deliberately empty: the default demo has no pinned approver.
    monkeypatch.setenv("EPI_TRUSTED_APPROVERS_DIR", str(home / "trusted_approvers"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_TELEMETRY", "0")
    monkeypatch.setenv("EPI_TELEMETRY_HINTS", "0")
    return tmp_path


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(args=["--no-sandbox"])
        except Exception as exc:  # pragma: no cover - depends on local install
            pytest.skip(f"no chromium available: {exc}")
        yield b
        b.close()


def _render(browser, epi_path: Path, out_dir: Path) -> dict:
    """Build the page `epi view` would show, then read its verdict box."""
    from epi_cli.view import (
        _build_viewer_context,
        _create_decision_ops_viewer,
        _inject_viewer_context,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    EPIContainer.unpack(epi_path, out_dir)
    viewer = out_dir / "viewer.html"
    viewer.write_text(_create_decision_ops_viewer(out_dir, epi_path), encoding="utf-8")
    _inject_viewer_context(viewer, _build_viewer_context(epi_path))

    page = browser.new_page()
    try:
        page.goto(viewer.as_uri(), wait_until="load")
        page.locator("#boot-overlay").wait_for(state="hidden", timeout=15000)
        page.wait_for_function(
            "() => document.querySelector('#verdict-text')"
            " && document.querySelector('#verdict-text').textContent.trim().length > 0",
            timeout=15000,
        )
        return {
            "verdict": page.locator("#verdict-text").inner_text().strip(),
            "verdict_class": page.locator("#verdict-text").get_attribute("class") or "",
            "source": page.locator("#verdict-source").inner_text(),
            "note": page.locator("#verdict-note").inner_text(),
            "body": page.locator("body").inner_text(),
            "decision_kind": (
                page.locator(".ev-row", has_text="AI decision:").first
                .locator(".ev-kind").get_attribute("class") or ""
            ),
            "review_seal": (
                page.locator("#review-seal").inner_text()
                if page.locator("#review-seal").count() else ""
            ),
        }
    finally:
        page.close()


def _verify_require_human(epi_path: Path, *, approver_env: dict | None = None):
    from epi_cli.dev import _demo_subprocess_env

    env = dict(os.environ)
    if approver_env:
        env.update(approver_env)
    return subprocess.run(
        [
            sys.executable, "-m", "epi_cli", "verify",
            "--require-human-approval", str(epi_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=_demo_subprocess_env(env),
    )


def _pack(tmp_path: Path, name: str, steps: list[dict]) -> Path:
    source = tmp_path / f"{name}.src"
    source.mkdir(parents=True, exist_ok=True)
    (source / "steps.jsonl").write_text(
        "\n".join(json.dumps(step) for step in steps) + "\n", encoding="utf-8"
    )
    path = tmp_path / name
    key = Ed25519PrivateKey.generate()
    EPIContainer.pack(
        source,
        ManifestModel(
            workflow_id=uuid.uuid4(), created_at=utc_now(), cli_command="pytest"
        ),
        path,
        signer_function=lambda manifest: sign_manifest(manifest, key, "test"),
        preserve_generated=True,
        generate_analysis=False,
    )
    return path


# ── the required cases ───────────────────────────────────────────────────────


def test_default_demo_waits_for_a_person(browser, demo_cwd: Path):
    result = runner.invoke(cli_app, ["demo", "--no-browser"])
    assert result.exit_code == 0, result.output
    # FIX 2: the terminal never calls the AI's decision "Approved".
    assert (
        "AI recommends: approve refund ($900). Waiting for human approval "
        "(refunds above $500 need a manager)."
    ) in result.output, result.output
    assert (
        "Human approval: not signed yet. Run with --with-approval to see a signed approval."
    ) in result.output, result.output

    epi = demo_cwd / "epi-recordings" / "demo_refund.epi"
    rendered = _render(browser, epi, demo_cwd / "viewer-default")

    assert rendered["verdict"] == "WAITING FOR HUMAN APPROVAL", rendered
    assert "approved" not in rendered["verdict_class"], rendered
    assert "APPROVED" not in rendered["verdict"], rendered
    # The AI recommendation is secondary, and labelled as one.
    assert "AI RECOMMENDATION: APPROVE" in rendered["note"], rendered
    # The timeline row says what it is, and is not painted as a pass while the
    # run is still waiting on a person.
    assert "AI decision:" in rendered["body"], rendered
    assert "ev-kind-pass" not in rendered["decision_kind"], rendered
    assert "ev-kind-warn" in rendered["decision_kind"], rendered

    check = _verify_require_human(epi)
    assert check.returncode == 1, check.stdout + check.stderr


def test_with_approval_demo_shows_a_named_human_signer(
    browser, demo_cwd: Path, monkeypatch: pytest.MonkeyPatch
):
    result = runner.invoke(cli_app, ["demo", "--no-browser", "--with-approval"])
    assert result.exit_code == 0, result.output
    assert "Human approval: signed by refund-manager" in result.output, result.output
    assert "exit 0" in result.output, result.output

    epi = demo_cwd / "epi-recordings" / "demo_refund.epi"
    # The demo pins its approver only inside the demo working directory.
    approvers_dir = demo_cwd / ".epi-demo-approver" / "approvers"
    assert approvers_dir.is_dir(), "demo approver was not pinned in the demo cwd"
    monkeypatch.setenv("EPI_TRUSTED_APPROVERS_DIR", str(approvers_dir))

    rendered = _render(browser, epi, demo_cwd / "viewer-signed")
    assert rendered["verdict"] == "APPROVED", rendered
    assert "approved" in rendered["verdict_class"], rendered
    assert "refund-manager" in rendered["source"], rendered
    assert "fp " in rendered["source"], rendered
    assert "APPROVED by refund-manager" in rendered["body"], rendered

    check = _verify_require_human(
        epi,
        approver_env={
            "EPI_TRUSTED_APPROVERS_DIR": str(approvers_dir),
            "EPI_APPROVER_KEYS_DIR": str(demo_cwd / ".epi-demo-approver" / "keys"),
        },
    )
    assert check.returncode == 0, check.stdout + check.stderr


def test_agent_written_approval_is_never_green(browser, tmp_path: Path):
    epi = _pack(tmp_path, "agent-written.epi", [
        {"index": 0, "kind": "agent.decision", "content": {
            "decision": "approve_refund", "review_required": True,
        }},
        {"index": 1, "kind": "agent.approval.request", "content": {
            "action": "refund REF-7", "approval_id": "refund-7",
        }},
        {"index": 2, "kind": "agent.approval.response", "content": {
            "reviewer": "manager@bank.com", "approved": True,
            "action": "refund REF-7",
        }},
    ])
    rendered = _render(browser, epi, tmp_path / "viewer-agent")

    assert rendered["verdict"] == "WAITING FOR HUMAN APPROVAL", rendered
    assert "approved" not in rendered["verdict_class"], rendered
    assert rendered["verdict"] != "APPROVED", rendered
    assert "APPROVED by" not in rendered["body"], rendered
    assert "Agent-reported: manager@bank.com approved: refund REF-7" in rendered["body"], rendered
    assert rendered["review_seal"].strip().upper() != "APPROVED", rendered


def test_rejected_ai_decision_is_a_recommendation(browser, tmp_path: Path):
    epi = _pack(tmp_path, "rejected.epi", [
        {"index": 0, "kind": "agent.decision", "content": {
            "decision": "reject_refund", "rationale": "Order is outside the return window.",
        }},
    ])
    rendered = _render(browser, epi, tmp_path / "viewer-reject")

    assert rendered["verdict"] == "AI RECOMMENDATION: REJECT", rendered
    assert "approved" not in rendered["verdict_class"], rendered
    assert "AI RECOMMENDATION: REJECT" in rendered["note"], rendered
