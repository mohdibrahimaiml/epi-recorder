"""`epi witness check` audits a hosted inbox: chain, checkpoints, Rekor."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from epi_cli.witness import app


def _chain(payloads: list[str], times: list[str]) -> list[dict]:
    prev = "GENESIS"
    out = []
    for i, (raw, at) in enumerate(zip(payloads, times)):
        inner = hashlib.sha256(raw.encode()).hexdigest()
        h = hashlib.sha256(f"{prev}{inner}{at}".encode()).hexdigest()
        out.append(
            {
                "seq": i + 1,
                "received_at": at,
                "payload_raw": raw,
                "prev_hash": prev,
                "entry_hash": h,
            }
        )
        prev = h
    return out


def _fixtures():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    witness_priv = Ed25519PrivateKey.generate()
    witness_pub = witness_priv.public_key().public_bytes_raw().hex()
    anchor_priv = ec.generate_private_key(ec.SECP256R1())
    anchor_pem = anchor_priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()

    raws = [
        '{"schema":"epi-witness/v1","n":1}',
        '{"schema":"epi-witness/v1","n":2}',
        '{"schema":"epi-witness/v1","n":3}',
    ]
    times = ["2026-10-14T23:00:00Z", "2026-10-15T00:30:00Z", "2026-10-15T01:30:00Z"]
    envelopes = _chain(raws, times)
    by_day: dict[str, dict] = {}
    for e in envelopes:
        day = e["received_at"][:10]
        slot = by_day.setdefault(day, {"count": 0, "head": ""})
        slot["count"] += 1
        slot["head"] = e["entry_hash"]
    cps = []
    for day, info in sorted(by_day.items()):
        canonical = json.dumps(
            {"inbox": "inb_test", "day": day, "count": info["count"], "head_hash": info["head"]},
            separators=(",", ":"),
        ).encode()
        sig = witness_priv.sign(canonical).hex()
        cps.append(
            {
                "inbox_id": "inb_test",
                "day": day,
                "count": info["count"],
                "head_hash": info["head"],
                "signature": sig,
                "signed_at": "2026-10-16T00:05:00Z",
                "rekor_uuid": f"uuid-{day}",
                "rekor_log_index": 7,
                "tsa_token_b64": "AA==",
            }
        )
    chain_text = "\n".join(json.dumps(e) for e in envelopes) + "\n"
    export_text = "\n".join(raws) + "\n"
    cp_doc = {"inbox": "inb_test", "checkpoints": cps}
    keys_doc = {"witness_ed25519_pub_hex": witness_pub, "anchor_p256_pem": anchor_pem}
    rekor = {}
    for cp in cps:
        canonical = json.dumps(
            {
                "inbox": "inb_test",
                "day": cp["day"],
                "count": cp["count"],
                "head_hash": cp["head_hash"],
            },
            separators=(",", ":"),
        ).encode()
        anchor_sig = anchor_priv.sign(canonical, ec.ECDSA(hashes.SHA256()))
        digest = hashlib.sha256(canonical).hexdigest()
        body = {
            "spec": {
                "data": {"hash": {"algorithm": "sha256", "value": digest}},
                "signature": {"content": base64.b64encode(anchor_sig).decode()},
            },
            "verification": {"inclusionProof": {"checkpoint": "rekor.sigstore.dev"}},
        }
        rekor[cp["rekor_uuid"]] = {"body": base64.b64encode(json.dumps(body).encode()).decode()}
    return envelopes, chain_text, export_text, cp_doc, keys_doc, rekor


class _Resp:
    def __init__(self, payload: bytes):
        self._buf = io.BytesIO(payload)

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _online_handler(cp_doc, chain_text, keys_doc, rekor):
    def handle(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.endswith("/checkpoints"):
            return _Resp(json.dumps(cp_doc).encode())
        if url.endswith("/chain.jsonl"):
            return _Resp(chain_text.encode())
        if url.endswith("/.well-known/epi-witness-key.json"):
            return _Resp(json.dumps(keys_doc).encode())
        if "rekor.sigstore.dev/api/v1/log/entries/" in url:
            uuid = url.rsplit("/", 1)[-1]
            return _Resp(json.dumps(rekor[uuid]).encode())
        raise AssertionError(f"unexpected URL {url}")

    return handle


def _invoke(args: list[str]):
    return CliRunner().invoke(app, args)


URL = "https://cloud.epilabs.org/w/inb_test"


def _net(cp_doc, chain_text, keys_doc, rekor):
    handler = _online_handler(cp_doc, chain_text, keys_doc, rekor)
    return patch("urllib.request.urlopen", side_effect=handler)


def test_check_online_happy_path():
    envelopes, chain_text, export_text, cp_doc, keys_doc, rekor = _fixtures()
    with _net(cp_doc, chain_text, keys_doc, rekor):
        result = _invoke(["check", "--inbox-url", URL])
    assert result.exit_code == 0, result.output
    assert "OK: hosted witness audited" in result.output
    assert "Chain: 3 entries recomputed" in result.output


def test_check_catches_edited_line():
    envelopes, chain_text, export_text, cp_doc, keys_doc, rekor = _fixtures()
    bad = chain_text.replace('\\"n\\":2', '\\"n\\":2 ')
    with _net(cp_doc, bad, keys_doc, rekor):
        result = _invoke(["check", "--inbox-url", URL])
    assert result.exit_code == 1, result.output
    assert "FAIL" in result.output


def test_check_catches_reorder_and_bad_signature():
    envelopes, chain_text, export_text, cp_doc, keys_doc, rekor = _fixtures()
    lines = chain_text.strip().split("\n")
    reordered = "\n".join([lines[1], lines[0], lines[2]]) + "\n"
    with _net(cp_doc, reordered, keys_doc, rekor):
        assert _invoke(["check", "--inbox-url", URL]).exit_code == 1
    cp_doc["checkpoints"][0]["signature"] = "00" * 64
    with _net(cp_doc, chain_text, keys_doc, rekor):
        result = _invoke(["check", "--inbox-url", URL])
    assert result.exit_code == 1
    assert "signature INVALID" in result.output


def test_check_offline_with_files(tmp_path: Path):
    envelopes, chain_text, export_text, cp_doc, keys_doc, rekor = _fixtures()
    chain_f = tmp_path / "chain.jsonl"
    chain_f.write_text(chain_text)
    cp_f = tmp_path / "checkpoints.json"
    cp_norekor = [{**c, "rekor_uuid": None} for c in cp_doc["checkpoints"]]
    cp_f.write_text(json.dumps({"inbox": "inb_test", "checkpoints": cp_norekor}))
    # witness key unknown offline -> fails closed; now test export mismatch instead
    exp_f = tmp_path / "export.jsonl"
    exp_f.write_text("tampered\n")
    with patch("urllib.request.urlopen", side_effect=AssertionError("no network in offline mode")):
        result = _invoke(
            ["check", "--inbox-url", "https://cloud.epilabs.org/w/inb_test", "--offline",
             "--chain", str(chain_f), "--checkpoints", str(cp_f), "--export", str(exp_f)]
        )
    assert result.exit_code == 1
    assert "export.jsonl does not match" in result.output


def test_check_rejects_http_without_flag():
    result = _invoke(["check", "--inbox-url", "http://127.0.0.1:8787/w/inb_test"])
    assert result.exit_code == 2
