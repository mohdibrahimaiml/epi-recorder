"""Browser preimage must keep unknown manifest fields (forward compatibility).

A future version may add a manifest field. The 4.10.0 verifier hashes the
manifest as stored, so the browser preimage must include that field rather than
re-serializing a model that drops it. This mirrors the CLI test.
"""

from __future__ import annotations

import http.server
import json
import shutil
import threading
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.schemas import ManifestModel
from epi_core.serialize import get_canonical_hash
from epi_core.trust import sign_manifest

pytestmark = pytest.mark.browser


def _with_page(config):  # type: ignore[no-untyped-def]
    playwright = pytest.importorskip("playwright.sync_api")
    headless = bool(config.getoption("--headless", default=True))
    manager = playwright.sync_playwright()
    started = manager.__enter__()
    try:
        try:
            browser = started.chromium.launch(headless=headless)
        except Exception as exc:  # pragma: no cover - local browser install
            pytest.skip(f"Playwright Chromium is not installed or cannot launch: {exc}")
        return manager, browser, browser.new_page()
    except Exception:
        manager.__exit__(None, None, None)
        raise


def _serve(directory: Path):  # type: ignore[no-untyped-def]
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, *args):  # noqa: ANN002
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def test_browser_hashes_an_unknown_extra_field(tmp_path: Path, request) -> None:
    website = Path(__file__).resolve().parents[2] / "website"
    served = tmp_path / "served"
    served.mkdir()
    shutil.copyfile(website / "js" / "epi-manifest-preimage.js", served / "epi-manifest-preimage.js")
    (served / "index.html").write_text("<!doctype html><title>preimage</title>", encoding="utf-8")

    key = Ed25519PrivateKey.generate()
    signed = sign_manifest(
        ManifestModel(goal="future", future_field={"new": [1, 2, 3]}),
        key,
        "future",
    )
    raw = signed.model_dump_json()
    assert json.loads(raw)["future_field"] == {"new": [1, 2, 3]}

    python_hash = get_canonical_hash(signed, exclude_fields={"signature"})
    public_hex = signed.public_key

    server, base = _serve(served)
    manager, browser, page = _with_page(request.config)
    try:
        page.goto(base + "/index.html", wait_until="load")
        page.add_script_tag(url=base + "/epi-manifest-preimage.js")
        result = page.evaluate(
            """async ([raw, sig, pub]) => {
                const hash = await epiComputeManifestHash(raw);
                const r = await epiVerifyEd25519(sig, pub, hash);
                return { hash: hash, valid: r.valid, msg: r.msg };
            }""",
            [raw, signed.signature, public_hex],
        )
    finally:
        browser.close()
        manager.__exit__(None, None, None)
        server.shutdown()

    assert result["hash"] == python_hash
    assert result["valid"] is True, result
