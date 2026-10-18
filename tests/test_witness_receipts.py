"""Signed witness receipts (M6 evidence pack) — CLI verification.

Canonical receipt contract (byte-compatibility with the server):
- canonical = JSON.stringify({artifact_sha256, inbox_id, line_sha256,
  received_at, seq}) with EXACTLY this key order, compact separators,
  UTF-8 bytes. Signature = Ed25519 over those bytes, hex-encoded.
- line_sha256 = sha256(payload_raw.encode('utf-8')).hexdigest()
- artifact_sha256 = payload.file_sha256 || payload.manifest_hash
  || payload.content_digest || '' (first present)

Test keys are generated fresh per-test with `cryptography` — never a real key.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from epi_cli.main import app as cli_app

runner = CliRunner()

RECEIVED_AT = "2026-10-16T00:00:00+00:00"
INBOX_ID = "inb_test"


def _hermetic(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "home" / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")
    for key in ("EPI_WITNESS_URL", "EPI_WITNESS_SECRET", "EPI_WITNESS_PUBKEY"):
        monkeypatch.delenv(key, raising=False)
    # Tests assume no trusted key unless they set one: clear package pins
    # (production pins them; hermetic tests must not inherit that trust).
    import epi_core.witness_keys as _wk

    monkeypatch.setattr(_wk, "EPI_WITNESS_PUBKEYS", ())


def _seal(monkeypatch, tmp_path: Path, out: Path) -> Path:
    from epi_recorder import record

    with record(str(out)) as epi:
        epi.log_step("llm.request", {"content": "hello receipts"})
    return out


def _payload_for(epi_path: Path) -> tuple[dict, str, str, str]:
    """Return (payload, payload_raw, manifest_hash, file_sha256) for an .epi."""
    from epi_core.container import EPIContainer
    from epi_core.serialize import get_canonical_hash
    from epi_core.webhook import witness_content_digest

    manifest = EPIContainer.read_manifest(epi_path)
    manifest_hash = get_canonical_hash(manifest, exclude_fields=["signature"])
    file_sha256 = hashlib.sha256(epi_path.read_bytes()).hexdigest()
    try:
        content_digest = witness_content_digest(manifest)
    except Exception:
        content_digest = "0" * 64
    payload = {
        "schema": "epi-witness/v1",
        "type": "epi.sealed",
        "workflow_id": str(manifest.workflow_id),
        "manifest_hash": manifest_hash,
        "file_sha256": file_sha256,
        "content_digest": content_digest,
        "steps": int(manifest.total_steps or 1),
        "sealed_at": RECEIVED_AT,
    }
    payload_raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return payload, payload_raw, manifest_hash, file_sha256


def _fresh_keypair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    from cryptography.hazmat.primitives import serialization

    pub_hex = pub.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    ).hex()
    return priv, pub_hex


def _canonical_bytes(receipt: dict) -> bytes:
    ordered = {
        "artifact_sha256": receipt["artifact_sha256"],
        "inbox_id": receipt["inbox_id"],
        "line_sha256": receipt["line_sha256"],
        "received_at": receipt["received_at"],
        "seq": receipt["seq"],
    }
    return json.dumps(ordered, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sign_receipt(priv, receipt: dict) -> str:
    return priv.sign(_canonical_bytes(receipt)).hex()


def _make_receipt(priv, payload: dict, payload_raw: str, seq: int = 1) -> dict:
    line_sha256 = hashlib.sha256(payload_raw.encode("utf-8")).hexdigest()
    artifact_sha256 = (
        payload.get("file_sha256")
        or payload.get("manifest_hash")
        or payload.get("content_digest")
        or ""
    )
    receipt = {
        "inbox_id": INBOX_ID,
        "seq": seq,
        "line_sha256": line_sha256,
        "artifact_sha256": artifact_sha256,
        "received_at": RECEIVED_AT,
        "signature": "",
    }
    receipt["signature"] = _sign_receipt(priv, receipt)
    return receipt


def _write_signed_doc(path: Path, pub_hex: str | None, payload_raw: str, receipt: dict) -> Path:
    doc = {
        "witness_pubkey": pub_hex,
        "note": "test witness pack",
        "lines": [
            {
                "inbox": INBOX_ID,
                "seq": receipt["seq"],
                "received_at": RECEIVED_AT,
                "payload_raw": payload_raw,
                "receipt": receipt,
            }
        ],
    }
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def _verify_json(epi_path: Path, witness_log: Path, extra: list[str] | None = None):
    args = ["verify", str(epi_path), "--json", "--witness-log", str(witness_log)]
    if extra:
        args.extend(extra)
    result = runner.invoke(cli_app, args)
    assert result.exit_code in (0, 1), result.output
    return result, json.loads(result.output)


def test_valid_signed_doc_is_witnessed(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    payload, payload_raw, _, _ = _payload_for(epi)
    priv, pub_hex = _fresh_keypair()
    receipt = _make_receipt(priv, payload, payload_raw)
    log = _write_signed_doc(tmp_path / "witness.json", pub_hex, payload_raw, receipt)
    result, report = _verify_json(epi, log, extra=["--witness-pubkey", pub_hex])
    assert report["witness"]["status"] == "WITNESSED", report["witness"]
    assert report["witness"]["received_at"] == RECEIVED_AT


def test_self_signed_pack_without_pinned_key_is_not_confirmed(
    monkeypatch, tmp_path: Path
) -> None:
    """The #121 blocker repro: a run never reported, self-stamped with an
    attacker key, verified with the exact README command (strict + offline,
    no pinned key). Must NEVER read WITNESSED — the doc key is not trust."""
    _hermetic(monkeypatch, tmp_path)
    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    payload, payload_raw, _, _ = _payload_for(epi)
    attacker_priv, attacker_pub = _fresh_keypair()
    receipt = _make_receipt(attacker_priv, payload, payload_raw)
    log = _write_signed_doc(tmp_path / "witness.json", attacker_pub, payload_raw, receipt)
    result, report = _verify_json(epi, log, extra=["--policy", "strict", "--offline"])
    assert report["witness"]["status"] == "NOT CONFIRMED", report["witness"]
    assert "NOT CONFIRMED" in report["witness"]["detail"]
    assert "pin" in report["witness"]["detail"].lower()
    assert report["witness"]["status"] != "WITNESSED"
    assert report["decision"]["status"] == "FAIL", report["decision"]
    assert result.exit_code == 1


def test_doc_key_alone_never_confirms(monkeypatch, tmp_path: Path) -> None:
    """Even a CORRECTLY self-signed doc (sig valid under its own doc key)
    stays NOT CONFIRMED without an out-of-band key — validity under the
    file's own key proves nothing."""
    _hermetic(monkeypatch, tmp_path)
    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    payload, payload_raw, _, _ = _payload_for(epi)
    priv, pub_hex = _fresh_keypair()
    receipt = _make_receipt(priv, payload, payload_raw)
    log = _write_signed_doc(tmp_path / "witness.json", pub_hex, payload_raw, receipt)
    _, report = _verify_json(epi, log)
    assert report["witness"]["status"] == "NOT CONFIRMED", report["witness"]


def test_package_pinned_key_confirms_without_flag(
    monkeypatch, tmp_path: Path
) -> None:
    """Keys pinned in epi_core.witness_keys count as out-of-band trust."""
    import epi_core.witness_keys as _wk

    _hermetic(monkeypatch, tmp_path)
    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    payload, payload_raw, _, _ = _payload_for(epi)
    priv, pub_hex = _fresh_keypair()
    receipt = _make_receipt(priv, payload, payload_raw)
    log = _write_signed_doc(tmp_path / "witness.json", None, payload_raw, receipt)
    monkeypatch.setattr(_wk, "EPI_WITNESS_PUBKEYS", (pub_hex,))
    _, report = _verify_json(epi, log)
    assert report["witness"]["status"] == "WITNESSED", report["witness"]


def test_tampered_payload_raw_never_witnessed(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    payload, payload_raw, _, _ = _payload_for(epi)
    priv, pub_hex = _fresh_keypair()
    receipt = _make_receipt(priv, payload, payload_raw)
    # Flip a byte in a non-workflow field so the workflow still matches but
    # the receipt's line_sha256 no longer covers these bytes. Keep the
    # original receipt (attacker replayed it verbatim).
    tampered = payload_raw.replace(payload["file_sha256"][:8], "ffffffff", 1)
    assert tampered != payload_raw
    assert json.loads(tampered)["workflow_id"] == payload["workflow_id"]
    log = _write_signed_doc(tmp_path / "witness.json", pub_hex, tampered, receipt)
    _, report = _verify_json(epi, log, extra=["--witness-pubkey", pub_hex])
    assert report["witness"]["status"] != "WITNESSED", report["witness"]
    assert report["witness"]["status"] in ("MISMATCH", "NOT IN WITNESS LOG")


def test_forged_signature_never_witnessed(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    payload, payload_raw, _, _ = _payload_for(epi)
    priv, pub_hex = _fresh_keypair()
    other_priv, _ = _fresh_keypair()
    receipt = _make_receipt(other_priv, payload, payload_raw)
    log = _write_signed_doc(tmp_path / "witness.json", pub_hex, payload_raw, receipt)
    _, report = _verify_json(epi, log, extra=["--witness-pubkey", pub_hex])
    assert report["witness"]["status"] != "WITNESSED", report["witness"]
    # A receipt forged under a different key is not from the trusted witness.
    # It must read NOT CONFIRMED ("stamp not from the EPI witness"), never
    # MISMATCH: MISMATCH means the file content differs from a verified
    # receipt, and here nothing verified at all.
    assert report["witness"]["status"] == "NOT CONFIRMED", report["witness"]
    assert "receipt" in report["witness"]["detail"].lower()


def test_wrong_artifact_bytes_is_mismatch(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    from epi_core.container import EPIContainer
    from epi_core.keys import KeyManager
    from epi_core.trust import sign_manifest

    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    payload, payload_raw, _, _ = _payload_for(epi)
    priv, pub_hex = _fresh_keypair()
    receipt = _make_receipt(priv, payload, payload_raw)
    log = _write_signed_doc(tmp_path / "witness.json", pub_hex, payload_raw, receipt)
    # Re-seal the same workflow with different content: same workflow_id,
    # different manifest/file hashes. The receipt still verifies
    # cryptographically but binds the ORIGINAL bytes, so this copy must read
    # as a different version, never WITNESSED.
    ws = tmp_path / "ws"
    EPIContainer.unpack(epi, ws)
    manifest = EPIContainer.read_manifest(epi)
    manifest2 = copy.deepcopy(manifest)
    manifest2.goal = "a tampered goal"
    km = KeyManager()
    altered = tmp_path / "altered.epi"
    EPIContainer.pack(
        ws,
        manifest2,
        altered,
        signer_function=lambda current: sign_manifest(
            current, km.load_private_key("default"), "default"
        ),
        preserve_generated=True,
    )
    _, report = _verify_json(altered, log, extra=["--witness-pubkey", pub_hex])
    assert report["witness"]["status"] == "MISMATCH", report["witness"]
    assert report["witness"]["status"] != "WITNESSED"


def test_legacy_bare_jsonl_without_pubkey_still_witnessed(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    payload, _, _, _ = _payload_for(epi)
    log = tmp_path / "received.jsonl"
    log.write_text(
        json.dumps({**payload, "received_at": RECEIVED_AT}) + "\n", encoding="utf-8"
    )
    _, report = _verify_json(epi, log)
    assert report["witness"]["status"] == "WITNESSED", report["witness"]
    assert report["witness"]["mode"] == "own-log-unsigned", report["witness"]
    assert "YOUR OWN LOG" in report["witness"]["detail"]
    assert report["witness"]["received_at"] == RECEIVED_AT


def test_stripped_forgery_without_key_is_qualified_not_plain(
    monkeypatch, tmp_path: Path
) -> None:
    """Trick 2: attacker strips receipts, shipping bare payload lines. Without
    a key the verifier cannot tell own-log from handed-file, so the verdict
    must carry the YOUR OWN LOG qualifier — never a plain WITNESSED an
    auditor could mistake for a checked stamp."""
    _hermetic(monkeypatch, tmp_path)
    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    _, payload_raw, _, _ = _payload_for(epi)
    log = tmp_path / "stripped.jsonl"
    log.write_text(payload_raw + "\n", encoding="utf-8")
    _, report = _verify_json(epi, log)
    assert report["witness"]["status"] == "WITNESSED", report["witness"]
    assert report["witness"].get("mode") == "own-log-unsigned", report["witness"]
    assert "YOUR OWN LOG" in report["witness"]["detail"]
    assert "verified witness receipt" not in report["witness"]["detail"].lower()


def test_genuine_unsigned_log_survives_package_pinning(
    monkeypatch, tmp_path: Path
) -> None:
    """Future regression: once EPI_WITNESS_PUBKEYS is populated, a customer's
    own unsigned received.jsonl must still verify — package pins never apply
    to unsigned logs."""
    import epi_core.witness_keys as _wk

    _hermetic(monkeypatch, tmp_path)
    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    payload, _, _, _ = _payload_for(epi)
    log = tmp_path / "received.jsonl"
    log.write_text(
        json.dumps({**payload, "received_at": RECEIVED_AT}) + "\n", encoding="utf-8"
    )
    _, other_hex = _fresh_keypair()
    monkeypatch.setattr(_wk, "EPI_WITNESS_PUBKEYS", (other_hex,))
    _, report = _verify_json(epi, log)
    assert report["witness"]["status"] == "WITNESSED", report["witness"]
    assert report["witness"].get("mode") == "own-log-unsigned", report["witness"]


def test_stripped_forgery_with_key_is_rejected(monkeypatch, tmp_path: Path) -> None:
    """Auditor mode (explicit key): unsigned lines are rejected even when the
    hashes match — only signed receipts count."""
    _hermetic(monkeypatch, tmp_path)
    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    _, payload_raw, _, _ = _payload_for(epi)
    _, pub_hex = _fresh_keypair()
    log = tmp_path / "stripped.jsonl"
    log.write_text(payload_raw + "\n", encoding="utf-8")
    _, report = _verify_json(epi, log, extra=["--witness-pubkey", pub_hex])
    assert report["witness"]["status"] == "MISMATCH", report["witness"]
    assert report["witness"]["status"] != "WITNESSED"


def test_receipt_without_trusted_key_is_not_confirmed(
    monkeypatch, tmp_path: Path
) -> None:
    # A receipt-bearing file with no out-of-band key (flag, env, package pin)
    # is NOT CONFIRMED, never WITNESSED — even when the doc names a key, and
    # even when the signature is valid under that key. The doc key is a hint
    # for display, never trust.
    _hermetic(monkeypatch, tmp_path)
    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    payload, payload_raw, _, _ = _payload_for(epi)
    priv, pub_hex = _fresh_keypair()
    receipt = _make_receipt(priv, payload, payload_raw)
    log = _write_signed_doc(tmp_path / "witness.json", pub_hex, payload_raw, receipt)
    _, report = _verify_json(epi, log)
    assert report["witness"]["status"] == "NOT CONFIRMED", report["witness"]
    log2 = _write_signed_doc(tmp_path / "witness2.json", None, payload_raw, receipt)
    _, report2 = _verify_json(epi, log2)
    assert report2["witness"]["status"] == "NOT CONFIRMED", report2["witness"]


def test_witness_pubkey_flag_overrides_wrong_doc_key(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    payload, payload_raw, _, _ = _payload_for(epi)
    priv, pub_hex = _fresh_keypair()
    _, wrong_hex = _fresh_keypair()
    receipt = _make_receipt(priv, payload, payload_raw)
    log = _write_signed_doc(tmp_path / "witness.json", wrong_hex, payload_raw, receipt)
    # Doc key alone is wrong: must not verify.
    _, bad = _verify_json(epi, log)
    assert bad["witness"]["status"] != "WITNESSED", bad["witness"]
    # Flag wins over the doc key.
    _, good = _verify_json(epi, log, extra=["--witness-pubkey", pub_hex])
    assert good["witness"]["status"] == "WITNESSED", good["witness"]
    assert good["witness"]["received_at"] == RECEIVED_AT


def test_signed_jsonl_lines_are_accepted(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    epi = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    payload, payload_raw, _, _ = _payload_for(epi)
    priv, pub_hex = _fresh_keypair()
    receipt = _make_receipt(priv, payload, payload_raw)
    log = tmp_path / "witness.jsonl"
    log.write_text(
        json.dumps({"payload_raw": payload_raw, "receipt": receipt}) + "\n",
        encoding="utf-8",
    )
    _, report = _verify_json(epi, log, extra=["--witness-pubkey", pub_hex])
    assert report["witness"]["status"] == "WITNESSED", report["witness"]


def test_noble_cross_language_golden_vector() -> None:
    """Server (TS @noble/curves) and CLI (python cryptography) must agree byte
    for byte. Canonical golden matches cloud/test/witnessChain.test.ts; the
    signature below was produced by noble over those exact bytes (secret ab*32).
    If either serializer drifts, this fails instead of shipping bad receipts."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    golden = (
        '{"artifact_sha256":"bb","inbox_id":"inb_x","line_sha256":"aa",'
        '"received_at":"2026-10-15T00:00:01.000Z","seq":7}'
    )
    receipt = {
        "artifact_sha256": "bb",
        "inbox_id": "inb_x",
        "line_sha256": "aa",
        "received_at": "2026-10-15T00:00:01.000Z",
        "seq": 7,
    }
    assert _canonical_bytes(receipt).decode("utf-8") == golden
    pub = Ed25519PublicKey.from_public_bytes(
        bytes.fromhex("248acbdbaf9e050196de704bea2d68770e519150d103b587dae2d9cad53dd930")
    )
    pub.verify(
        bytes.fromhex(
            "d710972a1b2f5077e177a22746fb8db3e8fb879aa4bf419f99d1cdee7b5c4abb03a9a1387c4f04fe5bb9f648e3960854650c2bd143e35c146a3945b4dc5c8607"
        ),
        _canonical_bytes(receipt),
    )
