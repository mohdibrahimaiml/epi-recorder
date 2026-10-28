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
        out = subprocess.run(
            ["node", str(p)], capture_output=True, text=True, encoding="utf-8"
        )
    assert out.returncode == 0, out.stderr[:800]
    return out.stdout


def test_polyglot_tamper_detected_in_code():
    # One implementation, in the shared core, used by every verifying page
    # (/verify/, homepage, trust page): home-verify.js only delegates to it.
    core = (REPO / "website" / "js" / "epi-verify-core.js").read_text(encoding="utf-8")
    assert "async function verifyPolyglotViewer(" in core
    assert "global.epiVerifyPolyglotViewer = verifyPolyglotViewer" in core
    assert "viewer = await verifyPolyglotViewer(u8, det0.offset)" in core, "verifyEPI must run the viewer check"
    assert "function verifyPolyglotViewer(" in HOME_VERIFY
    assert "window.epiVerifyPolyglotViewer" in HOME_VERIFY
    assert "reserved_tail" not in HOME_VERIFY.split("function toU8(")[0].split("async function verifyPolyglotViewer(")[1], \
        "home-verify.js must not carry its own copy of the viewer check"
    assert "SEAL FAIL — FILE ALTERED" in HOME_VERIFY


def test_core_verify_epi_rejects_tampered_viewer(tmp_path):
    """verifyEPI (shared by /verify/, the homepage and the trust page) fails a
    file whose embedded viewer HTML changed after sealing; genuine passes."""
    sample = (REPO / "website" / "assets" / "sample.epi").read_bytes()
    marker = b"\n<!-- EPI_ZIP_PAYLOAD_START -->\n"
    assert sample[:4] == b"<!--" and marker in sample and any(sample[72:104])
    bad = bytearray(sample)
    at = bad.index(b"<html", 128)
    bad[at + 1] ^= 0x20
    (tmp_path / "good.epi").write_bytes(sample)
    (tmp_path / "bad.epi").write_bytes(bytes(bad))
    js = REPO / "website" / "js"
    driver = tmp_path / "drv.mjs"
    driver.write_text(
        "import fs from 'fs'; import vm from 'vm'; import {webcrypto} from 'crypto';\n"
        "const ctx = {console, TextEncoder, TextDecoder, crypto: webcrypto, Uint8Array, ArrayBuffer,"
        " DataView, atob, btoa, setTimeout, Promise};\n"
        "ctx.globalThis = ctx; ctx.window = ctx; ctx.self = ctx; vm.createContext(ctx);\n"
        "for (const f of ['jszip.min.js','epi-manifest-preimage.js','epi-verify-core.js'])"
        " vm.runInContext(fs.readFileSync(%s + '/' + f, 'utf8'), ctx);\n"
        "for (const p of process.argv.slice(2)) {"
        " const r = await ctx.verifyEPI(new Blob([fs.readFileSync(p)]));"
        " console.log(JSON.stringify({integrity: r.integrity, viewer: r.viewer, message: r.message})); }\n"
        % json.dumps(str(js)),
        encoding="utf-8",
    )
    out = subprocess.run(
        ["node", str(driver), str(tmp_path / "good.epi"), str(tmp_path / "bad.epi")],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr[:800]
    good, badr = [json.loads(x) for x in out.stdout.strip().splitlines()]
    assert good["integrity"] is True and good["viewer"] is True, good
    assert badr["integrity"] is False and badr["viewer"] is False, badr
    assert "changed after it was sealed" in badr["message"], badr


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


def _story_driver(body: str) -> str:
    """Run buildStory/storyHTML (and esc) from home-verify.js under node."""
    def cut(start_mark: str, end_mark: str) -> str:
        start = HOME_VERIFY.index(start_mark)
        return HOME_VERIFY[start:HOME_VERIFY.index(end_mark, start)]

    prelude = "\n".join([
        cut("function esc(", "\n"),
        # stepLine calls these to label an approval honestly (step 3c).
        cut("function approvalSourceLabel(", "\nfunction hexToBytes("),
        cut("function normalizeVerdict(", "\n// One plain sentence first"),
    ])
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "story.mjs"
        p.write_text(prelude + "\n" + body, encoding="utf-8")
        out = subprocess.run(
            ["node", str(p)], capture_output=True, text=True, encoding="utf-8"
        )
    assert out.returncode == 0, out.stderr[:800]
    return out.stdout


def _steps(*items):
    return json.dumps([{"index": i, "kind": k, "content": c} for i, (k, c) in enumerate(items)])


def test_story_shows_decision_and_human_review():
    steps = _steps(
        ("session.start", {"workflow_name": "Scope check"}),
        ("agent.approval.request", {"action": "vuln.scan", "reason": "scan 10.20.0.5"}),
        ("agent.approval.response", {"approved": False, "reviewer": "vapt_lead", "reason": "Out of scope."}),
        ("agent.decision", {"decision": "REJECT", "rationale": "Host 10.20.0.7 is core banking."}),
        ("environment.captured", {}),
        ("session.end", {}),
    )
    out = json.loads(_story_driver(
        f"const s=buildStory({steps},{{goal:'Scan DemoBank'}});"
        "console.log(JSON.stringify({s,ok:storyHTML(s,false),bad:storyHTML(s,true)}));"
    ))
    s = out["s"]
    assert s["verdict"] == "REJECTED"
    assert s["review"]["approved"] is False
    assert s["review"]["reviewer"] == "vapt_lead"
    assert s["review"]["reason"] == "Out of scope."
    assert s["total"] == 6 and len(s["lines"]) == 5  # environment step is not a story line
    assert "WHAT THE AI DID" in out["ok"] and "Scan DemoBank" in out["ok"]
    # An agent-written response is labelled as the agent's claim, never as a
    # human decision (step 3c).
    assert "Agent-reported: vapt_lead rejected" in out["ok"]
    assert "Human review:" not in out["ok"]
    assert "Decision (agent-reported):" in out["ok"]
    # A tampered file still shows its claims, but labelled as possibly forged.
    assert "may be forged" in out["bad"] and "WHAT THE AI DID" not in out["bad"]


def test_story_verdict_words_match_viewer():
    out = _story_driver(
        "console.log(JSON.stringify(['APPROVE','approved_with_conditions','DISAPPROVED',"
        "'deny','escalate',''].map(normalizeVerdict)));"
    )
    assert json.loads(out) == ["APPROVED", "APPROVED", "REJECTED", "REJECTED", "ESCALATE", ""]


def _story_driver_approvals(story_js: str) -> dict:
    """storyHTML with the approval lines, driven from a literal story object."""
    return json.loads(_story_driver(
        f"console.log(JSON.stringify(storyHTML({story_js},false)));"
    ))


def test_story_approval_states_never_lie():
    """A valid signature with no pinned list is not "nobody signed".

    The browser verifier has no approver registry, so it must say the signer
    is not trusted HERE — and print the command that would fix that — instead
    of claiming no person signed. A bad signature is red, and the sealing key
    is never a human approval.
    """
    base = (
        "{total:3,goal:'Refund',lines:[],verdict:'',rationale:'',review:null,"
        "approvals:[%s]}"
    )
    untrusted_key = "ab" * 32
    html = _story_driver_approvals(base % json.dumps({
        "status": "untrusted",
        "decision": "approve",
        "approval_id": "refund-7",
        "claimed_name": "refund-manager",
        "key": untrusted_key,
        "fingerprint": "d746 bc7d 1111 2222 3333 4444 5555 6666 7777 8888 9999 aaaa bbbb cccc dddd",
    }))
    assert "SIGNED — APPROVER NOT TRUSTED HERE" in html, html
    # The signature verifies; the name is only ever a claim.
    assert "A signature verifies for the key with fingerprint" in html, html
    assert "(claimed name: refund-manager)" in html, html
    assert "--name &#39;refund-manager&#39;" in html, html
    assert "epi approvers add " + untrusted_key in html, html
    assert "--role approver" in html, html
    assert "no person has signed" not in html.lower(), html
    assert ">approved<" not in html.lower(), html

    bad = _story_driver_approvals(base % json.dumps({
        "status": "invalid",
        "decision": "approve",
        "approval_id": "refund-7",
        "claimed_name": "refund-manager",
    }))
    assert "approval signature does not verify" in bad.lower(), bad
    assert "var(--tamper)" in bad, bad
    assert "no person has signed" not in bad.lower(), bad

    sealing = _story_driver_approvals(base % json.dumps({
        "status": "sealing_key",
        "decision": "approve",
        "case_level": True,
    }))
    assert "Not a human approval" in sealing, sealing
    assert "no person has signed" not in sealing.lower(), sealing


def test_story_escapes_file_text():
    evil = "<img src=x onerror=alert(1)>"
    steps = _steps(("agent.decision", {"decision": evil, "rationale": evil}))
    html = _story_driver(
        f"console.log(storyHTML(buildStory({steps},{{goal:{json.dumps(evil)}}}),false));"
    )
    assert "<img" not in html and "&lt;img" in html


def test_story_empty_file_renders_nothing():
    assert _story_driver("console.log(JSON.stringify(storyHTML(buildStory([],{}),false)));").strip() == '""'
