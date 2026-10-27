"""Step 4: the public checkpoint mirror cannot quietly rewrite history.

No network: a local directory and a local HTTP server stand in for the mirror
and for the live witness.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_cli.witness import _compare_mirror, _load_mirror

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "mirror_witness_checkpoints.py"
INBOX = "inb_test"


def _pub(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def _canonical(inbox: str, cp: dict) -> bytes:
    return json.dumps(
        {"inbox": inbox, "day": cp["day"], "count": cp["count"], "head_hash": cp["head_hash"]},
        separators=(",", ":"),
    ).encode()


def _cp(key: Ed25519PrivateKey, day: str, count: int, head: str) -> dict:
    cp = {"day": day, "count": count, "head_hash": head}
    cp["signature"] = key.sign(_canonical(INBOX, cp)).hex()
    return cp


def _docs(key: Ed25519PrivateKey, cps: list[dict], *, pub: str | None = None):
    return (
        {"inbox": INBOX, "checkpoints": cps},
        {"witness_ed25519_pub_hex": pub or _pub(key)},
    )


# ── comparison (cases 1-4, 7) ────────────────────────────────────────────────


def test_mirror_matches_live(witness_key):
    cps = [_cp(witness_key, "2026-10-20", 3, "a" * 64), _cp(witness_key, "2026-10-21", 2, "b" * 64)]
    live_doc, live_keys = _docs(witness_key, cps)
    mirror_doc, mirror_keys = _docs(witness_key, cps)
    assert _compare_mirror(
        live_doc["checkpoints"], mirror_doc["checkpoints"], live_keys, mirror_keys
    ) == []


def test_live_day_changed_on_the_live_side_fails(witness_key):
    past = _cp(witness_key, "2026-10-20", 3, "a" * 64)
    live_doc, live_keys = _docs(witness_key, [_cp(witness_key, "2026-10-20", 4, "c" * 64)])
    mirror_doc, mirror_keys = _docs(witness_key, [past])
    failures = _compare_mirror(
        live_doc["checkpoints"], mirror_doc["checkpoints"], live_keys, mirror_keys
    )
    assert any("history rewritten" in f for f in failures), failures


def test_past_day_deleted_on_the_live_side_fails(witness_key):
    past = _cp(witness_key, "2026-10-20", 3, "a" * 64)
    live_doc, live_keys = _docs(witness_key, [])
    mirror_doc, mirror_keys = _docs(witness_key, [past])
    failures = _compare_mirror(
        live_doc["checkpoints"], mirror_doc["checkpoints"], live_keys, mirror_keys
    )
    assert any("missing from the live witness" in f for f in failures), failures


def test_swapped_signature_fails(witness_key):
    cp = _cp(witness_key, "2026-10-20", 3, "a" * 64)
    tampered = dict(cp, signature=_cp(witness_key, "2026-10-20", 3, "b" * 64)["signature"])
    live_doc, live_keys = _docs(witness_key, [cp])
    mirror_doc, mirror_keys = _docs(witness_key, [tampered])
    failures = _compare_mirror(
        live_doc["checkpoints"], mirror_doc["checkpoints"], live_keys, mirror_keys
    )
    assert any("signature differs" in f for f in failures), failures


def test_new_day_only_on_the_live_side_is_fine(witness_key):
    past = _cp(witness_key, "2026-10-20", 3, "a" * 64)
    live_doc, live_keys = _docs(witness_key, [past, _cp(witness_key, "2026-10-21", 1, "d" * 64)])
    mirror_doc, mirror_keys = _docs(witness_key, [past])
    assert _compare_mirror(
        live_doc["checkpoints"], mirror_doc["checkpoints"], live_keys, mirror_keys
    ) == []


def test_changed_witness_key_fails_without_rotation(witness_key):
    other = Ed25519PrivateKey.generate()
    cp = _cp(witness_key, "2026-10-20", 3, "a" * 64)
    live_doc, live_keys = _docs(witness_key, [cp])
    mirror_doc, mirror_keys = _docs(witness_key, [cp], pub=_pub(other))
    failures = _compare_mirror(
        live_doc["checkpoints"], mirror_doc["checkpoints"], live_keys, mirror_keys
    )
    assert any("key changed without a key-rotation entry" in f for f in failures), failures


def test_changed_witness_key_is_fine_when_rotation_is_documented(witness_key):
    old = Ed25519PrivateKey.generate()
    cp = _cp(witness_key, "2026-10-20", 3, "a" * 64)
    live_doc, live_keys = _docs(witness_key, [cp])
    live_keys["previous_witness_ed25519_pub_hexes"] = [_pub(old)]
    mirror_doc, mirror_keys = _docs(witness_key, [cp], pub=_pub(old))
    assert _compare_mirror(
        live_doc["checkpoints"], mirror_doc["checkpoints"], live_keys, mirror_keys
    ) == []


# ── the mirror script (cases 5, 6) ──────────────────────────────────────────


def _serve(pages: dict[str, bytes]) -> tuple[ThreadingHTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            body = pages.get(self.path.split("?")[0])
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def _live_pages(inbox: str, cps: list[dict], pub_hex: str) -> dict[str, bytes]:
    return {
        "/.well-known/epi-witness-key.json": json.dumps(
            {"witness_ed25519_pub_hex": pub_hex}
        ).encode(),
        f"/w/{inbox}/checkpoints": json.dumps({"inbox": inbox, "checkpoints": cps}).encode(),
    }


def _run_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


def test_script_twice_writes_no_duplicates(tmp_path, witness_key):
    cp = _cp(witness_key, "2026-10-20", 3, "a" * 64)
    server, url = _serve(_live_pages(INBOX, [cp], _pub(witness_key)))
    try:
        for _ in range(2):
            result = _run_script("--cloud-url", url, "--inboxes", INBOX, "--out", str(tmp_path))
            assert result.returncode == 0, result.stdout + result.stderr
    finally:
        server.shutdown()
        server.server_close()
    doc = json.loads((tmp_path / "checkpoints" / f"{INBOX}.json").read_text(encoding="utf-8"))
    assert [c["day"] for c in doc["checkpoints"]] == ["2026-10-20"]


def test_script_refuses_a_changed_past_day(tmp_path, witness_key):
    day = "2026-10-20"
    server, url = _serve(
        _live_pages(INBOX, [_cp(witness_key, day, 3, "a" * 64)], _pub(witness_key))
    )
    try:
        result = _run_script("--cloud-url", url, "--inboxes", INBOX, "--out", str(tmp_path))
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        server.shutdown()
        server.server_close()
    before = (tmp_path / "checkpoints" / f"{INBOX}.json").read_bytes()

    # The live witness now serves a different head for the same day.
    server, url = _serve(
        _live_pages(INBOX, [_cp(witness_key, day, 4, "c" * 64)], _pub(witness_key))
    )
    try:
        result = _run_script("--cloud-url", url, "--inboxes", INBOX, "--out", str(tmp_path))
    finally:
        server.shutdown()
        server.server_close()

    assert result.returncode == 2, result.stdout + result.stderr
    assert "history change detected" in result.stderr, result.stderr
    assert (tmp_path / "checkpoints" / f"{INBOX}.json").read_bytes() == before


def test_script_refuses_an_invalid_signature(tmp_path, witness_key):
    forged = _cp(witness_key, "2026-10-20", 3, "a" * 64)
    forged["head_hash"] = "b" * 64  # the signature no longer covers this
    server, url = _serve(_live_pages(INBOX, [forged], _pub(witness_key)))
    try:
        result = _run_script("--cloud-url", url, "--inboxes", INBOX, "--out", str(tmp_path))
    finally:
        server.shutdown()
        server.server_close()
    assert result.returncode == 1, result.stdout + result.stderr
    assert "signature INVALID" in result.stderr, result.stderr
    assert not (tmp_path / "checkpoints" / f"{INBOX}.json").exists()


# ── loading the mirror (local dir and HTTP) ─────────────────────────────────


def test_load_mirror_from_a_local_directory(tmp_path, witness_key):
    day = "2026-10-20"
    (tmp_path / "checkpoints").mkdir()
    (tmp_path / "checkpoints" / f"{INBOX}.json").write_text(
        json.dumps({"inbox": INBOX, "checkpoints": [_cp(witness_key, day, 3, "a" * 64)]}),
        encoding="utf-8",
    )
    (tmp_path / "witness-key.json").write_text(
        json.dumps({"witness_ed25519_pub_hex": _pub(witness_key)}), encoding="utf-8"
    )
    doc, keys = _load_mirror(str(tmp_path), INBOX, timeout=1)
    assert doc["checkpoints"][0]["day"] == day
    assert keys["witness_ed25519_pub_hex"] == _pub(witness_key)


def test_load_mirror_over_http(witness_key):
    day = "2026-10-20"
    pages = {
        f"/checkpoints/{INBOX}.json": json.dumps(
            {"inbox": INBOX, "checkpoints": [_cp(witness_key, day, 3, "a" * 64)]}
        ).encode(),
        "/witness-key.json": json.dumps(
            {"witness_ed25519_pub_hex": _pub(witness_key)}
        ).encode(),
    }
    server, url = _serve(pages)
    try:
        doc, keys = _load_mirror(url, INBOX, timeout=5)
    finally:
        server.shutdown()
        server.server_close()
    assert doc["inbox"] == INBOX
    assert keys["witness_ed25519_pub_hex"] == _pub(witness_key)


@pytest.fixture()
def witness_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()
