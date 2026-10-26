"""The pack-time embedded viewer must never bake a file-integrity PASS.

A `.epi` opened by double-click carries only an editable display copy of the
evidence, so any "N checked / 0 mismatches" it shows is self-consistent by
construction and proves nothing. Regression: a with-viewer file whose sealed
evidence was rewritten after sealing still displayed "0 mismatches" (green) in
the viewer's diagnostic matrix, because the viewer was generated with a baked
``integrity: {ok: true}``.

These assertions run without a browser; the rendered-page check lives in
``tests/browser/test_viewer_tamper_no_baked_pass.py``.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest

PRELOADED = re.compile(
    r'<script id="epi-preloaded-cases" type="application/json">(.*?)</script>', re.S
)


def _baked_integrity(viewer_html: str) -> dict:
    match = PRELOADED.search(viewer_html)
    assert match, "viewer has no preloaded cases payload"
    return json.loads(match.group(1))["cases"][0]["integrity"]


@pytest.fixture()
def sealed_epi(monkeypatch, tmp_path) -> Path:
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    from epi_mcp.records import seal_record

    result = seal_record(
        [
            {"kind": "user.message", "content": {"text": "Review the clause."},
             "timestamp": "2026-10-05T10:00:00Z", "fidelity": "verbatim"},
            {"kind": "tool.call", "content": {"tool": "check", "input": {}},
             "timestamp": "2026-10-05T10:00:01Z"},
            {"kind": "tool.response", "content": {"result": "ok"},
             "timestamp": "2026-10-05T10:00:02Z"},
            {"kind": "agent.decision", "content": {"decision": "approve"},
             "timestamp": "2026-10-05T10:00:03Z"},
        ],
        goal="Baked-pass regression",
    )
    return Path(result["epi_path"])


def _viewer_html(epi: Path) -> str:
    with zipfile.ZipFile(epi) as archive:
        return archive.read("viewer.html").decode("utf-8")


def test_pack_time_viewer_bakes_no_integrity_pass(sealed_epi):
    integ = _baked_integrity(_viewer_html(sealed_epi))
    assert integ.get("ok") is not True, integ
    assert integ.get("checked") == 0, integ
    assert integ.get("mismatches") == [], integ


def test_viewer_rebuilt_around_forged_steps_bakes_no_pass(sealed_epi, tmp_path):
    """Reproduce the attack: rewrite the sealed steps, regenerate the viewer."""
    from epi_core.container import EPIContainer

    work = tmp_path / "work"
    EPIContainer.unpack(sealed_epi, work)

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

    manifest = EPIContainer.read_manifest(sealed_epi)
    viewer_html = EPIContainer._create_embedded_viewer(
        work,
        manifest,
        viewer_version=str(getattr(manifest, "viewer_version", None) or "minimal"),
        output_path=tmp_path / "rebuilt.epi",
    )

    integ = _baked_integrity(viewer_html)
    assert integ.get("ok") is not True, integ
    assert integ.get("checked") == 0, integ


def test_diagnostic_matrix_cannot_show_an_uncomputed_pass():
    """The matrix must gate any green pass on a computed/authoritative result."""
    from epi_core.viewer_assets import load_viewer_assets

    js = load_viewer_assets()["app_js"] or ""
    assert "NOT VERIFIED HERE — drop this file on epilabs.org/verify" in js
    # the pass branch is gated, not the old `checked > 0 || integrity.ok != null`
    assert "integrityComputed" in js
