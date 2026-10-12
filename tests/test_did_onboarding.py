"""did:web identity onboarding (WP1c). Network is mocked via the _RequestsShim patch point."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app

runner = CliRunner()

VENDOR_DID = "did:web:vendor.com"


def _hermetic(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "home" / "keys"))
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(tmp_path / "home" / "trusted"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")


def _did_doc(did: str, *key_hexes: str) -> dict:
    return {
        "@context": ["https://www.w3.org/ns/did/v1"],
        "id": did,
        "verificationMethod": [
            {
                "id": f"{did}#key-{i + 1}",
                "type": "Ed25519VerificationKey2020",
                "controller": did,
                "publicKeyHex": key_hex,
            }
            for i, key_hex in enumerate(key_hexes)
        ],
    }


class _FakeResp:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _mock_resolve(monkeypatch, doc: dict, status_code: int = 200):
    calls: list[str] = []

    def _fake_get(url: str, *, timeout: int = 10, **kwargs):
        calls.append(url)
        return _FakeResp(doc, status_code)

    monkeypatch.setattr("epi_core.did_web.requests.get", _fake_get)
    return calls


def test_keys_did_writes_document(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    from epi_core.keys import KeyManager

    KeyManager().generate_keypair("default")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        cli_app, ["keys", "did", "--domain", "vendor.com", "--path", "agents/claims"]
    )
    assert result.exit_code == 0, result.output
    assert "did:web:vendor.com:agents:claims" in result.output
    assert "https://vendor.com/agents/claims/did.json" in result.output
    assert "GitHub Pages" in result.output or "Cloudflare" in result.output

    doc = json.loads((tmp_path / "did.json").read_text(encoding="utf-8"))
    assert doc["id"] == "did:web:vendor.com:agents:claims"
    pub_hex = KeyManager().load_public_key("default").hex()
    assert doc["verificationMethod"][0]["publicKeyHex"] == pub_hex

    # Bare domain variant.
    (tmp_path / "did.json").unlink()
    result = runner.invoke(cli_app, ["keys", "did", "--domain", "vendor.com"])
    assert result.exit_code == 0, result.output
    assert "did:web:vendor.com " in result.output or "did:web:vendor.com\n" in result.output
    assert "https://vendor.com/.well-known/did.json" in result.output


def test_record_did_and_env(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    from epi_core.container import EPIContainer
    from epi_recorder import record

    out = tmp_path / "a.epi"
    with record(str(out), did=VENDOR_DID) as epi:
        epi.log_step("llm.request", {"n": 1})
    manifest = EPIContainer.read_manifest(out)
    assert (manifest.governance or {}).get("did") == VENDOR_DID

    out2 = tmp_path / "b.epi"
    monkeypatch.setenv("EPI_DID", "did:web:other.example")
    with record(str(out2)) as epi:
        epi.log_step("llm.request", {"n": 1})
    manifest2 = EPIContainer.read_manifest(out2)
    assert (manifest2.governance or {}).get("did") == "did:web:other.example"


def test_trust_from_did_pins_key(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    from epi_core.keys import KeyManager

    KeyManager().generate_keypair("default")
    pub_hex = KeyManager().load_public_key("default").hex()
    _mock_resolve(monkeypatch, _did_doc(VENDOR_DID, pub_hex))

    result = runner.invoke(
        cli_app, ["keys", "trust", "--from-did", VENDOR_DID, "--name", "vendor"]
    )
    assert result.exit_code == 0, result.output
    pinned = tmp_path / "home" / "trusted" / "vendor.pub"
    assert pinned.is_file()
    assert pinned.read_text(encoding="utf-8").strip() == pub_hex
    from epi_core.keys import key_fingerprint

    fingerprint = hashlib.sha256(pub_hex.encode()).hexdigest()[:16]
    assert key_fingerprint(pub_hex) == " ".join(fingerprint[i:i + 4] for i in range(0, 16, 4))
    assert key_fingerprint(pub_hex) in result.output


def _keypair_for(tag: str):
    import hashlib as _hashlib

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    seed = _hashlib.sha256(f"did-onboarding-{tag}".encode()).digest()
    private = Ed25519PrivateKey.from_private_bytes(seed)
    public_hex = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return private, public_hex


def _sealed_with(private, key_hex: str, tmp_path: Path, name: str, did: str | None) -> Path:
    from epi_core.container import EPIContainer
    from epi_core.schemas import ManifestModel
    from epi_core.trust import sign_manifest
    from tests.helpers.artifacts import make_decision_workspace

    ws = make_decision_workspace(tmp_path / f"ws-{name}")
    manifest = ManifestModel(governance={"did": did} if did else None)
    out = tmp_path / f"{name}.epi"
    EPIContainer.pack(
        ws,
        manifest,
        out,
        signer_function=lambda item: sign_manifest(item, private, "test"),
        preserve_generated=True,
        generate_analysis=False,
    )
    # sanity: the sealed key is the intended one
    assert EPIContainer.read_manifest(out).public_key == key_hex
    return out


def test_verify_unpinned_vs_untrusted_key(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    vendor_private, vendor_hex = _keypair_for("vendor")
    other_private, other_hex = _keypair_for("other")

    vendor_file = _sealed_with(vendor_private, vendor_hex, tmp_path, "vendor", VENDOR_DID)
    other_file = _sealed_with(other_private, other_hex, tmp_path, "other", None)

    # No pins at all: soft NOT_PINNED.
    result = runner.invoke(cli_app, ["verify", str(other_file)])
    assert result.exit_code == 0, result.output
    assert "NOT_PINNED" in result.output
    assert "NOT A KEY YOU TRUST" not in result.output

    # Pins exist, file sealed by another key: red NOT A KEY YOU TRUST.
    (tmp_path / "home" / "trusted").mkdir(parents=True, exist_ok=True)
    (tmp_path / "home" / "trusted" / "vendor.pub").write_text(vendor_hex + "\n")
    # This is the impersonation case pinning exists to catch: it must FAIL
    # (non-zero exit), and must never suggest pinning the key from the file.
    result = runner.invoke(cli_app, ["verify", str(other_file)])
    assert result.exit_code != 0, result.output
    text = result.output.replace("\n", " ")
    assert "NOT A KEY YOU TRUST" in text
    assert "vendor" in text
    assert "This file was not sealed by a key you trust." in text
    assert "DECISION: FAIL" in text
    assert f'epi keys trust "{other_file}"' not in text

    # Pinned key itself: KNOWN, no red line.
    result = runner.invoke(cli_app, ["verify", str(vendor_file)])
    assert "NOT A KEY YOU TRUST" not in result.output


def test_verify_offline_did_declared(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    vendor_private, vendor_hex = _keypair_for("vendor2")
    vendor_file = _sealed_with(vendor_private, vendor_hex, tmp_path, "vendor-offline", VENDOR_DID)

    # Offline, no pins: declared but unresolved.
    result = runner.invoke(cli_app, ["verify", str(vendor_file), "--offline"])
    assert result.exit_code == 0, result.output
    text = result.output.replace("\n", " ")
    assert f"DID declared ({VENDOR_DID}), not resolved offline" in text

    # Offline with the key pinned: pinned key matches.
    (tmp_path / "home" / "trusted").mkdir(parents=True, exist_ok=True)
    (tmp_path / "home" / "trusted" / "vendor.pub").write_text(vendor_hex + "\n")
    result = runner.invoke(cli_app, ["verify", str(vendor_file), "--offline"])
    assert result.exit_code == 0, result.output
    assert "pinned key matches" in result.output.replace("\n", " ")


def test_rotation_second_key_accepted(monkeypatch, tmp_path: Path) -> None:
    """A did.json listing two keys verifies files sealed by either."""
    from epi_core.trust import TrustRegistry

    _hermetic(monkeypatch, tmp_path)
    _p1, hex1 = _keypair_for("rot1")
    _p2, hex2 = _keypair_for("rot2")
    doc = _did_doc(VENDOR_DID, hex1, hex2)
    _mock_resolve(monkeypatch, doc)

    registry = TrustRegistry()
    ok_old, _, _ = registry._verify_did_web(VENDOR_DID, hex1)
    ok_new, _, _ = registry._verify_did_web(VENDOR_DID, hex2)
    assert ok_old is True
    assert ok_new is True
    ok_other, _, _ = registry._verify_did_web(VENDOR_DID, "ff" * 32)
    assert ok_other is False
