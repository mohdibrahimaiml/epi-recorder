"""Duplicate JSON keys in manifest.json are refused (red-team F-07).

The Ed25519 signature covers the RFC 8785 canonical manifest, where a
duplicate key collapses to its last value. A duplicate added after sealing
therefore left the signature valid, while a first-wins JSON parser would read a
different ``goal`` or ``decision`` than the one that was verified. EPI never
writes duplicate keys, so every verifier now rejects them: the CLI, the browser
viewer (crypto.js) and epilabs.org/verify (epi-verify-core.js).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_core.container import EPIContainer

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "assets" / "demo-insurance-claim-adjudication.epi"
FAKE = "FAKE VALUE SEEN BY FIRST-WINS PARSERS"
node_required = pytest.mark.skipif(shutil.which("node") is None, reason="node required")


def _tampered_copy(src: Path, dst: Path) -> str:
    """Copy ``src`` with a duplicate of its first manifest key prepended.

    The real value comes last, so last-wins parsers (and the canonical form the
    signature covers) are unchanged; only first-wins parsers see FAKE.
    """
    with zipfile.ZipFile(src) as zin:
        raw = zin.read("manifest.json").decode("utf-8")
        key = "goal" if "goal" in json.loads(raw) else next(iter(json.loads(raw)))
        brace = raw.index("{") + 1
        tampered = raw[:brace] + json.dumps(key) + ": " + json.dumps(FAKE) + ", " + raw[brace:]
        with zipfile.ZipFile(dst, "w") as zout:
            for info in zin.infolist():
                data = tampered.encode("utf-8") if info.filename == "manifest.json" else zin.read(info.filename)
                zout.writestr(info, data)
    return key


@pytest.fixture()
def tampered(tmp_path: Path) -> tuple[Path, str]:
    assert zipfile.is_zipfile(DEMO), "demo must be a plain ZIP .epi"
    out = tmp_path / "duplicate-key.epi"
    return out, _tampered_copy(DEMO, out)


# --- Python parser ---------------------------------------------------------


def test_parser_accepts_manifest_without_duplicates():
    assert EPIContainer._parse_manifest_json('{"a": 1, "b": {"c": [1, {"c": 2}]}}') == {
        "a": 1,
        "b": {"c": [1, {"c": 2}]},
    }


@pytest.mark.parametrize(
    "text",
    [
        '{"goal": "x", "goal": "y"}',
        '{"outer": {"k": 1, "k": 2}}',
        '{"list": [{"k": 1, "k": 2}]}',
        '{"\\u0061": 1, "a": 2}',  # same key once decoded
    ],
)
def test_parser_rejects_duplicates_at_any_depth(text: str):
    with pytest.raises(ValueError, match="duplicate JSON key"):
        EPIContainer._parse_manifest_json(text)


def test_parser_still_reports_invalid_json():
    with pytest.raises(ValueError, match="Invalid JSON in manifest.json"):
        EPIContainer._parse_manifest_json("{not json")


# --- Sealed files ------------------------------------------------------------


def test_untouched_demo_still_reads():
    assert EPIContainer.read_manifest(DEMO).signature


def test_read_manifest_refuses_tampered_file(tampered):
    path, key = tampered
    with pytest.raises(ValueError, match=f"duplicate JSON key '{key}'"):
        EPIContainer.read_manifest(path)


def test_cli_verify_fails_tampered_file(tampered):
    path, key = tampered
    result = CliRunner().invoke(cli_app, ["verify", str(path)])
    assert result.exit_code != 0, result.output
    # Rich wraps to the terminal width (narrower on Windows runners), so
    # compare with line breaks collapsed.
    flat = " ".join(result.output.split())
    assert f"duplicate JSON key '{key}'" in flat, result.output
    assert FAKE not in flat


def test_cli_verify_still_passes_untouched_demo():
    result = CliRunner().invoke(cli_app, ["verify", str(DEMO)])
    assert result.exit_code == 0, result.output[-800:]


# --- Browser verifiers ---------------------------------------------------------


@node_required
def test_website_verifier_refuses_tampered_file(tampered):
    path, key = tampered
    proc = subprocess.run(
        [shutil.which("node"), str(ROOT / "tests" / "helpers" / "verify_epi_node.mjs"), str(path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["manifest"] is False
    assert report["signature"] is False
    assert f"duplicate JSON key '{key}'" in report["message"]


@node_required
def test_website_verifier_still_reads_untouched_demo():
    proc = subprocess.run(
        [shutil.which("node"), str(ROOT / "tests" / "helpers" / "verify_epi_node.mjs"), str(DEMO)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["manifest"] is True
    assert report["integrity"] is True


@node_required
def test_viewer_crypto_js_refuses_duplicate_keys(tmp_path: Path):
    script = tmp_path / "dup.mjs"
    script.write_text(
        f"""
import {{ readFileSync }} from 'node:fs';
import {{ webcrypto }} from 'node:crypto';
if (!globalThis.crypto) globalThis.crypto = webcrypto;
globalThis.window = globalThis; globalThis.self = globalThis;
console.log = () => {{}};
(0, eval)(readFileSync({json.dumps(str(ROOT / "epi_viewer_static" / "crypto.js"))}, 'utf8'));
const out = {{
  plain: epiFindDuplicateJsonKey('{{"a":1,"b":{{"a":2}},"c":[{{"k":1}},{{"k":2}}]}}'),
  top: epiFindDuplicateJsonKey('{{"goal":"x","goal":"y"}}'),
  nested: epiFindDuplicateJsonKey('{{"o":{{"k":1,"k":2}}}}'),
  inString: epiFindDuplicateJsonKey('{{"s":"a,\\\\"a\\\\":1","a":1}}'),
  escaped: epiFindDuplicateJsonKey('{{"\\\\u0061":1,"a":2}}'),
}};
const raw = '{{"signature":"ed25519:k:00","signature":"ed25519:k:11","public_key":"00"}}';
const vr = await verifyManifestSignature(JSON.parse(raw), raw);
process.stdout.write(JSON.stringify({{ ...out, verdict: vr }}));
""",
        encoding="utf-8",
    )
    proc = subprocess.run([shutil.which("node"), str(script)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    assert got["plain"] is None
    assert got["top"] == "goal"
    assert got["nested"] == "k"
    assert got["inString"] is None
    assert got["escaped"] == "a"
    assert got["verdict"]["valid"] is False
    assert "duplicate JSON key 'signature'" in got["verdict"]["reason"]
