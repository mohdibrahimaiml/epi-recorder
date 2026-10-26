"""
External Ed25519 signers: keys held in an HSM or cloud KMS.

Each signer stands in for ``Ed25519PrivateKey`` wherever EPI signs: it has
``sign(data) -> 64 bytes`` and ``public_key() -> Ed25519PublicKey``. The
private key never leaves the vault, so ``private_bytes()`` always fails.

Signatures are pure Ed25519 (RFC 8032), byte-identical to what a key file
would produce, so every existing ``.epi`` verifier accepts them unchanged.

Key URIs (stored in ``<keys_dir>/<name>.signer`` by ``epi keys link``):

    pkcs11:token=<label>;object=<label>[?module-path=/path/to/lib.so]
    awskms:<key-id | key-arn | alias/name>[?region=<region>]
    gcpkms:projects/<p>/locations/<l>/keyRings/<r>/cryptoKeys/<k>/cryptoKeyVersions/<n>

Secrets never go in a URI: the PKCS#11 PIN comes from ``EPI_PKCS11_PIN``;
cloud credentials come from each SDK's normal credential chain.
"""

from __future__ import annotations

import os
import threading
from typing import Any
from urllib.parse import parse_qs, unquote

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCHEMES = ("pkcs11", "awskms", "gcpkms")

# AWS KMS Sign accepts at most 4096 bytes when MessageType is RAW.
_AWS_RAW_MESSAGE_LIMIT = 4096


class ExternalSignerError(Exception):
    """An external signer could not be configured or refused to sign."""


def is_signer_uri(value: str) -> bool:
    scheme, _, rest = str(value or "").strip().partition(":")
    return scheme.lower() in SCHEMES and bool(rest)


class ExternalSigner:
    """Base class: an Ed25519 key that lives in a vault."""

    backend = "external"

    def __init__(self, uri: str) -> None:
        self.uri = uri
        self._public_key: Ed25519PublicKey | None = None
        self._lock = threading.Lock()

    # -- backend hooks -------------------------------------------------
    def _fetch_public_key_raw(self) -> bytes:  # pragma: no cover - abstract
        raise NotImplementedError

    def _sign_raw(self, data: bytes) -> bytes:  # pragma: no cover - abstract
        raise NotImplementedError

    # -- Ed25519PrivateKey-compatible surface ---------------------------
    def public_key(self) -> Ed25519PublicKey:
        if self._public_key is None:
            raw = self._fetch_public_key_raw()
            if len(raw) != 32:
                raise ExternalSignerError(
                    f"{self.backend}: expected a 32-byte Ed25519 public key, got {len(raw)} bytes"
                )
            self._public_key = Ed25519PublicKey.from_public_bytes(raw)
        return self._public_key

    def public_key_hex(self) -> str:
        return self.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        ).hex()

    def sign(self, data: bytes) -> bytes:
        data = bytes(data)
        with self._lock:
            signature = bytes(self._sign_raw(data))
        if len(signature) != 64:
            raise ExternalSignerError(
                f"{self.backend}: expected a 64-byte Ed25519 signature, got {len(signature)} bytes"
            )
        # Check before handing it out: a key set up for Ed25519ph, or a
        # backend that signs something else, fails here at seal time rather
        # than later in a customer's verify.
        try:
            self.public_key().verify(signature, data)
        except InvalidSignature as exc:
            raise ExternalSignerError(
                f"{self.backend}: the vault returned a signature that does not verify against "
                "the linked public key. Either the key in the vault was replaced, or it is set "
                "up for prehashed Ed25519ph instead of pure Ed25519. Refusing to sign."
            ) from exc
        return signature

    def private_bytes(self, *args: Any, **kwargs: Any) -> bytes:
        raise ExternalSignerError(
            f"This signing key is held in {self.backend} ({self.uri}); it cannot be exported."
        )

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.uri}>"


# ---------------------------------------------------------------------------
# PKCS#11 (hardware HSMs, AWS CloudHSM, YubiHSM, SoftHSM)
# ---------------------------------------------------------------------------


def _parse_pkcs11_uri(uri: str) -> tuple[dict[str, str], dict[str, str]]:
    body = uri.split(":", 1)[1]
    path, _, query = body.partition("?")
    attrs: dict[str, str] = {}
    for part in path.split(";"):
        if not part:
            continue
        key, sep, value = part.partition("=")
        if not sep:
            raise ExternalSignerError(f"pkcs11 URI: malformed attribute {part!r}")
        attrs[key.strip().lower()] = unquote(value)
    params = {k.lower(): v[-1] for k, v in parse_qs(query, keep_blank_values=True).items()}
    if "pin-value" in attrs or "pin-value" in params:
        raise ExternalSignerError(
            "pkcs11 URI must not contain the PIN; set EPI_PKCS11_PIN instead"
        )
    return attrs, params


def _ec_point_to_raw(point: bytes) -> bytes:
    """CKA_EC_POINT for Ed25519: DER OCTET STRING (04 20 || key) or the bare key."""
    point = bytes(point)
    if len(point) == 34 and point[0] == 0x04 and point[1] == 0x20:
        return point[2:]
    if len(point) == 32:
        return point
    raise ExternalSignerError(f"pkcs11: unexpected EC_POINT encoding ({len(point)} bytes)")


class Pkcs11Signer(ExternalSigner):
    backend = "PKCS#11 HSM"

    def __init__(self, uri: str, *, lib: Any = None) -> None:
        super().__init__(uri)
        attrs, params = _parse_pkcs11_uri(uri)
        self.token_label = attrs.get("token")
        self.object_label = attrs.get("object")
        self.key_id = bytes.fromhex(attrs["id"].replace("%", "")) if attrs.get("id") else None
        if not self.token_label:
            raise ExternalSignerError("pkcs11 URI needs token=<label>")
        if not (self.object_label or self.key_id):
            raise ExternalSignerError("pkcs11 URI needs object=<label> or id=<hex>")
        self.module_path = params.get("module-path") or os.environ.get("EPI_PKCS11_MODULE")
        self._lib = lib
        self._session = None

    def _open(self):
        if self._session is not None:
            return self._session
        try:
            import pkcs11  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ExternalSignerError(
                "PKCS#11 signing needs python-pkcs11: pip install 'epi-recorder[pkcs11]'"
            ) from exc
        if self._lib is None:
            if not self.module_path:
                raise ExternalSignerError(
                    "pkcs11: no module; add ?module-path=... to the URI or set EPI_PKCS11_MODULE"
                )
            self._lib = pkcs11.lib(self.module_path)
        pin = os.environ.get("EPI_PKCS11_PIN")
        try:
            token = self._lib.get_token(token_label=self.token_label)
            try:
                self._session = token.open(user_pin=pin) if pin else token.open()
            except pkcs11.exceptions.UserAlreadyLoggedIn:
                # PKCS#11 login is per token, not per session: another signer
                # in this process already logged in, so this session is too.
                self._session = token.open()
        except Exception as exc:
            raise ExternalSignerError(
                f"pkcs11: cannot open token {self.token_label!r}: "
                f"{type(exc).__name__} {exc}".rstrip()
            ) from exc
        return self._session

    def _find(self, object_class):
        import pkcs11  # type: ignore[import-not-found]

        query: dict[Any, Any] = {
            pkcs11.Attribute.CLASS: object_class,
            pkcs11.Attribute.KEY_TYPE: pkcs11.KeyType.EC_EDWARDS,
        }
        if self.object_label:
            query[pkcs11.Attribute.LABEL] = self.object_label
        if self.key_id:
            query[pkcs11.Attribute.ID] = self.key_id
        found = list(self._open().get_objects(query))
        if len(found) != 1:
            what = "private" if object_class == pkcs11.ObjectClass.PRIVATE_KEY else "public"
            raise ExternalSignerError(
                f"pkcs11: expected exactly one Ed25519 {what} key matching the URI, "
                f"found {len(found)}"
            )
        return found[0]

    def _fetch_public_key_raw(self) -> bytes:
        import pkcs11  # type: ignore[import-not-found]

        with self._lock:
            pub = self._find(pkcs11.ObjectClass.PUBLIC_KEY)
            return _ec_point_to_raw(pub[pkcs11.Attribute.EC_POINT])

    def _sign_raw(self, data: bytes) -> bytes:
        import pkcs11  # type: ignore[import-not-found]

        priv = self._find(pkcs11.ObjectClass.PRIVATE_KEY)
        return priv.sign(data, mechanism=pkcs11.Mechanism.EDDSA)


# ---------------------------------------------------------------------------
# AWS KMS (key spec ECC_NIST_EDWARDS25519)
# ---------------------------------------------------------------------------


class AwsKmsSigner(ExternalSigner):
    backend = "AWS KMS"

    def __init__(self, uri: str, *, client: Any = None) -> None:
        super().__init__(uri)
        body = uri.split(":", 1)[1]
        key_id, _, query = body.partition("?")
        if not key_id:
            raise ExternalSignerError("awskms URI needs a key id, ARN or alias")
        self.key_id = unquote(key_id)
        params = {k.lower(): v[-1] for k, v in parse_qs(query).items()}
        self.region = params.get("region")
        self._client = client

    def _kms(self):
        if self._client is None:
            try:
                import boto3  # type: ignore[import-not-found]
            except ImportError as exc:
                raise ExternalSignerError(
                    "AWS KMS signing needs boto3: pip install 'epi-recorder[aws-kms]'"
                ) from exc
            kwargs = {"region_name": self.region} if self.region else {}
            self._client = boto3.client("kms", **kwargs)
        return self._client

    def _fetch_public_key_raw(self) -> bytes:
        response = self._kms().get_public_key(KeyId=self.key_id)
        spec = response.get("KeySpec") or response.get("CustomerMasterKeySpec")
        if spec and spec != "ECC_NIST_EDWARDS25519":
            raise ExternalSignerError(
                f"AWS KMS key {self.key_id} is {spec}; EPI needs key spec ECC_NIST_EDWARDS25519"
            )
        public_key = serialization.load_der_public_key(bytes(response["PublicKey"]))
        if not isinstance(public_key, Ed25519PublicKey):
            raise ExternalSignerError(f"AWS KMS key {self.key_id} is not an Ed25519 key")
        return public_key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )

    def _sign_raw(self, data: bytes) -> bytes:
        if len(data) > _AWS_RAW_MESSAGE_LIMIT:
            raise ExternalSignerError(
                f"AWS KMS signs at most {_AWS_RAW_MESSAGE_LIMIT} bytes per message; got {len(data)}"
            )
        response = self._kms().sign(
            KeyId=self.key_id,
            Message=data,
            MessageType="RAW",
            SigningAlgorithm="ED25519_SHA_512",
        )
        return bytes(response["Signature"])


# ---------------------------------------------------------------------------
# Google Cloud KMS (algorithm EC_SIGN_ED25519)
# ---------------------------------------------------------------------------


class GcpKmsSigner(ExternalSigner):
    backend = "Google Cloud KMS"

    def __init__(self, uri: str, *, client: Any = None) -> None:
        super().__init__(uri)
        self.key_version = unquote(uri.split(":", 1)[1].strip())
        if "/cryptoKeyVersions/" not in self.key_version:
            raise ExternalSignerError(
                "gcpkms URI needs a full key version: "
                "projects/.../cryptoKeys/<k>/cryptoKeyVersions/<n>"
            )
        self._client = client

    def _kms(self):
        if self._client is None:
            try:
                from google.cloud import kms  # type: ignore[import-not-found]
            except ImportError as exc:
                raise ExternalSignerError(
                    "Google Cloud KMS signing needs google-cloud-kms: "
                    "pip install 'epi-recorder[gcp-kms]'"
                ) from exc
            self._client = kms.KeyManagementServiceClient()
        return self._client

    def _fetch_public_key_raw(self) -> bytes:
        response = self._kms().get_public_key(request={"name": self.key_version})
        # The client returns an enum (str() of it is the number), so read its name.
        raw_algorithm = getattr(response, "algorithm", None)
        algorithm = str(getattr(raw_algorithm, "name", raw_algorithm) or "")
        if algorithm and "ED25519" not in algorithm.upper():
            raise ExternalSignerError(
                f"Google Cloud KMS key is {algorithm}; EPI needs EC_SIGN_ED25519"
            )
        public_key = serialization.load_pem_public_key(str(response.pem).encode("utf-8"))
        if not isinstance(public_key, Ed25519PublicKey):
            raise ExternalSignerError("Google Cloud KMS key is not an Ed25519 key")
        return public_key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )

    def _sign_raw(self, data: bytes) -> bytes:
        response = self._kms().asymmetric_sign(request={"name": self.key_version, "data": data})
        return bytes(response.signature)


def load_signer(uri: str, **backend_kwargs: Any) -> ExternalSigner:
    """Build the signer for a key URI. Raises ExternalSignerError for unknown schemes."""
    uri = str(uri or "").strip()
    scheme = uri.split(":", 1)[0].lower()
    if scheme == "pkcs11":
        return Pkcs11Signer(uri, **backend_kwargs)
    if scheme == "awskms":
        return AwsKmsSigner(uri, **backend_kwargs)
    if scheme == "gcpkms":
        return GcpKmsSigner(uri, **backend_kwargs)
    raise ExternalSignerError(
        f"Unknown signer URI {uri!r}; expected one of: " + ", ".join(f"{s}:" for s in SCHEMES)
    )
