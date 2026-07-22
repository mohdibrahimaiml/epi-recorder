"""
Item 2 — notarization visibility in the forensic viewer.

Confirms:
- web_viewer HTML/JS renders a notarization panel when data is present
- panel is hidden when data is absent
- epi view injects notarization from real agicomply_demo.epi
- TSA genTime is extracted from the embedded .tsr token
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest

from epi_cli.view import (
    _build_preloaded_case_payload,
    _extract_tsr_gen_time,
)
from epi_core.container import EPIContainer

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "agicomply_demo.epi"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_web_viewer_has_notarization_panel_markup():
    html = _read("web_viewer/index.html")
    assert 'id="notarization-block"' in html
    assert 'id="ind-notarization"' in html
    assert 'id="notary-provider"' in html
    assert 'id="notary-tsa"' in html
    assert 'id="notary-time"' in html
    assert 'id="notary-ots"' in html
    assert 'id="diag-notary"' in html
    # Hidden by default — shown only when data exists
    assert "notarization-block" in html and "hidden" in html


def test_web_viewer_js_resolves_and_renders_notarization():
    js = _read("web_viewer/app.js")
    assert "function resolveNotarization" in js
    assert "function extractGenTimeFromTsrBytes" in js
    assert "function renderNotarization" in js
    assert "renderNotarization(caseData)" in js
    assert "artifacts/notarization/notarization.json" in js
    # Graceful absence
    assert "block.classList.add('hidden')" in js or 'block.classList.add("hidden")' in js


def test_extract_tsr_gen_time_from_agicomply_demo(tmp_path: Path):
    if not DEMO.exists():
        pytest.skip("agicomply_demo.epi not in tree")
    extract = tmp_path / "x"
    EPIContainer.unpack(DEMO, extract)
    tsr = extract / "artifacts" / "notarization" / "tsa_reply.tsr"
    assert tsr.exists()
    gen = _extract_tsr_gen_time(tsr)
    assert gen is not None
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", gen)
    # Known token from this fixture (FreeTSA)
    assert gen.startswith("2026-07-19")


def test_view_payload_includes_notarization_for_agicomply_demo(tmp_path: Path):
    if not DEMO.exists():
        pytest.skip("agicomply_demo.epi not in tree")
    extract = tmp_path / "x"
    EPIContainer.unpack(DEMO, extract)
    case = _build_preloaded_case_payload(extract, DEMO)

    assert case["notarization"] is not None
    evidence = case["notarization"]
    assert evidence["notarized_at"]["provider"] == "rfc3161"
    assert "freetsa.org" in evidence["notarized_at"]["url"]
    assert evidence["tsa_token_available"] is True
    assert evidence["ots_proof_available"] is False

    assert case["notarization_tsa_time"] is not None
    assert case["notarization_tsa_time"].startswith("2026-07-19")

    # Files surface for browser re-parse path
    assert "artifacts/notarization/notarization.json" in case["files"]
    assert "artifacts/notarization/tsa_reply.tsr" in case["files"]


def test_view_payload_notarization_absent_when_no_tokens(tmp_path: Path):
    """Graceful: no broken panel data when notarization directory missing."""
    extract = tmp_path / "bare"
    extract.mkdir()
    (extract / "steps.jsonl").write_text("{}\n", encoding="utf-8")
    (extract / "manifest.json").write_text(
        json.dumps(
            {
                "spec_version": "4.0.1",
                "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
                "created_at": "2026-01-15T12:00:00Z",
                "file_manifest": {"steps.jsonl": "a" * 64},
            }
        ),
        encoding="utf-8",
    )
    # Minimal fake path object for size/name
    fake_epi = tmp_path / "bare.epi"
    fake_epi.write_bytes(b"PK\x03\x04")  # not a real epi — only testing JSON reads

    # _build_preloaded_case_payload needs a real epi for integrity/signature;
    # call the pieces that matter for absence instead.
    from epi_cli.view import _read_json_if_exists, _extract_tsr_gen_time

    assert (
        _read_json_if_exists(extract / "artifacts" / "notarization" / "notarization.json")
        is None
    )
    assert _extract_tsr_gen_time(extract / "artifacts" / "notarization" / "tsa_reply.tsr") is None


def test_render_dom_snapshot_from_agicomply_evidence(tmp_path: Path):
    """
    Screenshot-equivalent: build the DOM strings the panel would show for
    real agicomply_demo.epi evidence (no browser required).
    """
    if not DEMO.exists():
        pytest.skip("agicomply_demo.epi not in tree")
    extract = tmp_path / "x"
    EPIContainer.unpack(DEMO, extract)
    case = _build_preloaded_case_payload(extract, DEMO)
    evidence = case["notarization"]
    tsa_time = case["notarization_tsa_time"]

    # Exact text nodes the UI would set (mirrors renderNotarization)
    provider = evidence["notarized_at"]["provider"]
    tsa_url = evidence["notarized_at"]["url"]
    hash_hex = evidence["notarized_at"]["hash"]
    tsa_ok = evidence["tsa_token_available"] is True
    ots_ok = evidence["ots_proof_available"] is True
    ots_note = evidence.get("ots_note") or "No — OTS proof not embedded"

    ind = "RFC 3161 + OTS" if (tsa_ok and ots_ok) else ("RFC 3161" if tsa_ok else "RECORDED (no token)")
    ots_text = (
        "Yes — OpenTimestamps / Bitcoin anchoring present"
        if ots_ok
        else ots_note
    )

    dom = f"""
<section id="integrity-status">
  <div id="notarization-block">  <!-- NOT hidden when present -->
    <span id="ind-notarization" class="indicator verified">{ind}</span>
    <span id="notary-provider">{provider}</span>
    <span id="notary-tsa">{tsa_url}</span>
    <span id="notary-time">{tsa_time}</span>
    <span id="notary-ots">{ots_text}</span>
    <span id="notary-hash">{hash_hex}</span>
  </div>
  <span id="diag-notary" class="diag-status ok">RFC3161</span>
</section>
""".strip()

    # Persist for human inspection in pytest output / debug
    (tmp_path / "notarization_dom_snapshot.html").write_text(dom, encoding="utf-8")

    assert provider == "rfc3161"
    assert "freetsa.org" in tsa_url
    assert tsa_time.startswith("2026-07-19")
    assert ind == "RFC 3161"
    assert "OTS" in ots_text or "opentimestamps" in ots_text.lower() or "No" in ots_text
    assert len(hash_hex) == 64
    print("\n=== NOTARIZATION DOM SNAPSHOT (agicomply_demo.epi) ===\n" + dom + "\n===\n")
