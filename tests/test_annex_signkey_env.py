"""EPI_SIGNING_KEY is honored by annex signing (no throwaway CI key)."""

import os

import pytest

from epi_core.keys import KeyManager

SEED = "9" * 64
EXPECTED_PUB = (
    "332ebe8d27cb7323b3a401c1c13b5dd64bccc0e10ecda1c2b5d11a03779a85e5"
)


def _expected_pub_hex(seed_hex: str) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    pub = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex)).public_key()
    return pub.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def test_import_hex_seed_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path))
    km = KeyManager()
    priv, pub = km.import_hex_seed("ci", SEED)
    assert priv.exists() and pub.exists()
    assert km.load_public_key("ci").hex() == _expected_pub_hex(SEED)
    assert _expected_pub_hex(SEED) == EXPECTED_PUB


def test_import_hex_seed_rejects_bad_format(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path))
    km = KeyManager()
    for bad in ("", "xyz", "9" * 63, "9" * 65, "zz" + "9" * 62):
        with pytest.raises(ValueError):
            km.import_hex_seed("ci", bad)


def test_annex_key_prefers_env_seed(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path))
    monkeypatch.setenv("EPI_SIGNING_KEY", SEED)
    import epi_cli.annex as annex

    pk = annex._key("ci-compliance")
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    assert (
        pk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        == EXPECTED_PUB
    )


def test_annex_key_generates_when_no_env_seed(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path))
    monkeypatch.delenv("EPI_SIGNING_KEY", raising=False)
    import epi_cli.annex as annex

    pk = annex._key("fresh-local")
    assert pk is not None
    assert (tmp_path / "fresh-local.key").exists()
