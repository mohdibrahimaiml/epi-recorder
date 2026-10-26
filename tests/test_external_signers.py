"""Signing keys held in an HSM / cloud KMS (epi_core.signers).

The PKCS#11 tests run against a real SoftHSM token when libsofthsm2 and
python-pkcs11 are installed; AWS and GCP use an injected client that signs
with a real Ed25519 key, so the request shape is checked byte for byte.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core import keys as keys_mod
from epi_core.container import EPIContainer
from epi_core.keys import ExternalKeyRequiredError, KeyManager
from epi_core.signers import (
    AwsKmsSigner,
    ExternalSignerError,
    GcpKmsSigner,
    Pkcs11Signer,
    is_signer_uri,
    load_signer,
)
from epi_core.trust import verify_signature
from epi_core.webhook import seal_signature_header
from tests.helpers.artifacts import make_decision_epi


@pytest.fixture(autouse=True)
def _fresh_signer_cache(monkeypatch):
    monkeypatch.setattr(keys_mod, "_EXTERNAL_SIGNERS", {})
    monkeypatch.delenv("EPI_REQUIRE_EXTERNAL_KEY", raising=False)


def _raw_pub(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )


class FakeAwsKms:
    def __init__(self, key: Ed25519PrivateKey, *, key_spec: str = "ECC_NIST_EDWARDS25519"):
        self.key = key
        self.key_spec = key_spec
        self.sign_calls: list[dict] = []

    def get_public_key(self, KeyId):  # noqa: N803 - boto3's argument name
        der = self.key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return {"KeyId": KeyId, "PublicKey": der, "KeySpec": self.key_spec}

    def sign(self, **kwargs):
        self.sign_calls.append(kwargs)
        return {"Signature": self.key.sign(kwargs["Message"])}


class FakeGcpKms:
    def __init__(self, key: Ed25519PrivateKey):
        self.key = key
        self.requests: list[dict] = []

    def get_public_key(self, request):
        pem = self.key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return SimpleNamespace(pem=pem.decode(), algorithm="EC_SIGN_ED25519")

    def asymmetric_sign(self, request):
        self.requests.append(request)
        return SimpleNamespace(signature=self.key.sign(request["data"]))


GCP_URI = "gcpkms:projects/p/locations/global/keyRings/r/cryptoKeys/epi/cryptoKeyVersions/1"


# --- URI parsing ------------------------------------------------------------


def test_uri_detection_and_unknown_scheme():
    assert is_signer_uri("awskms:alias/epi")
    assert is_signer_uri("pkcs11:token=a;object=b")
    assert not is_signer_uri("/home/me/.epi/keys/default.key")
    with pytest.raises(ExternalSignerError, match="Unknown signer URI"):
        load_signer("vault:secret/epi")


def test_pkcs11_uri_rejects_pin_and_needs_object():
    with pytest.raises(ExternalSignerError, match="must not contain the PIN"):
        Pkcs11Signer("pkcs11:token=epi;object=k;pin-value=1234")
    with pytest.raises(ExternalSignerError, match="object=<label> or id"):
        Pkcs11Signer("pkcs11:token=epi")


def test_gcp_uri_needs_key_version():
    with pytest.raises(ExternalSignerError, match="cryptoKeyVersions"):
        GcpKmsSigner("gcpkms:projects/p/locations/l/keyRings/r/cryptoKeys/k")


# --- AWS / GCP request shape -------------------------------------------------


def test_aws_kms_signs_pure_ed25519_raw():
    key = Ed25519PrivateKey.generate()
    fake = FakeAwsKms(key)
    signer = AwsKmsSigner("awskms:alias/epi-signing?region=eu-west-1", client=fake)
    assert signer.region == "eu-west-1"

    sig = signer.sign(b"manifest-hash")
    key.public_key().verify(sig, b"manifest-hash")
    assert fake.sign_calls == [
        {
            "KeyId": "alias/epi-signing",
            "Message": b"manifest-hash",
            "MessageType": "RAW",
            "SigningAlgorithm": "ED25519_SHA_512",
        }
    ]
    with pytest.raises(ExternalSignerError, match="cannot be exported"):
        signer.private_bytes()


def test_aws_kms_rejects_non_ed25519_key_spec():
    fake = FakeAwsKms(Ed25519PrivateKey.generate(), key_spec="RSA_2048")
    signer = AwsKmsSigner("awskms:alias/rsa", client=fake)
    with pytest.raises(ExternalSignerError, match="ECC_NIST_EDWARDS25519"):
        signer.public_key()


def test_aws_kms_message_limit():
    signer = AwsKmsSigner("awskms:alias/epi", client=FakeAwsKms(Ed25519PrivateKey.generate()))
    with pytest.raises(ExternalSignerError, match="at most 4096"):
        signer.sign(b"x" * 4097)


def test_gcp_kms_signs_data_not_digest():
    key = Ed25519PrivateKey.generate()
    fake = FakeGcpKms(key)
    signer = GcpKmsSigner(GCP_URI, client=fake)
    sig = signer.sign(b"payload")
    key.public_key().verify(sig, b"payload")
    assert fake.requests == [{"name": GCP_URI.split(":", 1)[1], "data": b"payload"}]


def test_signature_from_a_different_key_is_refused():
    """A vault that signs with something other than the advertised key is caught at seal time."""
    advertised = Ed25519PrivateKey.generate()
    fake = FakeAwsKms(advertised)
    fake.sign = lambda **kw: {"Signature": Ed25519PrivateKey.generate().sign(kw["Message"])}
    signer = AwsKmsSigner("awskms:alias/epi", client=fake)
    with pytest.raises(ExternalSignerError, match="does not verify"):
        signer.sign(b"data")


# --- KeyManager linking ------------------------------------------------------


def _link_aws(km: KeyManager, key: Ed25519PrivateKey, name: str = "default", **kw):
    return km.link_external_key(name, "awskms:alias/epi", client=FakeAwsKms(key), **kw)


def test_link_writes_public_key_and_no_secret(tmp_path):
    km = KeyManager(tmp_path)
    key = Ed25519PrivateKey.generate()
    signer_path, pub_hex = _link_aws(km, key)

    assert pub_hex == _raw_pub(key).hex()
    assert km.load_public_key("default") == _raw_pub(key)
    record = json.loads(signer_path.read_text())
    assert record == {"uri": "awskms:alias/epi", "backend": "AWS KMS", "public_key": pub_hex}
    assert not (tmp_path / "default.key").exists()
    assert km.has_key("default") and km.has_default_key()
    assert km.external_signer_uri("default") == "awskms:alias/epi"
    listed = {k["name"]: k for k in km.list_keys()}
    assert listed["default"]["external"] is True
    assert listed["default"]["private_path"] == "awskms:alias/epi"


def test_link_refuses_existing_key_file(tmp_path):
    km = KeyManager(tmp_path)
    km.generate_keypair("default")
    with pytest.raises(FileExistsError, match="Move or delete it"):
        _link_aws(km, Ed25519PrivateKey.generate(), overwrite=True)
    assert (tmp_path / "default.key").exists()


def test_link_refuses_relink_without_overwrite(tmp_path):
    km = KeyManager(tmp_path)
    _link_aws(km, Ed25519PrivateKey.generate())
    with pytest.raises(FileExistsError):
        _link_aws(km, Ed25519PrivateKey.generate())
    _link_aws(km, Ed25519PrivateKey.generate(), overwrite=True)


def test_generate_refuses_linked_name_unless_overwrite(tmp_path):
    km = KeyManager(tmp_path)
    _link_aws(km, Ed25519PrivateKey.generate())
    with pytest.raises(FileExistsError):
        km.generate_keypair("default")
    km.generate_keypair("default", overwrite=True)
    assert km.external_signer_uri("default") is None


def test_load_private_key_returns_signer_and_signs_manifest(tmp_path):
    km = KeyManager(tmp_path)
    key = Ed25519PrivateKey.generate()
    _link_aws(km, key)
    signer = km.load_private_key("default")
    assert isinstance(signer, AwsKmsSigner)

    epi_path, _ = make_decision_epi(tmp_path, private_key=signer)
    manifest = EPIContainer.read_manifest(epi_path)
    assert manifest.public_key == _raw_pub(key).hex()
    ok, message = verify_signature(manifest, _raw_pub(key))
    assert ok, message


def test_swapped_vault_key_is_refused(tmp_path, monkeypatch):
    km = KeyManager(tmp_path)
    _link_aws(km, Ed25519PrivateKey.generate())
    keys_mod._EXTERNAL_SIGNERS.clear()  # new process: reconnects to the vault

    import epi_core.signers as signers_mod

    swapped = FakeAwsKms(Ed25519PrivateKey.generate())
    monkeypatch.setattr(
        signers_mod, "load_signer", lambda uri, **kw: AwsKmsSigner(uri, client=swapped)
    )
    with pytest.raises(ExternalSignerError, match="Refusing to sign"):
        km.load_private_key("default")


def test_require_external_key_blocks_key_files(tmp_path, monkeypatch):
    km = KeyManager(tmp_path)
    km.generate_keypair("filekey")
    _link_aws(km, Ed25519PrivateKey.generate(), name="vaultkey")
    monkeypatch.setenv("EPI_REQUIRE_EXTERNAL_KEY", "1")
    with pytest.raises(ExternalKeyRequiredError, match="epi keys link"):
        km.load_private_key("filekey")
    assert isinstance(km.load_private_key("vaultkey"), AwsKmsSigner)


def test_witness_header_signed_through_external_signer():
    key = Ed25519PrivateKey.generate()
    signer = AwsKmsSigner("awskms:alias/epi", client=FakeAwsKms(key))
    header = seal_signature_header(b'{"a":1}', signer, "default")
    algo, name, sig_hex = header.split(":")
    assert (algo, name) == ("ed25519", "default")
    key.public_key().verify(bytes.fromhex(sig_hex), b'{"a":1}')
    # Raw key bytes still accepted (older callers).
    raw = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    assert seal_signature_header(b'{"a":1}', raw, "default") == header


# --- Real HSM (SoftHSM) ------------------------------------------------------

_SOFTHSM_LIBS = [
    os.environ.get("EPI_TEST_SOFTHSM_LIB", ""),
    "/usr/lib/softhsm/libsofthsm2.so",
    "/usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so",
    "/usr/local/lib/softhsm/libsofthsm2.so",
    "/opt/homebrew/lib/softhsm/libsofthsm2.so",
]
_SOFTHSM_LIB = next((p for p in _SOFTHSM_LIBS if p and Path(p).is_file()), None)

try:
    import pkcs11  # noqa: F401

    _HAS_PKCS11 = True
except ImportError:
    _HAS_PKCS11 = False

_SOFTHSM_READY = bool(_SOFTHSM_LIB and _HAS_PKCS11 and shutil.which("softhsm2-util"))
if os.environ.get("EPI_TEST_REQUIRE_SOFTHSM") == "1" and not _SOFTHSM_READY:
    raise RuntimeError("EPI_TEST_REQUIRE_SOFTHSM=1 but SoftHSM2 / python-pkcs11 is not installed")

needs_softhsm = pytest.mark.skipif(
    not _SOFTHSM_READY, reason="SoftHSM2 + python-pkcs11 not installed"
)


@pytest.fixture(scope="module")
def _softhsm_token(tmp_path_factory):
    """One SoftHSM token per module: the library reads its config once per process."""
    import pkcs11
    from pkcs11 import Attribute, KeyType, Mechanism
    from pkcs11.util.ec import encode_named_curve_parameters

    base = tmp_path_factory.mktemp("softhsm")
    tokens = base / "tokens"
    tokens.mkdir()
    conf = base / "softhsm2.conf"
    conf.write_text(f"directories.tokendir = {tokens}\nobjectstore.backend = file\n")
    mp = pytest.MonkeyPatch()
    mp.setenv("SOFTHSM2_CONF", str(conf))
    subprocess.run(
        ["softhsm2-util", "--init-token", "--free", "--label", "epi-test",
         "--pin", "1234", "--so-pin", "5678"],
        check=True, capture_output=True,
    )
    lib = pkcs11.lib(_SOFTHSM_LIB)
    with lib.get_token(token_label="epi-test").open(user_pin="1234", rw=True) as session:
        params = session.create_domain_parameters(
            KeyType.EC_EDWARDS,
            {Attribute.EC_PARAMS: encode_named_curve_parameters("1.3.101.112")},
            local=True,
        )
        params.generate_keypair(
            mechanism=Mechanism.EC_EDWARDS_KEY_PAIR_GEN, store=True, label="epi-signing"
        )
    yield f"pkcs11:token=epi-test;object=epi-signing?module-path={_SOFTHSM_LIB}"
    mp.undo()


@pytest.fixture
def softhsm_key(_softhsm_token, monkeypatch):
    """URI of an Ed25519 key pair in SoftHSM, labelled epi-signing."""
    monkeypatch.setenv("EPI_PKCS11_PIN", "1234")
    return _softhsm_token


@needs_softhsm
def test_softhsm_seal_and_cli_verify(tmp_path, softhsm_key, monkeypatch):
    keys_dir = tmp_path / "keys"
    km = KeyManager(keys_dir)
    _, pub_hex = km.link_external_key("default", softhsm_key)
    signer = km.load_private_key("default")
    assert isinstance(signer, Pkcs11Signer)

    epi_path, _ = make_decision_epi(tmp_path, private_key=signer)
    manifest = EPIContainer.read_manifest(epi_path)
    assert manifest.public_key == pub_hex
    assert verify_signature(manifest, bytes.fromhex(pub_hex))[0]

    env = {**os.environ, "EPI_KEYS_DIR": str(keys_dir), "EPI_HOME": str(tmp_path / "home")}
    result = subprocess.run(
        [sys.executable, "-m", "epi_cli", "verify", str(epi_path), "--json"],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout[result.stdout.index("{"):])
    assert report["signature_valid"] is True


@needs_softhsm
def test_softhsm_wrong_key_label_fails_clearly(softhsm_key):
    signer = load_signer(softhsm_key.replace("object=epi-signing", "object=missing"))
    with pytest.raises(ExternalSignerError, match="found 0"):
        signer.public_key()


@needs_softhsm
def test_softhsm_cli_link_then_record_signs_in_hsm(tmp_path, softhsm_key, monkeypatch):
    """The everyday path: `epi keys link`, then record() seals through the HSM."""
    keys_dir = tmp_path / "keys"
    env = {**os.environ, "EPI_KEYS_DIR": str(keys_dir), "EPI_HOME": str(tmp_path / "home")}
    linked = subprocess.run(
        [sys.executable, "-m", "epi_cli", "keys", "link",
         "--name", "default", "--uri", softhsm_key],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert linked.returncode == 0, linked.stdout + linked.stderr
    assert "Linked key" in linked.stdout
    assert not (keys_dir / "default.key").exists()
    pub_hex = json.loads((keys_dir / "default.signer").read_text())["public_key"]

    from epi_recorder import record

    monkeypatch.setenv("EPI_KEYS_DIR", str(keys_dir))
    monkeypatch.setenv("EPI_REQUIRE_EXTERNAL_KEY", "1")
    out = tmp_path / "hsm-run.epi"
    with record(out, workflow_name="hsm", capture_prints=False) as epi:
        epi.log_step("tool.call", {"tool": "lookup", "input": {"id": 1}})

    manifest = EPIContainer.read_manifest(out)
    assert manifest.public_key == pub_hex
    assert verify_signature(manifest, bytes.fromhex(pub_hex))[0]
    assert not (keys_dir / "default.key").exists()
