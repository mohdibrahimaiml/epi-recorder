"""WP-VERIFY-UX: the home-page drag-and-drop verifier must agree with the CLI
and speak plain language.

  1. Polyglot viewer tampering is detected (reserved_tail[0:32] check).
  2. Step-chain verdicts match epi_cli/verify.py _verify_step_chain for every
     .epi under website/assets (incl. pre-JCS spec 4.4.0 files).
  3. resetChecks() restores the six original labels (no leftover text/dots);
     non-EPI files leave the rows neutral.
  4. Phone: hover styles only under (hover:hover); seal-ok/warn/fail have colors.
  5. Files over 25 MB are refused immediately with a plain message.
  6. A plain-language headline leads every verdict; file-type sniffing names
     PDFs/photos/zips instead of hex; technical detail sits under a toggle.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME_VERIFY = (REPO / "website" / "js" / "home-verify.js").read_text(encoding="utf-8")
# JS-escaped quotes (isn\'t) must not defeat copy assertions.
HOME_FLAT = HOME_VERIFY.replace("\\", "")
SITE_CSS = (REPO / "website" / "css" / "site.css").read_text(encoding="utf-8")
SITE_FLAT = SITE_CSS.replace(" ", "")

CHECK_LABELS = {
    "chk1": "01 · Structure",
    "chk2": "02 · File hashes",
    "chk3": "03 · Signature",
    "chk4": "04 · Step chain",
    "chk5": "05 · Identity (browser)",
    "chk6": "06 · Full audit → CLI",
}

JS_EXTRACT = [
    ("function tokenizeJSON(", "\nfunction parseJSONPreserveNumbers("),
    ("function parseJSONPreserveNumbers(", "\nfunction sortedJSON("),
    ("function sortedJSON(", "\n// JCS number encoding"),
    ("function jcsNumberFromRaw(", "\n// Python-legacy number encoding"),
    ("function legacyNumberFromRaw(", "\n// True when the artifact predates JCS"),
    ("function isPreJcsSpecLocal(", "\nfunction epiUtcZ("),
    ("async function canonicalStepHash(", "\nfunction unwrapNum("),
    ("function unwrapNum(", "\nfunction auditStepSequence("),
    ("async function auditStepChain(", "\nfunction auditStepCount("),
    ("function epiUtcZ(", "\nfunction normalizeCreatedAt("),
]


def _node_prelude() -> str:
    parts = []
    for start_mark, end_mark in JS_EXTRACT:
        start = HOME_VERIFY.index(start_mark)
        end = HOME_VERIFY.index(end_mark, start)
        parts.append(HOME_VERIFY[start:end])
    return (
        "import { webcrypto } from 'crypto';\n"
        "async function sha256(buf){return Array.from(new Uint8Array("
        "await webcrypto.subtle.digest('SHA-256',buf))).map(function(b)"
        "{return b.toString(16).padStart(2,'0')}).join('')}\n" + "\n".join(parts)
    )


def _run_node(driver: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "drv.mjs"
        p.write_text(_node_prelude() + "\n" + driver, encoding="utf-8")
        out = subprocess.run(["node", str(p)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[:800]
    return out.stdout


def test_polyglot_tamper_detected_in_code():
    assert "function verifyPolyglotViewer(" in HOME_VERIFY
    assert "SEAL FAIL — FILE ALTERED" in HOME_VERIFY


def test_legacy_numbers_match_python_repr():
    import json as pyjson

    raws = ["89.0", "0.1", "3.14", "100.0", "-0.0", "42", "-7",
            "1e16", "1e-05", "2.5e-7", "1e21", "0.0001", "1234567890123456.0",
            "12345678901234567890123"]
    want = {r: pyjson.dumps(float(r) if re.search(r"[.eE]", r) else int(r)) for r in raws}
    driver = "const raws = %s;\nfor (const r of raws) console.log(r + '=>' + legacyNumberFromRaw(r));\n" % json.dumps(raws)
    got = dict(line.split("=>", 1) for line in _run_node(driver).strip().splitlines())
    for r in raws:
        assert got[r] == want[r], f"{r}: node {got[r]!r} != python {want[r]!r}"


def test_chain_parity_with_cli_for_every_site_epi():
    from epi_cli.verify import _verify_step_chain

    files = sorted((REPO / "website" / "assets").rglob("*.epi"))
    assert files, "no corpus files found"
    cases = []
    for f in files:
        import zipfile

        with zipfile.ZipFile(f) as z:
            names = z.namelist()
            if "manifest.json" not in names or "steps.jsonl" not in names:
                continue
            manifest = json.loads(z.read("manifest.json"))
            raw_lines = [
                l for l in z.read("steps.jsonl").decode("utf-8").splitlines() if l.strip()
            ]
        py_steps = [json.loads(l) for l in raw_lines]
        py_ok, _breaks = _verify_step_chain(py_steps, manifest.get("spec_version"))
        cases.append({"spec": manifest.get("spec_version"), "lines": raw_lines, "py": py_ok})
    assert cases, "no viable corpus files"
    driver = (
        "const cases = %s;\n(async () => {\n"
        "  for (const c of cases) {\n"
        "    const steps = [];\n"
        "    for (const line of c.lines) {\n"
        "      try { steps.push(parseJSONPreserveNumbers(line)); } catch (e) {}\n"
        "    }\n"
        "    console.log(c.spec + '|' + (await auditStepChain(steps, c.spec)));\n"
        "  }\n})();\n" % json.dumps([{"spec": c["spec"], "lines": c["lines"]} for c in cases])
    )
    for line, case in zip(_run_node(driver).strip().splitlines(), cases):
        _spec, js_ok = line.rsplit("|", 1)
        assert (js_ok == "true") == case["py"], (
            f"chain mismatch (spec={case['spec']}): browser={js_ok}, cli={case['py']}"
        )


def test_reset_restores_original_labels():
    m = re.search(r"function resetChecks\(\)\{(.*?)\n\}", HOME_VERIFY, re.S)
    assert m, "resetChecks missing"
    body = m.group(1)
    for cid, label in CHECK_LABELS.items():
        assert label in body or "CHECK_LABELS" in body, f"{cid} label not restored"
    assert ".replace(/^" not in body, "reset must restore labels, not regex-surgery"


def test_oversize_files_refused_fast():
    assert re.search(r"25\s*\*\s*1024\s*\*\s*1024|26_214_400|26214400", HOME_VERIFY), (
        "files over 25 MB must be refused before reading"
    )
    assert "too large to check in the browser" in HOME_VERIFY


def test_touch_hover_and_seal_colors():
    assert "@media(hover:hover)" in SITE_FLAT, "hover styles must not stick on touch"
    assert re.search(r"\.drop\.seal-ok\s*\{", SITE_CSS), "seal-ok needs a color"
    assert re.search(r"\.drop\.seal-warn\s*\{", SITE_CSS), "seal-warn needs a color"
    assert re.search(r"\.drop\.seal-fail\s*\{", SITE_CSS), "seal-fail needs a color"


def test_file_type_sniffing():
    for kind in ["PDF", "PNG", "JPEG", "GIF", "ZIP"]:
        assert kind in HOME_VERIFY, f"{kind} sniffing missing"
    assert "isn't an EPI evidence file" in HOME_FLAT


def test_polish_headlines():
    flat = HOME_FLAT
    # Viewer tamper: plain red headline first, technical detail dimmed below.
    assert "changed after it was sealed. Don't rely on it." in flat
    # Non-EPI zip and empty file share the not-an-EPI headline.
    assert flat.count("isn't an EPI evidence file") >= 3
    assert "Not a valid EPI file" not in flat
    assert "No mimetype file in archive" not in flat
