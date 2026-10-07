"""Every section of the viewer must state only what it actually checked.

Found by comparing what the page displayed with what was true in the file:
- Chain Integrity showed OK for a file with a deliberately broken hash chain
  (the CLI said FAIL): it was never recomputed, just "steps exist and file
  hashes match".
- "Completeness OK" was the same fallback and reads like "the record is
  complete"; it actually measures call/response pairing.
- Times were the reader's local time with no zone.
- Declared gaps were only in a hover tooltip, and only the first five.
"""

from __future__ import annotations

import glob
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _chromium():
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    return os.environ.get("EPI_TEST_CHROMIUM") or (hits[0] if hits else None)


def _render(html: str, tmp_path: Path) -> dict:
    sync_api = pytest.importorskip("playwright.sync_api")
    exe = _chromium()
    if not exe:
        pytest.skip("no chromium available")
    page_path = tmp_path / "v.html"
    page_path.write_text(html, encoding="utf-8")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(page_path.as_uri())
        page.wait_for_timeout(3500)

        def txt(sel):
            el = page.query_selector(sel)
            return el.inner_text().strip() if el else None

        def title(sel):
            el = page.query_selector(sel)
            return (el.get_attribute("title") or "") if el else None

        out = {
            "body": page.inner_text("body"),
            "chain": txt("#diag-chain"),
            "chain_title": title("#diag-chain"),
            "pairing": txt("#diag-completeness"),
            "pairing_title": title("#diag-completeness"),
            "files": txt("#diag-files"),
            "created": txt("#meta-created"),
            "tz_note": txt("#evidence-tz"),
            "pills": txt("#header-pills"),
            "gaps": [li.inner_text() for li in page.query_selector_all("#capture-gaps-list li")],
            "labels": [el.inner_text().strip().lower() for el in page.query_selector_all(".diag-label")],
        }
        browser.close()
    return out


def _seal(monkeypatch, tmp_path, events, goal="Section test"):
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    from epi_mcp.records import seal_record

    r = seal_record(events, goal=goal)
    return zipfile.ZipFile(r["epi_path"]).read("viewer.html").decode("utf-8"), r


EVENTS = [
    {"kind": "user.message", "content": {"text": "Approve the loan?"}, "timestamp": "2026-10-05T10:00:00Z", "fidelity": "verbatim"},
    {"kind": "tool.call", "content": {"tool": "credit_check", "input": {"id": 1}}, "timestamp": "2026-10-05T10:00:01Z"},
    {"kind": "tool.response", "content": {"result": "score 410"}, "timestamp": "2026-10-05T10:00:02Z"},
    {"kind": "agent.decision", "content": {"decision": "deny", "rationale": "low score"}, "timestamp": "2026-10-05T10:00:03Z"},
]


def test_intact_record_shows_computed_chain_and_pairing_and_utc(monkeypatch, tmp_path):
    html, _ = _seal(monkeypatch, tmp_path, EVENTS)
    r = _render(html, tmp_path)
    assert r["chain"] == "OK" and "Recomputed in this page" in r["chain_title"]
    assert r["pairing"] == "OK"
    assert "call/response pairing" in r["labels"]
    assert "completeness" not in r["labels"]
    assert r["created"].endswith("UTC")
    assert r["tz_note"] and "UTC" in r["tz_note"]
    files = r["files"].lower()
    assert re.search(r"\d+ checked / 0 mismatches", files)
    # a listed file this page cannot re-hash (the viewer's own HTML) is stated, not silently counted
    assert "not checkable here" in files


def test_broken_chain_is_reported_as_broken_and_fails_integrity(monkeypatch, tmp_path):
    """A file signed consistently but with its steps reordered after chaining."""
    from epi_core.container import EPIContainer
    from epi_core.keys import KeyManager
    from epi_core.schemas import ManifestModel
    from epi_core.trust import sign_manifest
    from epi_mcp.records import _chain_steps, _normalize_events

    monkeypatch.setenv("EPI_NOTARIZE", "0")
    steps = _chain_steps(_normalize_events(EVENTS))
    steps[1], steps[2] = steps[2], steps[1]
    work = Path(tempfile.mkdtemp())
    (work / "steps.jsonl").write_text("\n".join(json.dumps(s) for s in steps) + "\n")
    km = KeyManager(tmp_path / "evilkeys")
    km.generate_keypair("evil")
    key = km.load_private_key("evil")
    out = tmp_path / "broken.epi"
    EPIContainer.pack(work, ManifestModel(goal="Loan"), out,
                      signer_function=lambda m: sign_manifest(m, key, "evil"),
                      generate_analysis=False, preserve_generated=True)
    r = _render(zipfile.ZipFile(out).read("viewer.html").decode("utf-8"), tmp_path)
    assert r["chain"] == "BROKEN"
    assert "INTEGRITY FAILED" in r["body"] and "INTEGRITY VERIFIED" not in r["body"]


def test_unanswered_tool_call_is_shown_as_a_pairing_gap(monkeypatch, tmp_path):
    html, _ = _seal(monkeypatch, tmp_path, EVENTS[:2])  # tool.call with no response
    r = _render(html, tmp_path)
    assert r["pairing"].startswith("GAPS")
    assert "no matching tool.response" in r["pairing_title"]


def test_older_format_is_never_shown_as_a_verified_chain(tmp_path):
    from epi_cli.view import _create_decision_ops_viewer
    from epi_core.container import EPIContainer

    legacy = REPO / "tests" / "goldens" / "legacy-spec-4.4.0.epi"
    ext = Path(tempfile.mkdtemp())
    EPIContainer.unpack(legacy, ext)
    r = _render(_create_decision_ops_viewer(ext, legacy), tmp_path)
    assert r["chain"] == "NOT CHECKED HERE"


def test_current_format_golden_chain_is_recomputed_and_ok(tmp_path):
    from epi_cli.view import _create_decision_ops_viewer
    from epi_core.container import EPIContainer

    golden = REPO / "tests" / "goldens" / "spec-4.4.3.epi"
    ext = Path(tempfile.mkdtemp())
    EPIContainer.unpack(golden, ext)
    r = _render(_create_decision_ops_viewer(ext, golden), tmp_path)
    assert r["chain"] == "OK"


def test_declared_gaps_are_visible_on_the_page_and_complete(monkeypatch, tmp_path):
    html, rec = _seal(monkeypatch, tmp_path, [
        {"kind": "user.message", "content": {"text": "a"}},                      # no timestamp, unlabelled
        {"kind": "assistant.message", "content": {"text": "b"}},
        {"kind": "agent.decision", "content": {"text": "no decision field"}},
    ])
    declared = json.loads(zipfile.ZipFile(rec["epi_path"]).read("artifacts/manifest.json"))["known_gaps"]
    r = _render(html, tmp_path)
    assert len(declared) >= 6                      # more than the five a tooltip used to show
    assert len(r["gaps"]) == len(declared)
    assert any("share one timestamp" in g for g in r["gaps"])


IDENTITY = {"method": "oidc", "verified_by": "https://accounts.google.com", "account_id": "abcd1234efgh5678",
            "email_verified": True, "email": "alice@corp.example"}


def _seal_identity(monkeypatch, tmp_path, identity):
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    from epi_mcp.records import seal_record

    r = seal_record(EVENTS, goal="Identity", identity=identity)
    return zipfile.ZipFile(r["epi_path"]).read("viewer.html").decode("utf-8")


def test_signed_in_identity_is_shown_for_a_verified_file(monkeypatch, tmp_path):
    r = _render(_seal_identity(monkeypatch, tmp_path, IDENTITY), tmp_path)
    pills = r["pills"].lower()
    assert "signed in as alice@corp.example" in pills and "accounts.google.com" in pills
    assert "signer not verified" in pills  # a name never upgrades the signer to trusted


def test_anonymous_seal_shows_no_identity(monkeypatch, tmp_path):
    r = _render(_seal_identity(monkeypatch, tmp_path, None), tmp_path)
    assert "signed in as" not in r["pills"].lower()


def test_editing_the_page_cannot_forge_who_sealed_it(monkeypatch, tmp_path):
    """Swapping the name in the page's own copy must not change what is displayed."""
    html = _seal_identity(monkeypatch, tmp_path, IDENTITY)
    assert "alice@corp.example" in html
    r = _render(html.replace("alice@corp.example", "ceo@victim.example"), tmp_path)
    pills = r["pills"].lower()
    assert "ceo@victim.example" not in pills


def test_github_username_is_shown_as_a_handle(monkeypatch, tmp_path):
    gh = {"method": "github", "verified_by": "github.com", "account_id": "abcd1234efgh5678",
          "username": "octocat", "profile_url": "https://github.com/octocat", "email_verified": False}
    r = _render(_seal_identity(monkeypatch, tmp_path, gh), tmp_path)
    assert "signed in as @octocat" in r["pills"].lower()


def test_server_assigned_times_say_received_not_a_zero_offset(monkeypatch, tmp_path):
    """A chat host gives no per-message times; "+0.000s" on every row would read as a measured gap."""
    untimed = [{"kind": "user.message", "content": {"text": "hi"}}, {"kind": "assistant.message", "content": {"text": "yo"}}]
    html, _ = _seal(monkeypatch, tmp_path, untimed)
    body = _render(html, tmp_path)["body"]
    assert "+0.000s" not in body and "received" in body.lower()


def test_caller_times_still_show_offsets(monkeypatch, tmp_path):
    html, _ = _seal(monkeypatch, tmp_path, EVENTS)
    assert "+1.000s" in _render(html, tmp_path)["body"]
