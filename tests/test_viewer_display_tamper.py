"""The viewer must not show green integrity banners over altered evidence.

The browser page displays steps from a baked-in copy, while only the hashed
``steps.jsonl`` is bound to the signed manifest. Earlier the page checked the
hashed files but displayed the baked copy and read the header banner from a
flag stored in the same editable page, so changing only what was displayed (or
deleting the hashed copy, or forging the flag) still showed
INTEGRITY VERIFIED / SIGNATURE VALID over the attacker's text.
"""

from __future__ import annotations

import base64
import glob
import json
import os
import re
import zipfile

import pytest

MARK = "I APPROVE TRANSFERRING $1,000,000 (TAMPER)"


def _chromium():
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    return os.environ.get("EPI_TEST_CHROMIUM") or (hits[0] if hits else None)


@pytest.fixture()
def sealed_viewer(monkeypatch, tmp_path):
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    from epi_mcp.records import seal_record

    r = seal_record(
        [
            {"kind": "user.message", "content": {"text": "Please review the clause."},
             "timestamp": "2026-10-05T10:00:00Z", "fidelity": "verbatim"},
            {"kind": "assistant.message", "content": {"text": "Acceptable."},
             "timestamp": "2026-10-05T10:00:05Z", "fidelity": "verbatim"},
        ],
        goal="Contract review",
    )
    return zipfile.ZipFile(r["epi_path"]).read("viewer.html").decode("utf-8")


def _variant(html, mutate):
    m = re.search(r'(<script id="epi-preloaded-cases" type="application/json">)(.*?)(</script>)', html, re.S)
    data = json.loads(m.group(2))
    mutate(data["cases"][0])
    return html[: m.start(2)] + json.dumps(data) + html[m.end(2):]


def _edit_display(c):
    c["steps"][0]["content"]["text"] = MARK


def _delete_hashed(c):
    _edit_display(c)
    c["files"].pop("steps.jsonl", None)
    c.pop("archive_base64", None)


def _forge_flags(c):
    _delete_hashed(c)
    c["integrity"] = {"ok": True, "checked": 8, "mismatches": []}


def _drop_all_files(c):
    _forge_flags(c)
    c["files"] = {}


def _edit_display_and_copy(c):
    _edit_display(c)
    c["files"]["steps.jsonl"] = base64.b64encode(
        ("\n".join(json.dumps(s) for s in c["steps"]) + "\n").encode()
    ).decode()


def _render(html, tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    exe = _chromium()
    if not exe:
        pytest.skip("no chromium available")
    path = tmp_path / "v.html"
    path.write_text(html, encoding="utf-8")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(path.as_uri())
        page.wait_for_timeout(3500)
        text = page.inner_text("body")
        browser.close()
    return text


def test_untouched_file_still_shows_verified_with_a_live_count(sealed_viewer, tmp_path):
    text = _render(sealed_viewer, tmp_path)
    assert "INTEGRITY VERIFIED" in text and "SIGNATURE VALID" in text
    assert MARK not in text
    # signature valid is not an identity: the page says the signer is not verified
    assert "SIGNER NOT VERIFIED" in text


@pytest.mark.parametrize(
    "mutate",
    [_edit_display, _delete_hashed, _forge_flags, _drop_all_files, _edit_display_and_copy],
    ids=["display-only", "hashed-copy-removed", "flags-forged", "all-files-removed", "copy-edited-hash-stale"],
)
def test_altered_evidence_never_shows_a_green_integrity_banner(sealed_viewer, tmp_path, mutate):
    text = _render(_variant(sealed_viewer, mutate), tmp_path)
    assert "INTEGRITY FAILED" in text
    assert "INTEGRITY VERIFIED" not in text


def test_display_only_edit_shows_the_sealed_text_not_the_attackers(sealed_viewer, tmp_path):
    text = _render(_variant(sealed_viewer, _edit_display), tmp_path)
    assert MARK not in text
    assert "Please review the clause." in text
