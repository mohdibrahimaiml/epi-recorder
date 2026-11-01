"""The browser's witness digest and verdict match the CLI's, without a browser.

`epi_core.webhook.witness_content_digest` is what the witness payload stores for
a repacked file. If the page computed a different digest, every approved file
would look like a different version. This runs the real page script in Node and
compares the two, then checks the four verdicts.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "docs" / "assets" / "demo-insurance-claim-adjudication.epi"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const crypto = require('crypto');
const el = () => ({ _v:'', set textContent(v){this._v=v;}, get textContent(){return this._v;},
  get innerHTML(){return String(this._v);}, set innerHTML(v){this._v=v;}, style:{}, dataset:{}, children:[],
  classList:{add(){},remove(){},toggle(){}}, addEventListener(){}, appendChild(){}, setAttribute(){},
  getAttribute(){return null;}, querySelector(){return null;}, querySelectorAll(){return [];} });
const document = { readyState:'loading', addEventListener(){}, removeEventListener(){},
  createElement: el, createTextNode:(t)=>({textContent:t}), getElementById(){return null;},
  querySelector(){return null;}, querySelectorAll(){return []}, body:el(), documentElement:el(), head:el() };
const window = { addEventListener(){}, removeEventListener(){}, location:{protocol:'file:',href:'file:///x',search:''},
  localStorage:{getItem(){return null},setItem(){}}, matchMedia(){return{matches:false,addEventListener(){}}} };
const ctx = { document, window, console, navigator:{clipboard:{writeText(){}},userAgent:'node'},
  JSZip:function(){}, Blob:function(){}, FileReader:function(){}, URL,
  setTimeout, clearTimeout, setInterval, clearInterval, TextEncoder, TextDecoder, atob, btoa,
  fetch:()=>Promise.resolve({ok:false,json:()=>Promise.resolve({})}),
  crypto: crypto.webcrypto, location: window.location, localStorage: window.localStorage };
ctx.globalThis = ctx; ctx.self = ctx; ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('website/js/epi-manifest-preimage.js','utf8'), ctx, {filename:'preimage.js'});
vm.runInContext(fs.readFileSync('website/js/home-verify.js','utf8'), ctx, {filename:'home-verify.js'});

(async () => {
  const manifest = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const digest = await ctx.epiWitnessContentDigest(manifest);
  const verdict = ctx.epiWitnessVerdict;
  const fileSha = 'a'.repeat(64), manifestHash = 'b'.repeat(64);
  const line = { workflow_id: manifest.workflow_id, manifest_hash: manifestHash,
                 file_sha256: fileSha, goal: manifest.goal, received_at: '2026-10-30T10:00:00+00:00' };
  const log = { signed: false, reports: [line] };
  const otherRun = Object.assign({}, manifest, { workflow_id: '00000000-0000-0000-0000-000000000000' });
  const unrelated = Object.assign({}, manifest, { workflow_id: '11111111-1111-1111-1111-111111111111', goal: 'something else' });
  console.log(JSON.stringify({
    digest,
    exact: verdict(manifest, manifestHash, fileSha, null, log).status,
    differentBytes: verdict(manifest, 'c'.repeat(64), 'd'.repeat(64), null, log).status,
    otherRun: verdict(otherRun, 'e'.repeat(64), 'f'.repeat(64), null, log).status,
    otherRunDetail: verdict(otherRun, 'e'.repeat(64), 'f'.repeat(64), null, log).detail,
    unrelated: verdict(unrelated, '1'.repeat(64), '2'.repeat(64), null, log).status,
    signed: verdict(manifest, manifestHash, fileSha, null, Object.assign({}, log, {signed: true})).status,
  }));
})();
"""


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    raw = SAMPLE.read_bytes()
    marker = b"\n<!-- EPI_ZIP_PAYLOAD_START -->\n"
    index = raw.find(marker)
    with zipfile.ZipFile(io.BytesIO(raw[index + len(marker):] if index >= 0 else raw)) as zf:
        manifest = json.loads(zf.read("manifest.json"))

    work = tmp_path_factory.mktemp("witness-js")
    manifest_path = work / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    harness = work / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")

    run = subprocess.run(
        ["node", str(harness), str(manifest_path)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_browser_content_digest_matches_python(result):
    from epi_core.container import EPIContainer
    from epi_core.webhook import witness_content_digest

    expected = witness_content_digest(EPIContainer.read_manifest(SAMPLE))
    assert result["digest"] == expected


def test_browser_verdicts_match_the_cli(result):
    assert result["exact"] == "WITNESSED"
    assert result["differentBytes"] == "MISMATCH"
    assert result["otherRun"] == "MISMATCH"
    assert "a different version of" in result["otherRunDetail"]
    assert result["unrelated"] == "NOT IN WITNESS LOG"
    assert result["signed"] == "NOT CONFIRMED"
