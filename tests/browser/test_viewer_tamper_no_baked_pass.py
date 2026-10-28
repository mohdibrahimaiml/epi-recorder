"""A with-viewer .epi tampered after sealing must not render a computed PASS.

Double-clicking a `.epi` shows the embedded viewer over an editable display
copy, so it must never paint "0 mismatches" / "INTEGRITY VERIFIED" it did not
compute. It must instead say the file was not verified here.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser


def _launch(config):
    playwright = pytest.importorskip("playwright.sync_api")
    headless = bool(config.getoption("--headless", default=True))
    manager = playwright.sync_playwright()
    started = manager.__enter__()
    try:
        browser = started.chromium.launch(headless=headless)
    except Exception as exc:  # pragma: no cover - depends on local browser install
        manager.__exit__(None, None, None)
        pytest.skip(f"Playwright Chromium is not installed or cannot launch: {exc}")
    return manager, browser


def _sealed_with_viewer(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    from epi_mcp.records import seal_record

    result = seal_record(
        [
            {"kind": "user.message", "content": {"text": "Please review the clause."},
             "timestamp": "2026-10-05T10:00:00Z", "fidelity": "verbatim"},
            {"kind": "tool.call", "content": {"tool": "check", "input": {}},
             "timestamp": "2026-10-05T10:00:01Z"},
            {"kind": "tool.response", "content": {"result": "ok"},
             "timestamp": "2026-10-05T10:00:02Z"},
            {"kind": "agent.decision", "content": {"decision": "approve"},
             "timestamp": "2026-10-05T10:00:03Z"},
        ],
        goal="Tamper render regression",
    )
    return Path(result["epi_path"])


def _tampered_viewer_html(epi: Path, tmp_path: Path) -> str:
    """Rewrite the sealed steps, then regenerate the viewer around them (the attack)."""
    from epi_core.container import EPIContainer

    work = tmp_path / "work"
    EPIContainer.unpack(epi, work)
    steps = [
        json.loads(line)
        for line in (work / "steps.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for step in steps:
        if step.get("kind") == "agent.decision":
            step.setdefault("content", {})["decision"] = "deny"
    (work / "steps.jsonl").write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in steps) + "\n", encoding="utf-8"
    )
    manifest = EPIContainer.read_manifest(epi)
    return EPIContainer._create_embedded_viewer(
        work,
        manifest,
        viewer_version=str(getattr(manifest, "viewer_version", None) or "minimal"),
        output_path=tmp_path / "rebuilt.epi",
    )


def test_tampered_with_viewer_renders_no_computed_pass(tmp_path, monkeypatch, pytestconfig):
    epi = _sealed_with_viewer(tmp_path, monkeypatch)
    html = _tampered_viewer_html(epi, tmp_path)
    viewer = tmp_path / "viewer.html"
    viewer.write_text(html, encoding="utf-8")

    manager, browser = _launch(pytestconfig)
    try:
        page = browser.new_page()
        page.goto(viewer.as_uri())
        page.wait_for_timeout(3500)
        text = page.inner_text("body")
        browser.close()
    finally:
        manager.__exit__(None, None, None)

    lowered = text.lower()
    assert "integrity verified" not in lowered
    assert "0 mismatch" not in lowered
    assert "not verified" in lowered
