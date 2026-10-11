"""Offline RFC 3161 timestamp validation against pinned TSA roots.

A timestamp token only becomes evidence once a verifier checks it: that the
token is well-formed, that its message imprint covers the exact bytes we
sealed, that its signature verifies with the signer's key, that the signer
was authorised to timestamp, and that the signer chains to a trust root
pinned in ``epi_core/assets/tsa_roots/`` (shipped with the package) or
supplied by the operator.

Validation is fully offline by construction: no network fetch, no OCSP/CRL
revocation check (see docs/VERIFICATION_CONTRACT.md). asn1crypto is used for
DER parsing only; every signature check runs in ``cryptography``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from typing import Literal

from asn1crypto import cms, tsp, x509 as asn1_x509
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.x509.oid import ExtendedKeyUsageOID

TsaStatus = Literal[
    "valid",
    "imprint_mismatch",
    "bad_signature",
    "untrusted",
    "cert_invalid",
    "not_granted",
    "malformed",
    "absent",
]

TST_INFO_OID = "1.2.840.113549.1.9.16.1.4"
ESS_V1_OID = "1.2.840.113549.1.9.16.2.12"
ESS_V2_OID = "1.2.840.113549.1.9.16.2.47"
IMPRINT_ALGORITHMS = {"sha256": 32, "sha384": 48, "sha512": 64}

_HASHLIB_BY_NAME = {
    "sha256": hashlib.sha256,
    "sha384": hashlib.sha384,
    "sha512": hashlib.sha512,
    "sha1": hashlib.sha1,
}


@dataclass
class TsaValidation:
    status: TsaStatus
    gen_time: str | None  # UTC ISO-8601 from TSTInfo.genTime (parsed, not scanned)
    tsa_subject: str | None  # signer certificate subject
    tsa_root: str | None  # name of the pinned root it chained to
    serial: int | None  # TSTInfo.serialNumber
    policy_oid: str | None
    hash_algorithm: str | None  # messageImprint algorithm
    detail: str  # one human sentence explaining the status


def _fail(status: TsaStatus, detail: str, **kw) -> TsaValidation:
    base = {
        "gen_time": None,
        "tsa_subject": None,
        "tsa_root": None,
        "serial": None,
        "policy_oid": None,
        "hash_algorithm": None,
    }
    base.update(kw)
    return TsaValidation(status=status, detail=detail, **base)  # type: ignore[arg-type]


def _utc_iso(dt) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _not_valid_before(cert: x509.Certificate):
    """Signer validity start as aware UTC.

    `not_valid_before_utc` exists only on cryptography >= 42 while pyproject
    allows >= 41: fall back to the naive (UTC by X.509 convention) property
    so old installs validate instead of reporting "unreadable".
    """
    get = getattr(cert, "not_valid_before_utc", None)
    if get is not None:
        return get
    return cert.not_valid_before.replace(tzinfo=timezone.utc)


def _not_valid_after(cert: x509.Certificate):
    get = getattr(cert, "not_valid_after_utc", None)
    if get is not None:
        return get
    return cert.not_valid_after.replace(tzinfo=timezone.utc)


def _read_tlv(buf: bytes, pos: int):
    """Split one DER TLV at pos -> (tag, value_start, value_bytes, next_pos)."""
    tag = buf[pos]
    pos += 1
    first = buf[pos]
    pos += 1
    if first & 0x80:
        n = first & 0x7F
        if n == 0 or n > 4 or pos + n > len(buf):
            raise ValueError("bad DER length")
        length = int.from_bytes(buf[pos : pos + n], "big")
        pos += n
    else:
        length = first
    if pos + length > len(buf):
        raise ValueError("DER overruns buffer")
    return tag, pos, bytes(buf[pos : pos + length]), pos + length


def _tst_raw_octets(encap_content) -> bytes:
    """Raw TSTInfo DER octets as embedded in the token (no re-encoding).

    encap_content is the [0] EXPLICIT ANY holding an OCTET STRING. Handles
    both primitive and constructed string forms.
    """
    dump = encap_content.dump()
    if not dump or dump[0] != 0xA0:
        raise ValueError("encap content is not [0] EXPLICIT")
    _, _, inner_tlv, _ = _read_tlv(dump, 0)
    tag, _, value, _ = _read_tlv(inner_tlv, 0)
    if tag == 0x04:
        return value
    if tag == 0x24:
        parts: list[bytes] = []
        pos = 0
        # value holds concatenated primitive OCTET STRING TLVs
        while pos < len(value):
            seg_tag, _, seg_val, nxt = _read_tlv(value, pos)
            if seg_tag != 0x04:
                raise ValueError("non-octet segment in constructed content")
            parts.append(seg_val)
            pos = nxt
        return b"".join(parts)
    raise ValueError("encap content is not an OCTET STRING")


def _asn1_certs_to_crypto(objs) -> list[x509.Certificate]:
    out = []
    for obj in objs or []:
        try:
            out.append(x509.load_der_x509_certificate(bytes(obj.dump())))
        except Exception:
            continue
    return out


def _load_pem_certs(path: Path) -> list[x509.Certificate]:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return []
    out: list[x509.Certificate] = []
    marker = b"-----BEGIN CERTIFICATE-----"
    # cryptography loads only the first PEM block per call, so split manually.
    for chunk in data.split(marker):
        if b"-----END CERTIFICATE-----" not in chunk:
            continue
        try:
            out.extend(x509.load_pem_x509_certificates(marker + chunk))
        except Exception:
            continue
    return out


def _assets_dir() -> Path:
    from importlib.resources import files

    return Path(str(files("epi_core") / "assets" / "tsa_roots"))


def load_pinned_tsa_roots() -> list[tuple[str, x509.Certificate]]:
    """Pinned TSA trust roots shipped with the package.

    Each entry is cross-checked against the SHA-256 fingerprint recorded in
    ROOTS.json (whose values were verified against the publishers' pages at
    pin time); a mismatch raises rather than silently trusting.
    """
    import json

    directory = _assets_dir()
    index = json.loads((directory / "ROOTS.json").read_text(encoding="utf-8"))
    out: list[tuple[str, x509.Certificate]] = []
    for entry in index.get("roots", []):
        certs = _load_pem_certs(directory / entry["file"])
        if not certs:
            raise FileNotFoundError(f"pinned TSA root missing: {entry['file']}")
        for cert in certs:
            fp = cert.fingerprint(hashes.SHA256()).hex()
            if fp != entry["sha256_fingerprint"].replace(":", "").lower():
                raise ValueError(
                    f"pinned TSA root {entry['file']} fingerprint mismatch: "
                    f"got {fp}, ROOTS.json pins {entry['sha256_fingerprint']}"
                )
            out.append((entry["name"], cert))
    return out


def load_pinned_tsa_extra_certs() -> list[tuple[str, x509.Certificate]]:
    """Pinned TSA *signer* certificates (not roots).

    Older tokens were requested without certReq and carry no certificates;
    these extras let the validator locate their signer. They never terminate
    a chain on their own.
    """
    import json

    directory = _assets_dir()
    index = json.loads((directory / "ROOTS.json").read_text(encoding="utf-8"))
    out: list[tuple[str, x509.Certificate]] = []
    for entry in index.get("extra_signer_certs", []):
        for cert in _load_pem_certs(directory / entry["file"]):
            out.append((entry["name"], cert))
    return out


def load_user_tsa_roots() -> list[x509.Certificate]:
    """Operator-supplied roots from EPI_TSA_TRUST_ROOTS (os.pathsep-separated PEM paths)."""
    import os

    raw = os.environ.get("EPI_TSA_TRUST_ROOTS", "").strip()
    if not raw:
        return []
    out: list[x509.Certificate] = []
    for part in raw.split(os.pathsep):
        part = part.strip().strip("\"'")
        if part:
            out.extend(_load_pem_certs(Path(part)))
    return out


def load_pem_roots(paths: list[str]) -> list[x509.Certificate]:
    """Load extra trust roots from PEM files (backing for `epi verify --tsa-root`)."""
    out: list[x509.Certificate] = []
    for part in paths or []:
        out.extend(_load_pem_certs(Path(part)))
    return out


def _find_signer_cert(sid, token_asn1: list, extra: list[x509.Certificate]):
    """Locate the signer certificate by SignerIdentifier.

    Searches token certificates, then extra_certs, then pinned signer extras.
    Returns (cryptography_cert, found_where) or (None, None).
    """
    candidates: list[tuple[str, x509.Certificate]] = []
    for cert in _asn1_certs_to_crypto(token_asn1):
        candidates.append(("token", cert))
    for cert in extra:
        candidates.append(("extra", cert))
    try:
        for _name, cert in load_pinned_tsa_extra_certs():
            candidates.append(("pinned", cert))
    except Exception:
        pass

    choice = sid.name
    chosen = sid.chosen
    if choice == "issuer_and_serial_number":
        try:
            want_issuer_der = bytes(chosen["issuer"].dump())
            want_serial = int(chosen["serial_number"].native)
        except Exception:
            return None, None
        for where, cert in candidates:
            try:
                asn1_cert = asn1_x509.Certificate.load(
                    cert.public_bytes(serialization.Encoding.DER)
                )
                if bytes(asn1_cert["tbs_certificate"]["issuer"].dump()) == want_issuer_der and (
                    int(asn1_cert["tbs_certificate"]["serial_number"].native) == want_serial
                ):
                    return cert, where
            except Exception:
                continue
        return None, None
    if choice == "subject_key_identifier":
        try:
            want_ski = bytes(chosen.native)
        except Exception:
            return None, None
        for where, cert in candidates:
            try:
                ski = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
                if bytes(ski.value.digest) == want_ski:
                    return cert, where
            except x509.ExtensionNotFound:
                continue
            except Exception:
                continue
        return None, None
    return None, None


def _check_ess_binding(signer_infos_attrs, signer_der: bytes) -> str | None:
    """Verify ESS signing-certificate(-v2) attributes bind the signer cert.

    Returns None on success (or when absent), else a human detail string.
    """
    for attr in signer_infos_attrs or []:
        try:
            oid = attr["type"].dotted
        except Exception:
            continue
        if oid not in (ESS_V1_OID, ESS_V2_OID):
            continue
        try:
            values = attr["values"]
            if not values:
                return "ESS attribute present but empty"
            ess = values[0].parsed if hasattr(values[0], "parsed") else values[0]
            first = ess["certs"][0]
            claimed = bytes(first["cert_hash"].native)
            if oid == ESS_V2_OID:
                algo = first["hash_algorithm"]["algorithm"].native
                hasher = _HASHLIB_BY_NAME.get(str(algo).lower())
                if hasher is None:
                    return f"ESS binding uses unsupported hash {algo}"
                actual = hasher(signer_der).digest()
            else:
                actual = hashlib.sha1(signer_der).digest()
            if claimed != actual:
                return (
                    "ESS signing-certificate attribute names a different "
                    "certificate than the signer"
                )
        except Exception as exc:
            return f"ESS signing-certificate attribute unparseable ({exc})"
    return None


def _verify_cms_signature(
    signer_cert: x509.Certificate,
    signed_attrs_dump: bytes,
    signature: bytes,
    digest_algo_name: str,
    sig_algo_name: str,
    sig_algo_params,
) -> bool:
    # DER of signedAttrs re-tagged IMPLICIT [0] -> SET OF (CMS signs the SET).
    signed_bytes = b"\x31" + signed_attrs_dump[1:]
    digest_name = str(digest_algo_name).lower()
    hash_ctor = _HASHLIB_BY_NAME.get(digest_name)
    if hash_ctor is None:
        return False
    # Map to a cryptography hash object.
    if digest_name == "sha256":
        digest_alg = hashes.SHA256()
    elif digest_name == "sha384":
        digest_alg = hashes.SHA384()
    elif digest_name == "sha512":
        digest_alg = hashes.SHA512()
    elif digest_name == "sha1":
        digest_alg = hashes.SHA1()
    else:
        return False
    pub = signer_cert.public_key()
    try:
        if sig_algo_name == "rsassa_pss":
            salt_len = digest_alg.digest_size
            try:
                params = sig_algo_params.native if sig_algo_params else {}
                if isinstance(params, dict) and params.get("salt_length") is not None:
                    salt_len = int(params["salt_length"])
            except Exception:
                pass
            if isinstance(pub, ec.EllipticCurvePublicKey):
                return False
            pub.verify(
                signature,
                signed_bytes,
                padding.PSS(mgf=padding.MGF1(digest_alg), salt_length=salt_len),
                digest_alg,
            )
            return True
        if "ecdsa" in sig_algo_name or isinstance(pub, ec.EllipticCurvePublicKey):
            pub.verify(signature, signed_bytes, ec.ECDSA(digest_alg))
            return True
        # RSA PKCS#1 v1.5 (asn1crypto reports rsassa_pkcs1v15).
        pub.verify(signature, signed_bytes, padding.PKCS1v15(), digest_alg)
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


def _build_chain(
    signer: x509.Certificate,
    intermediates: list[x509.Certificate],
    roots: list[tuple[str, x509.Certificate]],
    gen_time,
) -> str | None:
    """Build signer -> ... -> pinned root. Returns the root name or None.

    Links require issuer/subject name equality plus a valid issuer signature;
    every certificate must be valid at genTime. Non-anchor issuers must be CAs.
    Depth is capped to stop pathological chains.
    """
    root_by_der = {r.public_bytes(serialization.Encoding.DER): n for n, r in roots}

    def _valid_at(cert: x509.Certificate) -> bool:
        try:
            return bool(_not_valid_before(cert) <= gen_time <= _not_valid_after(cert))
        except Exception:
            return False

    def _is_ca(cert: x509.Certificate) -> bool:
        try:
            bc = cert.extensions.get_extension_for_class(x509.BasicConstraints)
            return bool(bc.value.ca)
        except x509.ExtensionNotFound:
            return False
        except Exception:
            return False

    # DFS over candidate issuers; token certs + extras are the only intermediates.
    def _dfs(current: x509.Certificate, depth: int, seen: set[bytes]) -> str | None:
        if depth > 6:
            return None
        cur_der = current.public_bytes(serialization.Encoding.DER)
        if cur_der in root_by_der:
            return root_by_der[cur_der] if _valid_at(current) else None
        for cand in intermediates:
            try:
                if cand.subject != current.issuer:
                    continue
                cand_der = cand.public_bytes(serialization.Encoding.DER)
                if cand_der in seen:
                    continue
                current.verify_directly_issued_by(cand)
            except Exception:
                continue
            if not _valid_at(cand):
                continue
            # A non-anchor issuer must be a CA (the anchor itself is trusted by pin).
            if cand_der not in root_by_der and not _is_ca(cand):
                continue
            hit = _dfs(cand, depth + 1, seen | {cand_der})
            if hit:
                return hit
        return None

    if not _valid_at(signer):
        return None
    return _dfs(signer, 0, {signer.public_bytes(serialization.Encoding.DER)})


def validate_tsr(
    blob: bytes | None,
    expected_digest: bytes,
    *,
    trust_roots: list[x509.Certificate] | list[tuple[str, x509.Certificate]] | None = None,
    extra_certs: list[x509.Certificate] | None = None,
) -> TsaValidation:
    """Validate one RFC 3161 token against an expected message imprint.

    Stops at the first failure, ordered to distinguish tampering from
    missing trust: malformed -> not_granted -> imprint -> signer location ->
    attributes -> signature -> certificate -> chain.

    trust_roots may be bare certificates (named by subject) or
    (name, certificate) pairs (e.g. from load_pinned_tsa_roots).
    """
    if not blob:
        return _fail("absent", "no timestamp token was collected at seal time")
    try:
        expected = bytes(expected_digest)
    except Exception:
        return _fail("malformed", "expected digest is not bytes")

    # 1. Parse: accept a full TimeStampResp (what EPI stores) or a bare token.
    token = None
    try:
        resp = tsp.TimeStampResp.load(bytes(blob))
        # asn1crypto reports enumerated PKIStatus as its name string.
        status_native = resp["status"]["status"].native
        status = (
            status_native
            if isinstance(status_native, int)
            else {
                "granted": 0,
                "granted_with_modifications": 1,
                "rejection": 2,
                "waiting": 3,
                "revocation_warning": 4,
                "revocation_notification": 5,
            }.get(str(status_native), -1)
        )
        if status not in (0, 1):
            return _fail(
                "not_granted",
                f"timestamp authority refused the request (RFC 3161 status {status})",
            )
        token_raw = resp["time_stamp_token"]
        if token_raw is None:
            return _fail("not_granted", "timestamp response carries no token")
        # Re-load from DER: a single clean parse, immune to lazy/resolved
        # child state on the response object.
        token = cms.ContentInfo.load(token_raw.dump())
    except Exception:
        token = None
    if token is None:
        try:
            token = cms.ContentInfo.load(bytes(blob))
        except Exception:
            return _fail("malformed", "bytes are neither a TimeStampResp nor a CMS token")

    try:
        if token["content_type"].native != "signed_data":
            return _fail("malformed", "CMS token is not SignedData")
        signed_data = token["content"]
        eci = signed_data["encap_content_info"]
        if eci["content_type"].dotted != TST_INFO_OID:
            return _fail("malformed", "SignedData does not encapsulate TSTInfo")
        # Bind once: repeated child resolution on one object is not re-entrant
        # in every asn1crypto path, so every later step reuses this handle.
        encap_content_obj = eci["content"]
        tst = encap_content_obj.parsed
        if not isinstance(tst, tsp.TSTInfo):
            return _fail("malformed", "encapsulated content is not TSTInfo")
    except Exception:
        return _fail("malformed", "token structure is not a valid timestamp SignedData")

    try:
        imprint = tst["message_imprint"]
        algo_name = str(imprint["hash_algorithm"]["algorithm"].native).lower()
        imprinted = bytes(imprint["hashed_message"].native)
        gen_time = tst["gen_time"].native
        if gen_time.tzinfo is None:
            gen_time = gen_time.replace(tzinfo=timezone.utc)
        serial = int(tst["serial_number"].native)
        policy_oid = tst["policy"].dotted
    except Exception:
        return _fail("malformed", "TSTInfo fields are unreadable")

    # 3. Imprint check (before any signature work: a wrong digest is decisive).
    if algo_name not in IMPRINT_ALGORITHMS:
        return _fail(
            "imprint_mismatch",
            f"token imprints with {algo_name}, not a SHA-2 digest EPI accepts",
            gen_time=_utc_iso(gen_time),
            serial=serial,
            policy_oid=policy_oid,
            hash_algorithm=algo_name,
        )
    if imprinted != expected:
        return _fail(
            "imprint_mismatch",
            "token's message imprint does not match the sealed bytes",
            gen_time=_utc_iso(gen_time),
            serial=serial,
            policy_oid=policy_oid,
            hash_algorithm=algo_name,
        )

    # 4. SignerInfo: exactly one expected.
    try:
        signer_infos = list(signed_data["signer_infos"])
    except Exception:
        return _fail("malformed", "SignerInfos are unreadable")
    if len(signer_infos) != 1:
        return _fail(
            "malformed",
            f"token carries {len(signer_infos)} SignerInfos, expected exactly one",
        )
    signer_info = signer_infos[0]

    token_certs = list(signed_data["certificates"] or [])
    signer_cert, _where = _find_signer_cert(signer_info["sid"], token_certs, list(extra_certs or []))
    try:
        tsa_subject = (
            signer_cert.subject.rfc4514_string() if signer_cert is not None else None
        )
    except Exception:
        tsa_subject = None
    if signer_cert is None:
        return _fail(
            "untrusted",
            "token carries no certificate identifying its signer "
            "(older tokens were requested without certReq); "
            "pin the TSA certificate and retry",
            gen_time=_utc_iso(gen_time),
            tsa_subject=None,
            serial=serial,
            policy_oid=policy_oid,
            hash_algorithm=algo_name,
        )

    # 5. Signed attributes.
    try:
        signed_attrs = signer_info["signed_attrs"]
    except Exception:
        signed_attrs = None
    if signed_attrs is None:
        return _fail(
            "malformed",
            "SignerInfo carries no signed attributes to verify",
            gen_time=_utc_iso(gen_time),
            tsa_subject=tsa_subject,
            serial=serial,
            policy_oid=policy_oid,
            hash_algorithm=algo_name,
        )
    try:
        attr_by_oid = {a["type"].dotted: a for a in signed_attrs}
        content_type_attr = attr_by_oid.get("1.2.840.113549.1.9.3")
        try:
            ct_native = content_type_attr["values"][0].native if content_type_attr else None
        except Exception:
            ct_native = None
        if ct_native != "tst_info":
            return _fail(
                "bad_signature",
                "signed content-type attribute is not tst_info",
                gen_time=_utc_iso(gen_time),
                tsa_subject=tsa_subject,
                serial=serial,
                policy_oid=policy_oid,
                hash_algorithm=algo_name,
            )
        md_attr = attr_by_oid.get("1.2.840.113549.1.9.4")
        if md_attr is None:
            return _fail(
                "bad_signature",
                "signed attributes carry no message-digest",
                gen_time=_utc_iso(gen_time),
                tsa_subject=tsa_subject,
                serial=serial,
                policy_oid=policy_oid,
                hash_algorithm=algo_name,
            )
        digest_algo_name = str(signer_info["digest_algorithm"]["algorithm"].native)
        hasher = _HASHLIB_BY_NAME.get(digest_algo_name.lower())
        if hasher is None:
            return _fail(
                "malformed",
                f"signer uses unsupported digest {digest_algo_name}",
                gen_time=_utc_iso(gen_time),
                tsa_subject=tsa_subject,
                serial=serial,
                policy_oid=policy_oid,
                hash_algorithm=algo_name,
            )
        raw_octets = _tst_raw_octets(encap_content_obj)
        if bytes(md_attr["values"][0].native) != hasher(raw_octets).digest():
            return _fail(
                "bad_signature",
                "message-digest attribute does not match the timestamped bytes",
                gen_time=_utc_iso(gen_time),
                tsa_subject=tsa_subject,
                serial=serial,
                policy_oid=policy_oid,
                hash_algorithm=algo_name,
            )
    except TsaValidation:
        raise
    except Exception as exc:
        return _fail(
            "malformed",
            f"signed attributes are unreadable ({exc})",
            gen_time=_utc_iso(gen_time),
            tsa_subject=tsa_subject,
            serial=serial,
            policy_oid=policy_oid,
            hash_algorithm=algo_name,
        )

    # ESS signer binding (when the TSA includes it).
    try:
        signer_der = signer_cert.public_bytes(serialization.Encoding.DER)
    except Exception:
        signer_der = b""
    ess_problem = _check_ess_binding(signed_attrs, signer_der)
    if ess_problem:
        return _fail(
            "bad_signature",
            ess_problem,
            gen_time=_utc_iso(gen_time),
            tsa_subject=tsa_subject,
            serial=serial,
            policy_oid=policy_oid,
            hash_algorithm=algo_name,
        )

    # 6. Signature over DER(signedAttrs) re-tagged as SET OF.
    try:
        signature = bytes(signer_info["signature"].native)
        signed_attrs_dump = bytes(signed_attrs.dump())
        sig_algo = signer_info["signature_algorithm"]
        sig_algo_name = str(sig_algo["algorithm"].native)
        sig_params = sig_algo["parameters"]
    except Exception:
        return _fail(
            "bad_signature",
            "signature block is unreadable",
            gen_time=_utc_iso(gen_time),
            tsa_subject=tsa_subject,
            serial=serial,
            policy_oid=policy_oid,
            hash_algorithm=algo_name,
        )
    if not _verify_cms_signature(
        signer_cert,
        signed_attrs_dump,
        signature,
        digest_algo_name,
        sig_algo_name,
        sig_params,
    ):
        return _fail(
            "bad_signature",
            "CMS signature does not verify with the signer certificate",
            gen_time=_utc_iso(gen_time),
            tsa_subject=tsa_subject,
            serial=serial,
            policy_oid=policy_oid,
            hash_algorithm=algo_name,
        )

    # 7. Signer certificate authorisation and lifetime.
    try:
        eku = signer_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        eku_ok = ExtendedKeyUsageOID.TIME_STAMPING in eku.value and eku.critical
    except x509.ExtensionNotFound:
        eku_ok = False
    except Exception:
        eku_ok = False
    if not eku_ok:
        return _fail(
            "cert_invalid",
            "signer certificate lacks critical timeStamping extended key usage",
            gen_time=_utc_iso(gen_time),
            tsa_subject=tsa_subject,
            serial=serial,
            policy_oid=policy_oid,
            hash_algorithm=algo_name,
        )
    try:
        if not (_not_valid_before(signer_cert) <= gen_time <= _not_valid_after(signer_cert)):
            return _fail(
                "cert_invalid",
                "timestamp was issued outside the signer certificate's validity",
                gen_time=_utc_iso(gen_time),
                tsa_subject=tsa_subject,
                serial=serial,
                policy_oid=policy_oid,
                hash_algorithm=algo_name,
            )
    except Exception:
        return _fail(
            "cert_invalid",
            "signer certificate validity is unreadable",
            gen_time=_utc_iso(gen_time),
            tsa_subject=tsa_subject,
            serial=serial,
            policy_oid=policy_oid,
            hash_algorithm=algo_name,
        )

    # 8. Chain to a pinned root.
    if trust_roots is None:
        try:
            roots = load_pinned_tsa_roots()
        except Exception as exc:
            return _fail(
                "untrusted",
                f"pinned TSA roots are unloadable ({exc})",
                gen_time=_utc_iso(gen_time),
                tsa_subject=tsa_subject,
                serial=serial,
                policy_oid=policy_oid,
                hash_algorithm=algo_name,
            )
    else:
        roots = []
        for item in trust_roots:
            if isinstance(item, (tuple, list)) and len(item) == 2:
                roots.append((str(item[0]), item[1]))
            else:
                try:
                    roots.append((item.subject.rfc4514_string(), item))
                except Exception:
                    continue
    try:
        intermediates = _asn1_certs_to_crypto(token_certs) + list(extra_certs or [])
        # Pinned roots double as candidate issuers (e.g. the self-signed G4
        # completes the chain where the token only carries its cross-signed
        # twin); termination still requires landing on a pinned root.
        intermediates.extend([c for _, c in roots])
        try:
            for _n, _c in load_pinned_tsa_extra_certs():
                intermediates.append(_c)
        except Exception:
            pass
        root_name = _build_chain(signer_cert, intermediates, roots, gen_time)
    except Exception:
        root_name = None
    if not root_name:
        try:
            user_roots = load_user_tsa_roots()
            if user_roots:
                root_name = _build_chain(
                    signer_cert,
                    intermediates,
                    [(c.subject.rfc4514_string(), c) for c in user_roots],
                    gen_time,
                )
        except Exception:
            root_name = None
    if not root_name:
        return _fail(
            "untrusted",
            "signer chains to no pinned root; supply it with --tsa-root",
            gen_time=_utc_iso(gen_time),
            tsa_subject=tsa_subject,
            serial=serial,
            policy_oid=policy_oid,
            hash_algorithm=algo_name,
        )

    # 9. Valid.
    return TsaValidation(
        status="valid",
        gen_time=_utc_iso(gen_time),
        tsa_subject=tsa_subject,
        tsa_root=root_name,
        serial=serial,
        policy_oid=policy_oid,
        hash_algorithm=algo_name,
        detail=f"token is signed by {tsa_subject}, chained to pinned root {root_name!r}",
    )
