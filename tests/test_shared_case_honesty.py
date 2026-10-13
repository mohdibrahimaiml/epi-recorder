"""WP-SEC-5: shared-case and browser verifier must never show false green.

Browser rules pinned here (same honesty bar as the CLI):
  1. home-verify.js: a manifest.json that is not a JSON object (garbage
     string, array, trailing junk) fails as Invalid manifest — never
     "Structure valid, Hashes match".
  2. home-verify.js: integrity_ok is false when zero files were checked
     (an empty file_manifest must not read "Hashes match").
  3. home-verify.js: a registry-listed key stays UNKNOWN ("informational;
     not a pin", name escaped) — never KNOWN / IDENTITY PINNED / HIGH.
  4. home-verify.js: the WebCrypto error is stored raw and escaped once at
     render (no double-escaping).
  5. epi-verify-core.js: hashChain is null ("not checked in browser"),
     never a hard-coded true; non-object manifests are rejected.
  6. cases/index.html: no plain "Verified case" green; unpinned-but-valid
     shows the signer-not-pinned caveat, unverified shows the strict CLI
     command (amber), never green.
  7. Product (SEC-4 follow-ups): strict never resolves did:web (local-only)
     and says exactly how to pin; revocation wording is precise.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from tests.test_seal_witness import _hermetic

REPO = Path(__file__).resolve().parents[1]
HOME_VERIFY = (REPO / "website" / "js" / "home-verify.js").read_text(encoding="utf-8")
EPI_CORE = (REPO / "website" / "js" / "epi-verify-core.js").read_text(encoding="utf-8")
CASES = (REPO / "website" / "cases" / "index.html").read_text(encoding="utf-8")

STRICT_CMD = "epi verify FILE --policy strict --witness-log received.jsonl --offline"


def test_manifest_must_be_json_object():
    assert "Invalid manifest" in HOME_VERIFY, "garbage manifest must fail loudly"


def test_trailing_junk_rejected_by_parser():
    src = _extract_parser(HOME_VERIFY)
    cases = [
        ('{"a":1} trailing', True),
        ('{"a":1}{"b":2}', True),
        ('"just a string"', False),  # parses (valid JSON); rejected by the object check
        ('{"a":1}', False),
    ]
    with tempfile.TemporaryDirectory() as td:
        driver = Path(td) / "drv.mjs"
        driver.write_text(
            src
            + "\nconst cases = "
            + json.dumps([c[0] for c in cases])
            + ";\nfor (const [i, text] of cases.entries()) {\n"
            + "  let threw = false;\n"
            + "  try { parseJSONPreserveNumbers(text); } catch (e) { threw = true; }\n"
            + "  console.log(i + ':' + (threw ? 'throw' : 'ok'));\n}\n",
            encoding="utf-8",
        )
        out = subprocess.run(
            ["node", str(driver)], capture_output=True, text=True, check=True
        ).stdout
    got = dict(line.split(":") for line in out.strip().splitlines())
    for i, (text, should_throw) in enumerate(cases):
        assert (got[str(i)] == "throw") == should_throw, f"{text!r}: got {got[str(i)]}"


def _extract_parser(src: str) -> str:
    start = src.index("function tokenizeJSON(")
    end = src.index("\nfunction sortedJSON(")
    return src[start:end]


def test_zero_files_checked_is_not_integrity_ok():
    # integrity_ok must require at least one checked file.
    assert re.search(r"checked\s*>\s*0|files_checked\s*!==?\s*0|checked\s*!==?\s*0", HOME_VERIFY), (
        "integrity must depend on files actually checked"
    )


def test_registry_listing_never_pinned_in_browser():
    assert "report.identity.status='KNOWN'" not in HOME_VERIFY, (
        "browser must never claim KNOWN (visitor pinned nothing)"
    )
    assert "informational; not a pin" in HOME_VERIFY
    assert "esc(registry.trusted_keys[manifest.public_key])" in HOME_VERIFY


def test_webcrypto_error_stored_raw():
    assert "'WebCrypto not available: '+e.message" in HOME_VERIFY, (
        "store raw; reportDOM escapes once at render"
    )
    assert "'WebCrypto not available: '+esc(e.message)" not in HOME_VERIFY
    assert "esc(i.detail)" in HOME_VERIFY, "reportDOM must escape the detail line"


def test_core_hashchain_honest():
    assert "hashChain: true" not in EPI_CORE
    assert "hashChain: null" in EPI_CORE


def test_core_rejects_non_object_manifest():
    assert re.search(r"not a JSON object|Invalid manifest", EPI_CORE), (
        "garbage manifest must fail, not read as unsigned"
    )


def test_cases_no_plain_verified_green():
    assert "label='Verified case'" not in CASES
    assert "Seal valid" in CASES and "not pinned" in CASES
    assert STRICT_CMD in CASES, "amber state must show the strict CLI command"


def test_strict_did_unpinned_says_how_to_pin(monkeypatch, tmp_path) -> None:
    """SEC-4 follow-up: strict is offline, so a declared did:web stays
    unpinned — and the FAIL reason must say exactly how to pin it."""
    from epi_recorder import record

    _hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(tmp_path / "trusted"))
    (tmp_path / "trusted").mkdir()
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "sealer"))
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "sealer" / "keys"))
    out = tmp_path / "run.epi"
    monkeypatch.setenv("EPI_DID", "did:web:vendor.example")
    with record(str(out)) as epi:
        epi.log_step("agent.decision", {"content": "hi", "decision": "approve"})
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "auditor"))
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "auditor" / "keys"))
    res = CliRunner().invoke(cli_app, ["verify", str(out), "--policy", "strict", "--json"])
    assert res.exit_code == 1, res.output
    reason = json.loads(res.output)["decision"]["reason"]
    assert "did:web:vendor.example" in reason, reason
    assert "epi keys trust --from-did did:web:vendor.example" in reason, reason


def test_revocation_wording_is_precise():
    contract = (REPO / "docs" / "VERIFICATION_CONTRACT.md").read_text(encoding="utf-8").lower()
    assert "only" in contract and "not pinned" in contract
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    sec = " ".join(
        changelog.split("## [4.6.1]")[1].split("## [4.6.0]")[0].split()
    )
    assert "did:web" in sec and "strict" in sec, "CHANGELOG must note strict skips did:web"
    assert "have NOT pinned" in sec or "not pinned" in sec
