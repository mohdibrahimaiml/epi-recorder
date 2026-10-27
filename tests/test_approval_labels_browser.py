"""Step 3c: no browser screen may present an approval as a verified human one.

Six files are built with the real SDK / CLI / gateway export path, dropped on
the real /verify/ page in Chromium, and their rendered text is asserted.
"""

from __future__ import annotations

import base64
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.container import EPIContainer
from epi_core.keys import key_fingerprint
from epi_core.review import ReviewRecord, add_review_to_artifact, make_approval_entry
from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now
from epi_core.trust import sign_manifest
from tests.helpers.artifacts import rewrite_legacy_member

pytestmark = pytest.mark.browser

REPO = Path(__file__).resolve().parents[1]

DROP_JS = """(async (b64) => {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const dt = new DataTransfer();
  dt.items.add(new File([new Blob([bytes], { type: 'application/octet-stream' })], 'case.epi'));
  const dz = document.getElementById('dropZoneEl');
  dz.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
  return 'dropped';
})"""


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
            b = p.chromium.launch(args=["--no-sandbox"])
        except Exception:
            pytest.skip("no chromium available")
        yield b
        b.close()


def _pubhex(key) -> str:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def _render(site, browser, epi_path: Path) -> str:
    b64 = base64.b64encode(epi_path.read_bytes()).decode("ascii")
    ctx = browser.new_context()
    pg = ctx.new_page()
    try:
        pg.goto(site + "/verify/")
        pg.wait_for_selector("#dropZoneEl", timeout=15000)
        assert pg.evaluate(DROP_JS + f"('{b64}')") == "dropped"
        pg.wait_for_function(
            "() => document.querySelector('#dropResult').textContent.length > 20",
            timeout=30000,
        )
        return pg.locator("#dropResult").inner_text()
    finally:
        ctx.close()


def _sealed(tmp_path: Path, name: str) -> tuple[Path, Ed25519PrivateKey]:
    """A sealed artifact whose sealing key we know (real container + sign)."""
    source = tmp_path / f"{name}.src"
    source.mkdir(parents=True, exist_ok=True)
    (source / "steps.jsonl").write_text(
        '{"index":0,"kind":"agent.decision","content":{"decision":"approve"}}\n',
        encoding="utf-8",
    )
    key = Ed25519PrivateKey.generate()
    path = tmp_path / name
    EPIContainer.pack(
        source,
        ManifestModel(workflow_id=__import__("uuid").uuid4(), created_at=utc_now(), cli_command="pytest"),
        path,
        signer_function=lambda manifest: sign_manifest(manifest, key, "test"),
        preserve_generated=True,
        generate_analysis=False,
    )
    return path, key


def _with_approval(
    tmp_path: Path,
    name: str,
    *,
    signing_key: Ed25519PrivateKey | None = None,
    approver_name: str = "alice@bank.com",
    sealing_key: Ed25519PrivateKey | None = None,
) -> Path:
    path, seal = _sealed(tmp_path, name)
    approver = signing_key or Ed25519PrivateKey.generate()
    entry = make_approval_entry(
        approval_id="refund-7",
        decision="approve",
        action="refund REF-7",
        reason="checked against ledger",
        approver_name=approver_name,
        key_fingerprint_hex=key_fingerprint(_pubhex(approver), grouped=False),
    )
    record = ReviewRecord(
        reviewed_by=approver_name,
        reviews=[entry],
        reviewer_identity={
            "type": "email",
            "value": approver_name,
            "role": "Approver",
            "org": "Unknown",
            "verified": False,
        },
    )
    add_review_to_artifact(path, record, private_key=sealing_key or approver)
    return path


def _agent_run(tmp_path: Path, name: str, response_content: dict) -> Path:
    request = {
        "index": 1,
        "kind": "agent.approval.request",
        "content": {"action": "refund REF-7", "approval_id": "refund-7"},
    }
    step = {
        "index": 2,
        "kind": "agent.approval.response",
        "content": {"action": "refund REF-7", "approved": True, **response_content},
    }
    source = tmp_path / f"{name}.src"
    source.mkdir(parents=True, exist_ok=True)
    (source / "steps.jsonl").write_text(
        '{"index":0,"kind":"agent.decision","content":{"decision":"approve"}}\n'
        + __import__("json").dumps(request)
        + "\n"
        + __import__("json").dumps(step)
        + "\n",
        encoding="utf-8",
    )
    path = tmp_path / name
    key = Ed25519PrivateKey.generate()
    EPIContainer.pack(
        source,
        ManifestModel(workflow_id=__import__("uuid").uuid4(), created_at=utc_now(), cli_command="pytest"),
        path,
        signer_function=lambda manifest: sign_manifest(manifest, key, "test"),
        preserve_generated=True,
        generate_analysis=False,
    )
    return path


# ── the six cases ────────────────────────────────────────────────────────────


def test_agent_reported_approval_is_labelled(site, browser, tmp_path):
    epi = _agent_run(tmp_path, "agent.epi", {"reviewer": "manager@bank.com"})
    text = _render(site, browser, epi)
    assert "Agent-reported: manager@bank.com approved refund REF-7" in text, text
    assert "verified human approval" not in text.lower()
    assert "human-signed" not in text.lower()


def test_gateway_link_click_is_not_a_signed_approval(site, browser, tmp_path):
    epi = _agent_run(
        tmp_path,
        "gateway.epi",
        {"reviewer": "approval-link (identity not verified)", "approval_source": "gateway_link_unsigned"},
    )
    text = _render(site, browser, epi)
    assert "Gateway link click (not a signed approval)" in text, text
    assert "Agent-reported: approval-link" not in text, text


def test_signed_approval_shows_fingerprint_and_claimed_name(site, browser, tmp_path):
    epi = _with_approval(tmp_path, "signed.epi")
    text = _render(site, browser, epi)
    assert "Signed approval (approve) for approval \"refund-7\"" in text, text
    assert "key fingerprint" in text, text
    assert "epi approvers add" in text, text
    assert "epi verify --require-human-approval" in text, text
    assert "(claimed name: alice@bank.com)" in text, text


def test_cli_written_approval_is_labelled(site, browser, tmp_path):
    """The signed-approval label must work on a record the real CLI wrote."""
    import os
    import subprocess
    import sys

    epi = _agent_run(tmp_path, "cli.epi", {})
    home = tmp_path / "approver-home"
    env = dict(
        os.environ,
        EPI_HOME=str(home),
        EPI_KEYS_DIR=str(home / "keys"),
        EPI_APPROVER_KEYS_DIR=str(home / "approver_keys"),
        EPI_TRUSTED_APPROVERS_DIR=str(home / "trusted_approvers"),
        EPI_KEY_PASSWORD="test-password",
        EPI_NOTARIZE="0",
        PYTHONPATH=str(REPO),
    )
    keygen = subprocess.run(
        [sys.executable, "-m", "epi_cli", "approvers", "keygen", "--name", "alice@bank.com"],
        env=env, capture_output=True, text=True,
    )
    assert keygen.returncode == 0, keygen.stdout + keygen.stderr
    approve = subprocess.run(
        [
            sys.executable, "-m", "epi_cli", "review", str(epi), "approve",
            "--approval-id", "refund-7", "--decision", "approve",
            "--as", "alice@bank.com", "--yes",
        ],
        env=env, capture_output=True, text=True,
    )
    assert approve.returncode == 0, approve.stdout + approve.stderr

    text = _render(site, browser, epi)
    assert 'Signed approval (approve) for approval "refund-7"' in text, text
    assert "key fingerprint" in text, text
    assert "(claimed name: alice@bank.com)" in text, text


def test_embedded_name_is_only_a_claim(site, browser, tmp_path):
    epi = _with_approval(tmp_path, "spoof.epi", approver_name="ceo@bank.com")
    text = _render(site, browser, epi)
    assert "(claimed name: ceo@bank.com)" in text, text
    # Never shown as a fact: the only occurrence is inside the claimed-name note.
    assert text.replace("(claimed name: ceo@bank.com)", "").count("ceo@bank.com") == 0, text


def test_tampered_approval_record_is_invalid(site, browser, tmp_path):
    epi = _with_approval(tmp_path, "tampered.epi")
    member = sorted(
        name for name in EPIContainer.list_members(epi)
        if name.startswith("reviews/") and name.endswith(".json")
    )[-1]
    payload = EPIContainer.read_member_json(epi, member)
    payload["reviews"][0]["decision"] = "deny"  # one field changed, signature no longer covers it
    rewrite_legacy_member(epi, member, __import__("json").dumps(payload).encode("utf-8"))

    text = _render(site, browser, epi)
    assert "Invalid signed approval (does not match this file)" in text, text
    assert "alice@bank.com" not in text, text


def test_approval_signed_by_the_sealing_key_is_not_independent(site, browser, tmp_path):
    path, seal = _sealed(tmp_path, "sealed.epi")
    entry = make_approval_entry(
        approval_id="refund-7",
        decision="approve",
        action="refund REF-7",
        reason="ok",
        approver_name="the-agent",
        key_fingerprint_hex=key_fingerprint(_pubhex(seal), grouped=False),
    )
    record = ReviewRecord(
        reviewed_by="the-agent",
        reviews=[entry],
        reviewer_identity={"type": "name", "value": "the-agent", "verified": False},
    )
    add_review_to_artifact(path, record, private_key=seal)

    text = _render(site, browser, path)
    assert "Signed by the same key that sealed the run (not independent of the agent)" in text, text


VIEWER_SOURCES = [
    REPO / "web_viewer" / "app.js",
    REPO / "epi_viewer_static" / "app.js",
    REPO / "epi-official" / "epi-viewer" / "app.js",
]


def test_viewers_label_approvals_honestly():
    """The offline viewers render the same honest labels (source guard)."""
    for path in VIEWER_SOURCES:
        src = path.read_text(encoding="utf-8")
        assert "Agent-reported: " in src, path
        assert "Gateway link click (not a signed approval)" in src, path
        assert "Gateway link click by a logged-in user (not a signed approval)" in src, path
        assert "approved by human supervisor" not in src, path
        # The old bare "<reviewer> approved" summary is gone.
        assert "return `${reviewer} ${approved ? 'approved'" not in src, path


def test_browser_fingerprint_matches_python(site, browser, tmp_path):
    keys = [Ed25519PrivateKey.generate() for _ in range(3)]
    epi = _agent_run(tmp_path, "fp.epi", {})
    ctx = browser.new_context()
    pg = ctx.new_page()
    try:
        pg.goto(site + "/verify/")
        pg.wait_for_selector("#dropZoneEl", timeout=15000)
        pg.wait_for_function(
            "() => window.epiApprovalLabels && typeof window.epiApprovalLabels.keyFingerprintHex === 'function'",
            timeout=15000,
        )
        for key in keys:
            pub = _pubhex(key)
            got = pg.evaluate("(h) => window.epiApprovalLabels.keyFingerprintHex(h)", pub)
            assert got == key_fingerprint(pub)
    finally:
        ctx.close()
    # keep the fixture referenced so the helper above stays honest about building real files
    assert epi.exists()
