from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from tests.helpers.artifacts import make_decision_epi


pytestmark = pytest.mark.browser
runner = CliRunner()


def _with_page(config):  # type: ignore[no-untyped-def]
    playwright = pytest.importorskip("playwright.sync_api")
    headless = bool(config.getoption("--headless", default=True))
    manager = playwright.sync_playwright()
    started = manager.__enter__()
    try:
        try:
            browser = started.chromium.launch(headless=headless)
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed or cannot launch: {exc}")
        return manager, browser, browser.new_page()
    except Exception:
        manager.__exit__(None, None, None)
        raise


def test_viewer_loads_offline_and_shows_decision_evidence_policy_and_trust(
    tmp_path: Path,
    request,
):
    artifact, _ = make_decision_epi(tmp_path, signed=True)
    extract_dir = tmp_path / "viewer"
    result = runner.invoke(cli_app, ["view", str(artifact), "--extract", str(extract_dir)])
    assert result.exit_code == 0, result.output

    manager, browser, page = _with_page(request.config)
    external_requests: list[str] = []
    page.on(
        "request",
        lambda req: external_requests.append(req.url)
        if req.url.startswith(("http://", "https://"))
        else None,
    )
    try:
        page.goto((extract_dir / "viewer.html").as_uri(), wait_until="load")
        body = page.locator("body").inner_text(timeout=5000)
    finally:
        browser.close()
        manager.__exit__(None, None, None)

    # Use case-insensitive check to handle CSS text-transform (uppercase) in the viewer.
    body_lower = body.lower()
    assert "evidence packaged infrastructure" in body_lower
    assert "execution timeline" in body_lower
    assert "evidence" in body_lower
    assert "policy" in body_lower
    assert "review" in body_lower
    assert "cryptographic proof" in body_lower
    assert external_requests == []


def test_printable_decision_record_html_loads_in_browser(tmp_path: Path, request):
    artifact, _ = make_decision_epi(tmp_path, signed=True)
    summary_path = tmp_path / "decision-record.html"
    result = runner.invoke(
        cli_app,
        ["export-summary", "summary", str(artifact), "--out", str(summary_path)],
    )
    assert result.exit_code == 0, result.output

    manager, browser, page = _with_page(request.config)
    try:
        page.goto(summary_path.as_uri(), wait_until="load")
        body = page.locator("body").inner_text(timeout=5000)
    finally:
        browser.close()
        manager.__exit__(None, None, None)

    assert "EPI Decision Record".lower() in body.lower()
    assert "Policy Compliance Summary".lower() in body.lower()
    assert "Cryptographic Proof and Verification".lower() in body.lower()
