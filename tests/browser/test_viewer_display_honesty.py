"""Adversarial (browser): the viewer must not paint a verdict it cannot support.

The double-click experience opens the polyglot ``.epi`` itself. That page
carries a pack-time *copy* of the manifest and of the sealed members. The
archive's ``manifest.json`` is re-signed after the viewer is generated, so the
baked copy is a different, stale pre-image — and it is editable by whoever
holds the file.

Re-hashing the baked members against the baked ``file_manifest`` is therefore
self-consistent by construction. Before this fix the viewer reported
"INTEGRITY VERIFIED" and "SIGNATURE VALID" from exactly that check, so a
forged file painted green in the one place a human is most likely to look.

A verdict is only meaningful when it is bound to the signed manifest:

* ``epi view`` injects a context built from the CLI's own verification of the
  file on disk — that IS authoritative, and an intact file shows green.
* A double-clicked polyglot file has no such context — it must show a
  neutral "not verified here", never green and never red.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_core.container import (
    EPI_ENVELOPE_HEADER_SIZE,
    EPI_ZIP_MARKER,
)
from tests.helpers.artifacts import make_decision_epi

pytestmark = pytest.mark.browser

runner = CliRunner()

_POLYGLOT_PREFIX = b" -->\n"


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


def _extract_polyglot_viewer_html(epi_path: Path, out_path: Path) -> Path:
    """Write the outer double-click HTML of an envelope artifact to a file."""
    data = epi_path.read_bytes()
    marker_idx = data.find(EPI_ZIP_MARKER)
    assert marker_idx > EPI_ENVELOPE_HEADER_SIZE, "expected an envelope-v2 polyglot region"
    region = data[EPI_ENVELOPE_HEADER_SIZE:marker_idx]
    html = region[len(_POLYGLOT_PREFIX):] if region.startswith(_POLYGLOT_PREFIX) else region
    out_path.write_bytes(html)
    return out_path


def _pill_texts(page) -> list[str]:
    page.locator("#boot-overlay").wait_for(state="hidden", timeout=15000)
    return page.locator("#header-pills").inner_text(timeout=5000)


def test_polyglot_viewer_does_not_paint_green_without_authority(
    tmp_path: Path, request
):
    """A double-clicked .epi carries no signed manifest bytes -> no green."""
    from epi_core.container import EPI_CONTAINER_FORMAT_ENVELOPE

    artifact, _key = make_decision_epi(
        tmp_path, container_format=EPI_CONTAINER_FORMAT_ENVELOPE
    )
    viewer_html = _extract_polyglot_viewer_html(
        artifact, tmp_path / "polyglot_viewer.html"
    )

    manager, browser, page = _with_page(request.config)
    try:
        page.goto(viewer_html.as_uri(), wait_until="load")
        pills = _pill_texts(page)
        integrity_indicator = page.locator("#ind-integrity").inner_text(timeout=5000)
        signature_indicator = page.locator("#ind-signature").inner_text(timeout=5000)
    finally:
        browser.close()
        manager.__exit__(None, None, None)

    normalized = " ".join(pills.upper().split())

    # The file itself is intact — but this page cannot prove it.
    assert "INTEGRITY VERIFIED" not in normalized, (
        f"polyglot viewer must not claim integrity it cannot prove: {normalized!r}"
    )
    assert "INTEGRITY NOT VERIFIED HERE" in normalized, (
        f"polyglot viewer should say it cannot verify here: {normalized!r}"
    )
    assert integrity_indicator.strip().upper().startswith("NOT VERIFIED HERE"), integrity_indicator
    assert signature_indicator.strip().upper() != "VALID", signature_indicator


def test_host_injected_viewer_still_shows_green_for_intact_file(
    tmp_path: Path, request
):
    """`epi view` injects an authoritative context -> an intact file is green."""
    artifact, _key = make_decision_epi(tmp_path, signed=True)
    extract_dir = tmp_path / "viewer"
    result = runner.invoke(
        cli_app, ["view", str(artifact), "--extract", str(extract_dir)]
    )
    assert result.exit_code == 0, result.output

    manager, browser, page = _with_page(request.config)
    try:
        page.goto((extract_dir / "viewer.html").as_uri(), wait_until="load")
        pills = _pill_texts(page)
    finally:
        browser.close()
        manager.__exit__(None, None, None)

    normalized = " ".join(pills.upper().split())
    assert "INTEGRITY VERIFIED" in normalized, normalized


def test_exported_html_still_shows_green_for_intact_file(tmp_path: Path, request):
    """`epi export-html` embeds the archive -> the page holds the signed
    manifest bytes -> an intact file is green."""
    artifact, _key = make_decision_epi(tmp_path, signed=True)
    out_html = tmp_path / "shared_case.html"
    result = runner.invoke(
        cli_app, ["export-html", str(artifact), "--output", str(out_html)]
    )
    assert result.exit_code == 0, result.output
    assert out_html.exists()

    manager, browser, page = _with_page(request.config)
    try:
        page.goto(out_html.as_uri(), wait_until="load")
        pills = _pill_texts(page)
    finally:
        browser.close()
        manager.__exit__(None, None, None)

    normalized = " ".join(pills.upper().split())
    assert "INTEGRITY VERIFIED" in normalized, normalized
