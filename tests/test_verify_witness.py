"""Browser verifier + the customer's witness log.

The page can now take `received.jsonl` next to the `.epi`. These tests drive it
the way a person does: drop the file, drop the log, read the verdict. The forged
artifact is a genuine re-seal (rebuilt chain, recomputed hashes, valid
signature, same claim, new workflow id), so only the log can tell.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import pathlib
import shutil
import tempfile
import threading
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest

pytestmark = pytest.mark.browser

REPO = pathlib.Path(__file__).resolve().parents[1]
GENUINE_URL = "/assets/demo/demo-insurance-claim-adjudication.epi"
GENUINE = REPO / "website" / "assets" / "demo" / "demo-insurance-claim-adjudication.epi"

DROP_JS = """async ({ url, logText, forgedB64 }) => {
  const dropOn = (id, blob, name) => {
    const dt = new DataTransfer();
    dt.items.add(new File([blob], name));
    const zone = document.getElementById(id);
    zone.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
  };
  let bytes;
  if (forgedB64) {
    const bin = atob(forgedB64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    bytes = arr;
  } else {
    bytes = await (await fetch(url)).arrayBuffer();
  }
  dropOn('dropZoneEl', new Blob([bytes]), 'case.epi');
  if (logText !== null) dropOn('witnessZoneEl', new Blob([logText], { type: 'application/x-ndjson' }), 'received.jsonl');
  return 'dropped';
}"""


@pytest.fixture()
def site():
    handler = partial(SimpleHTTPRequestHandler, directory=str(REPO / "website"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            instance = p.chromium.launch(args=["--no-sandbox"])
        except Exception:
            pytest.skip("no chromium available")
        yield instance
        instance.close()


def _manifest(epi: pathlib.Path) -> dict:
    raw = epi.read_bytes()
    marker = b"\n<!-- EPI_ZIP_PAYLOAD_START -->\n"
    i = raw.find(marker)
    with zipfile.ZipFile(io.BytesIO(raw[i + len(marker):] if i >= 0 else raw)) as zf:
        return json.loads(zf.read("manifest.json"))


def _witness_line(epi: pathlib.Path) -> str:
    """The hash-only line the customer's receiver would have written."""
    from epi_core.container import EPIContainer
    from epi_core.serialize import get_canonical_hash
    from epi_core.webhook import witness_content_digest

    manifest_model = EPIContainer.read_manifest(epi)
    manifest = _manifest(epi)
    return json.dumps(
        {
            "schema": "epi-witness/v1",
            "type": "epi.sealed",
            "workflow_id": str(manifest["workflow_id"]),
            "manifest_hash": get_canonical_hash(manifest_model, exclude_fields=["signature"]),
            "file_sha256": hashlib.sha256(epi.read_bytes()).hexdigest(),
            "content_digest": witness_content_digest(manifest_model),
            "goal": manifest.get("goal"),
            "steps": manifest.get("total_steps") or 1,
            "sealed_at": manifest.get("created_at"),
            "received_at": "2026-10-30T10:00:00+00:00",
        }
    )


def _forge(src: pathlib.Path) -> bytes:
    """Re-seal the same claim with a changed decision: valid signature, new run id."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from epi_core.container import EPIContainer
    from epi_core.schemas import StepModel
    from epi_core.serialize import get_canonical_hash
    from epi_core.trust import sign_manifest

    manifest = EPIContainer.read_manifest(src)
    steps = EPIContainer.read_steps(src)
    for step in steps:
        if step.get("kind") in ("agent.decision", "decision"):
            content = dict(step.get("content") or {})
            content["decision"] = "DENY"
            content["determination"] = "DENY"
            content["rationale"] = "Outside the policy window."
            step["content"] = content

    previous = "CHAIN_START"
    rebuilt = []
    for step in steps:
        model = StepModel(
            index=step["index"],
            timestamp=step["timestamp"],
            kind=step["kind"],
            content=step["content"],
            prev_hash=previous,
        )
        rebuilt.append(model.model_dump(mode="json"))
        previous = get_canonical_hash(model, format="json")

    work = pathlib.Path(tempfile.mkdtemp(prefix="epi_browser_forge_"))
    try:
        payload = work / "payload.zip"
        EPIContainer.extract_inner_payload(src, payload)
        source = work / "payload"
        with zipfile.ZipFile(payload) as zf:
            zf.extractall(source)
        (source / "steps.jsonl").write_text(
            "\n".join(json.dumps(step) for step in rebuilt) + "\n", encoding="utf-8"
        )
        for generated in ("manifest.json", "VERIFY.txt", "viewer.html"):
            path = source / generated
            if path.exists():
                path.unlink()
        for directory in ("reviews", "review_timestamps"):
            shutil.rmtree(source / directory, ignore_errors=True)
        for name in ("review.json", "review_index.json", "artifacts/manifest.json"):
            path = source / name
            if path.exists():
                path.unlink()

        # Same claim, new run: the vendor "re-ran" it.
        manifest.workflow_id = uuid4()
        key = Ed25519PrivateKey.generate()
        out = work / "forged.epi"
        EPIContainer.pack(
            source,
            manifest,
            out,
            signer_function=lambda model: sign_manifest(model, key, "vendor"),
            preserve_generated=True,
            generate_analysis=False,
            notarize=False,
            embed_viewer=False,
        )
        return out.read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _drop(pg, *, log: str | None, forged: bytes | None = None) -> None:
    pg.evaluate(
        DROP_JS,
        {
            "url": GENUINE_URL,
            "logText": log,
            "forgedB64": base64.b64encode(forged).decode("ascii") if forged else "",
        },
    )


def _wait_result(pg) -> str:
    pg.wait_for_function(
        "() => document.querySelector('#dropResult').textContent.length > 20", timeout=30000
    )
    if "WITNESS" in (pg.locator("#witnessStatus").inner_text() if pg.locator("#witnessStatus").is_visible() else ""):
        pass
    return pg.locator("#dropResult").inner_text()


def test_genuine_file_with_the_customers_log_is_witnessed(site, browser) -> None:
    ctx = browser.new_context()
    pg = ctx.new_page()
    try:
        pg.goto(site + "/verify/")
        pg.wait_for_selector("#witnessZoneEl", timeout=15000)
        _drop(pg, log=_witness_line(GENUINE))
        pg.wait_for_function(
            "() => document.querySelector('#dropResult').textContent.indexOf('Witness') >= 0",
            timeout=30000,
        )
        text = pg.locator("#dropResult").inner_text()
        assert "matches your log" in text, text[:900]
        assert "not the version" not in text.lower(), text[:900]
    finally:
        ctx.close()


def test_forged_file_with_the_customers_log_is_caught(site, browser) -> None:
    forged = _forge(GENUINE)
    ctx = browser.new_context()
    pg = ctx.new_page()
    try:
        pg.goto(site + "/verify/")
        pg.wait_for_selector("#witnessZoneEl", timeout=15000)
        _drop(pg, log=_witness_line(GENUINE), forged=forged)
        pg.wait_for_function(
            "() => document.querySelector('#dropResult').textContent.length > 20", timeout=30000
        )
        text = pg.locator("#dropResult").inner_text()
        assert "not the version your witness recorded" in text.lower(), text[:900]
        assert "different version" in text.lower(), text[:1200]
    finally:
        ctx.close()


def test_a_signed_log_is_not_called_verified_without_a_pinned_key(site, browser) -> None:
    line = json.loads(_witness_line(GENUINE))
    signed = json.dumps(
        {
            "payload_raw": json.dumps(line),
            "receipt": {"received_at": "2026-10-30T10:00:05+00:00", "signature": "ed25519:00:00"},
            "received_at": "2026-10-30T10:00:05+00:00",
        }
    )
    ctx = browser.new_context()
    pg = ctx.new_page()
    try:
        pg.goto(site + "/verify/")
        pg.wait_for_selector("#witnessZoneEl", timeout=15000)
        _drop(pg, log=signed)
        pg.wait_for_function(
            "() => document.querySelector('#dropResult').textContent.length > 20", timeout=30000
        )
        text = pg.locator("#dropResult").inner_text()
        assert "signed receipts" in text.lower(), text[:900]
        assert "matches your log" not in text.lower(), text[:900]
    finally:
        ctx.close()


def test_without_a_log_the_page_makes_no_witness_claim(site, browser) -> None:
    ctx = browser.new_context()
    pg = ctx.new_page()
    try:
        pg.goto(site + "/verify/")
        pg.wait_for_selector("#dropZoneEl", timeout=15000)
        _drop(pg, log=None)
        pg.wait_for_function(
            "() => document.querySelector('#dropResult').textContent.length > 20", timeout=30000
        )
        text = pg.locator("#dropResult").inner_text()
        assert "witness" not in text.lower(), text[:900]
        assert "hasn't been changed since it was sealed" in text, text[:900]
    finally:
        ctx.close()
