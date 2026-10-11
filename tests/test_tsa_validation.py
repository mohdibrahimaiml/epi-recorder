"""Offline RFC 3161 timestamp validation (WP1a). No network: every token comes
from a throwaway test TSA built with cryptography + asn1crypto, except the
explicitly-marked manual live check at the bottom."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

import pytest
from asn1crypto import cms, tsp, x509 as asn1_x509
from asn1crypto.core import ParsableOctetString
from asn1crypto.tsp import SigningCertificateV2
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from epi_core.tsa_verify import load_pinned_tsa_roots, validate_tsr

SIGNED_DATA_OID_TLV = bytes.fromhex("06092a864886f70d010702")
STATUS_GRANTED = bytes.fromhex("3003020100")
STATUS_REJECTION = bytes.fromhex("3003020102")


def _der_len(n: int) -> bytes:
    if n < 128:
        return bytes([n])
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _seq(body: bytes) -> bytes:
    return b"\x30" + _der_len(len(body)) + body


def _a0(inner: bytes) -> bytes:
    return b"\xa0" + _der_len(len(inner)) + inner


def _split_tlvs(body: bytes) -> list[bytes]:
    out: list[bytes] = []
    pos = 0
    while pos < len(body):
        p = pos + 1
        first = body[p]
        p += 1
        if first & 0x80:
            n = first & 0x7F
            length = int.from_bytes(body[p : p + n], "big")
            p += n
        else:
            length = first
        nxt = p + length
        out.append(bytes(body[pos:nxt]))
        pos = nxt
    return out


def _rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class MiniPKI:
    """Throwaway TSA: self-signed root CA + timestamping end-entity."""

    __test__ = False

    def __init__(
        self,
        *,
        with_eku: bool = True,
        eku_critical: bool = True,
        tsa_not_before: datetime = datetime(2024, 1, 1, tzinfo=timezone.utc),
        tsa_not_after: datetime = datetime(2030, 1, 1, tzinfo=timezone.utc),
    ) -> None:
        self.root_key = _rsa_key()
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test TSA Root")])
        self.root_cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(self.root_key.public_key())
            .serial_number(1)
            .not_valid_before(datetime(2020, 1, 1, tzinfo=timezone.utc))
            .not_valid_after(datetime(2040, 1, 1, tzinfo=timezone.utc))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(self.root_key, hashes.SHA256())
        )
        self.tsa_key = _rsa_key()
        builder = (
            x509.CertificateBuilder()
            .subject_name(
                x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test TSA Signer")])
            )
            .issuer_name(name)
            .public_key(self.tsa_key.public_key())
            .serial_number(2)
            .not_valid_before(tsa_not_before)
            .not_valid_after(tsa_not_after)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        )
        if with_eku:
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]),
                critical=eku_critical,
            )
        self.tsa_cert = builder.sign(self.root_key, hashes.SHA256())
        self.tsa_asn1 = asn1_x509.Certificate.load(
            self.tsa_cert.public_bytes(serialization.Encoding.DER)
        )

    def root_pem_file(self, path: Path) -> Path:
        path.write_bytes(
            self.root_cert.public_bytes(serialization.Encoding.PEM)
        )
        return path


def make_tsr(
    digest: bytes,
    pki: MiniPKI,
    *,
    gen_time: datetime = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc),
    serial: int = 12345,
    nonce: int | None = None,
    include_certs: bool = True,
    status: bytes = STATUS_GRANTED,
    sign_key=None,
    mutate_tst: bool = False,
    ess_mode: str = "ok",
    ess_other_cert: x509.Certificate | None = None,
) -> bytes:
    """Build a real TimeStampResp DER with the test TSA.

    mutate_tst flips one TSTInfo byte after the message-digest attribute is
    computed (signature not redone) -> bad_signature. ess_mode "other" binds
    the ESS attribute to a different certificate.
    """
    tst = tsp.TSTInfo(
        {
            "version": 1,
            "policy": "1.2.3.4.1",
            "message_imprint": {
                "hash_algorithm": {"algorithm": "sha256"},
                "hashed_message": bytes(digest),
            },
            "serial_number": serial,
            "gen_time": gen_time,
            "nonce": nonce if nonce is not None else int.from_bytes(
                secrets.token_bytes(8), "big"
            ),
        }
    )
    raw = tst.dump()
    md = hashlib.sha256(raw).digest()
    if mutate_tst:
        # Same TSTInfo shape, one field value changed after the
        # message-digest attribute was computed (signature not redone).
        raw = tsp.TSTInfo(
            {
                "version": 1,
                "policy": "1.2.3.4.1",
                "message_imprint": {
                    "hash_algorithm": {"algorithm": "sha256"},
                    "hashed_message": bytes(digest),
                },
                "serial_number": serial + 1,
                "gen_time": gen_time,
                "nonce": tst["nonce"].native,
            }
        ).dump()
        assert len(raw) == len(tst.dump())

    if ess_mode == "omit":
        ess_attrs: list = []
    else:
        target = pki.tsa_cert if ess_mode == "ok" else ess_other_cert
        assert target is not None
        ess = SigningCertificateV2(
            {
                "certs": [
                    {
                        "hash_algorithm": {"algorithm": "sha256"},
                        "cert_hash": hashlib.sha256(
                            target.public_bytes(serialization.Encoding.DER)
                        ).digest(),
                    }
                ]
            }
        )
        ess_attrs = [{"type": "signing_certificate_v2", "values": [ess]}]

    attrs = cms.CMSAttributes(
        [
            {"type": "content_type", "values": ["tst_info"]},
            {"type": "message_digest", "values": [md]},
            *ess_attrs,
        ]
    )
    signed_bytes = b"\x31" + attrs.dump()[1:]
    key = sign_key if sign_key is not None else pki.tsa_key
    signature = key.sign(signed_bytes, padding.PKCS1v15(), hashes.SHA256())

    si = {
        "version": 1,
        "sid": {
            "issuer_and_serial_number": {
                "issuer": pki.tsa_asn1["tbs_certificate"]["issuer"],
                "serial_number": 2,
            }
        },
        "digest_algorithm": {"algorithm": "sha256"},
        "signed_attrs": attrs,
        "signature_algorithm": {"algorithm": "sha256_rsa"},
        "signature": signature,
    }
    inner = b"\x04" + _der_len(len(raw)) + raw
    po = ParsableOctetString.load(inner)
    eci_good = cms.EncapsulatedContentInfo(
        {"content_type": "tst_info", "content": po}
    ).dump()
    # asn1crypto 1.5.1 drops the [0] EXPLICIT wrapper when
    # EncapsulatedContentInfo is built nested inside SignedData, so build
    # nested (correct except the wrapper), splice the standalone encoding in,
    # and re-emit the outer length.
    broken = cms.SignedData(
        {
            "version": 3,
            "digest_algorithms": [{"algorithm": "sha256"}],
            "encap_content_info": {
                "content_type": "tst_info",
                "content": po,
            },
            **(
                {"certificates": [pki.tsa_asn1]} if include_certs else {}
            ),
            "signer_infos": [si],
        }
    ).dump()
    assert broken[0] == 0x30
    p = 1
    first = broken[p]
    p += 1
    if first & 0x80:
        p += first & 0x7F
    kids = _split_tlvs(broken[p:])
    assert len(kids) >= 4
    kids[2] = eci_good
    sd_fixed = _seq(b"".join(kids))

    ci_der = _seq(SIGNED_DATA_OID_TLV + _a0(sd_fixed))
    return _seq(status + ci_der)


@pytest.fixture()
def pki() -> MiniPKI:
    return MiniPKI()


DIGEST = hashlib.sha256(b"sealed-payload").digest()


def test_valid_token(pki: MiniPKI) -> None:
    token = make_tsr(DIGEST, pki)
    v = validate_tsr(token, DIGEST, trust_roots=[pki.root_cert])
    assert v.status == "valid", v.detail
    assert v.gen_time == "2026-05-05T12:00:00Z"
    assert v.hash_algorithm == "sha256"
    assert v.serial == 12345
    assert v.policy_oid == "1.2.3.4.1"
    assert "Test TSA Signer" in (v.tsa_subject or "")


def test_imprint_mismatch(pki: MiniPKI) -> None:
    token = make_tsr(DIGEST, pki)
    v = validate_tsr(token, b"\x01" * 32, trust_roots=[pki.root_cert])
    assert v.status == "imprint_mismatch"


def test_flipped_tst_byte_is_bad_signature(pki: MiniPKI) -> None:
    token = make_tsr(DIGEST, pki, mutate_tst=True)
    v = validate_tsr(token, DIGEST, trust_roots=[pki.root_cert])
    assert v.status == "bad_signature", v.detail


def test_wrong_signing_key_is_bad_signature(pki: MiniPKI) -> None:
    token = make_tsr(DIGEST, pki, sign_key=_rsa_key())
    v = validate_tsr(token, DIGEST, trust_roots=[pki.root_cert])
    assert v.status == "bad_signature", v.detail


def test_missing_eku_is_cert_invalid() -> None:
    bad_pki = MiniPKI(with_eku=False)
    token = make_tsr(DIGEST, bad_pki)
    v = validate_tsr(token, DIGEST, trust_roots=[bad_pki.root_cert])
    assert v.status == "cert_invalid", v.detail


def test_gen_time_outside_validity_is_cert_invalid(pki: MiniPKI) -> None:
    token = make_tsr(
        DIGEST, pki, gen_time=datetime(2035, 6, 1, tzinfo=timezone.utc)
    )
    v = validate_tsr(token, DIGEST, trust_roots=[pki.root_cert])
    assert v.status == "cert_invalid", v.detail


def test_unknown_root_is_untrusted(pki: MiniPKI) -> None:
    other = MiniPKI()
    token = make_tsr(DIGEST, pki)
    v = validate_tsr(token, DIGEST, trust_roots=[other.root_cert])
    assert v.status == "untrusted", v.detail


def test_signer_via_extra_certs_valid(pki: MiniPKI) -> None:
    token = make_tsr(DIGEST, pki, include_certs=False)
    v = validate_tsr(token, DIGEST, trust_roots=[pki.root_cert],
                     extra_certs=[pki.tsa_cert])
    assert v.status == "valid", v.detail


def test_rejection_status_is_not_granted(pki: MiniPKI) -> None:
    token = make_tsr(DIGEST, pki, status=STATUS_REJECTION)
    v = validate_tsr(token, DIGEST, trust_roots=[pki.root_cert])
    assert v.status == "not_granted"


def test_validity_fallback_without_utc_properties() -> None:
    """cryptography < 42 lacks not_valid_before_utc: the shim must still work."""
    import types
    from datetime import datetime

    from epi_core.tsa_verify import _not_valid_after, _not_valid_before

    naive_before = datetime(2024, 1, 1)
    naive_after = datetime(2030, 1, 1)
    stub = types.SimpleNamespace(
        not_valid_before=naive_before, not_valid_after=naive_after
    )
    assert not hasattr(stub, "not_valid_before_utc")
    before = _not_valid_before(stub)
    after = _not_valid_after(stub)
    assert before.tzinfo is not None and after.tzinfo is not None
    assert (before.replace(tzinfo=None), after.replace(tzinfo=None)) == (
        naive_before,
        naive_after,
    )


def test_garbage_is_malformed(pki: MiniPKI) -> None:
    v = validate_tsr(b"definitely not a token", DIGEST, trust_roots=[pki.root_cert])
    assert v.status == "malformed"
    v2 = validate_tsr(b"", DIGEST, trust_roots=[pki.root_cert])
    assert v2.status == "absent"


def test_ess_binding_to_other_cert_not_valid(pki: MiniPKI) -> None:
    other = MiniPKI()
    token = make_tsr(DIGEST, pki, ess_mode="other", ess_other_cert=other.tsa_cert)
    v = validate_tsr(token, DIGEST, trust_roots=[pki.root_cert])
    assert v.status != "valid", v.detail


def _seal_with_test_tsa(monkeypatch, tmp_path: Path, pki: MiniPKI, out: Path,
                        n_steps: int = 3) -> Path:
    def fake_submit(digest_hex: str, url: str = "") -> bytes:
        return make_tsr(bytes.fromhex(digest_hex), pki)

    monkeypatch.setattr("epi_core.notarize._submit_rfc3161", fake_submit)
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    # Hermetic keys: never touch the developer's real ~/.epi keystore.
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "home" / "keys"))
    monkeypatch.setenv("EPI_TSA_URLS", "https://tsa.example.test/tsr")
    # Notarization must be on: other tests in the same process may leak
    # EPI_NOTARIZE=0 via os.environ (monkeypatch always wins for this test).
    monkeypatch.setenv("EPI_NOTARIZE", "1")
    from epi_recorder import record

    with record(str(out)) as epi:
        for i in range(n_steps):
            epi.log_step("llm.request", {"provider": "openai", "n": i})
    return out


def _run_verify_json(out: Path, capsys, **kwargs) -> dict:
    import typer

    from epi_cli.verify import verify_command

    try:
        verify_command(None, out, True, False, None, **kwargs)
    except typer.Exit:
        pass
    return json.loads(capsys.readouterr().out)


def test_end_to_end_record_verify_and_imprint(
    monkeypatch, tmp_path: Path, capsys, pki: MiniPKI
) -> None:
    out = tmp_path / "run.epi"
    _seal_with_test_tsa(monkeypatch, tmp_path, pki, out)
    root_pem = pki.root_pem_file(tmp_path / "test-root.pem")

    from epi_core.container import EPIContainer
    from epi_core.notarize import compute_seal_imprint, normalize_imprint_time

    manifest = EPIContainer.read_manifest(out)
    notar = EPIContainer.read_member_json(out, "artifacts/notarization/notarization.json")
    assert notar.get("imprint_scheme") == "epi-tsa-imprint/v1"
    recomputed = compute_seal_imprint(
        str(manifest.workflow_id),
        normalize_imprint_time(manifest.created_at),
        notar.get("imprinted_public_key"),
        dict(manifest.file_manifest or {}),
    )
    assert recomputed == notar["imprinted_digest"]

    report = _run_verify_json(out, capsys, tsa_root=[root_pem])
    assert report["facts"]["timestamp_verified"] is True
    seal = report["timestamps"]["seal"]
    assert len(seal) == 1 and seal[0]["status"] == "valid"
    assert seal[0]["gen_time"] == "2026-05-05T12:00:00Z"
    assert report["decision"]["status"] in ("PASS", "WARN")


def test_end_to_end_tampered_token_fails(
    monkeypatch, tmp_path: Path, capsys, pki: MiniPKI
) -> None:
    import copy

    import typer

    out = tmp_path / "run.epi"
    _seal_with_test_tsa(monkeypatch, tmp_path, pki, out)
    root_pem = pki.root_pem_file(tmp_path / "test-root.pem")

    from epi_core.container import EPIContainer
    from epi_core.keys import KeyManager
    from epi_core.trust import sign_manifest

    ws = tmp_path / "ws"
    EPIContainer.unpack(out, ws)
    token_path = ws / "artifacts" / "notarization" / "tsa_reply.tsr"
    raw = bytearray(token_path.read_bytes())
    raw[-1] ^= 0xFF  # break the CMS signature, keep the structure parseable
    token_path.write_bytes(bytes(raw))

    km = KeyManager()
    key_name = km.list_keys()[0]["name"]
    private_key = km.load_private_key(key_name)
    manifest = EPIContainer.read_manifest(out)
    out2 = tmp_path / "tampered.epi"
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    EPIContainer.pack(
        ws,
        copy.deepcopy(manifest),
        out2,
        signer_function=lambda current: sign_manifest(current, private_key, key_name),
        preserve_generated=True,
    )

    from epi_cli.verify import verify_command

    with pytest.raises(typer.Exit):
        verify_command(None, out2, True, False, None, tsa_root=[root_pem])
    report = json.loads(capsys.readouterr().out)
    assert report["decision"]["status"] == "FAIL"
    assert report["timestamps"]["seal"][0]["status"] == "bad_signature"
    # The tamper detail IS the decision reason (no stale policy PASS-text
    # survives), and file integrity stays as measured: the hashes verified,
    # it is the time attestation that is broken.
    assert report["decision"]["reason"] == report["timestamps"]["seal"][0]["detail"]
    assert "Integrity verified" not in report["decision"]["reason"]
    assert report["facts"]["integrity_ok"] is True

    with pytest.raises(typer.Exit):
        verify_command(None, out2, False, False, None, tsa_root=[root_pem])
    human = capsys.readouterr().out
    assert "INVALID" in human


def test_legacy_sample_reports_legacy_not_fail(capsys) -> None:
    from epi_cli.verify import verify_command

    sample = Path(__file__).resolve().parents[1] / "docs" / "assets" / "sample-hello.epi"
    import typer

    try:
        verify_command(None, sample, True, False, None)
    except typer.Exit:
        pass
    report = json.loads(capsys.readouterr().out)
    seal = report["timestamps"]["seal"]
    assert seal and seal[0]["status"] == "legacy"
    assert report["facts"]["timestamp_verified"] is False
    # Legacy tokens never drive the decision.
    assert "timestamp" not in report["decision"].get("reason", "").lower()


def test_checkpoint_wrong_head_is_timestamp_invalid(tmp_path: Path, pki: MiniPKI) -> None:
    from epi_core.checkpoints import verify_checkpoints
    from epi_core.container import EPIContainer
    from epi_core.schemas import ManifestModel, StepModel
    from epi_core.serialize import get_canonical_hash

    steps: list[dict] = []
    prev = "CHAIN_START"
    for i in range(3):
        model = StepModel(index=i, kind="llm.request", content={"i": i}, prev_hash=prev)
        prev = get_canonical_hash(model, format="json")
        steps.append(model.model_dump(mode="json"))
    real_head = prev
    record_cp = {
        "schema_version": "1.0",
        "index": 0,
        "event_count": 3,
        "chain_head": real_head,
        "tsa_url": "https://tsa.example.test/tsr",
        "tsa_available": True,
        # Token imprints a DIFFERENT head than the record claims.
        "tsa_token_b64": base64.b64encode(make_tsr(b"\x02" * 32, pki)).decode("ascii"),
        "created_at": "2026-05-05T12:00:00Z",
    }
    ws = tmp_path / "ws"
    (ws / "artifacts" / "checkpoints").mkdir(parents=True)
    (ws / "steps.jsonl").write_text(
        "\n".join(json.dumps(s) for s in steps) + "\n", encoding="utf-8"
    )
    (ws / "artifacts" / "checkpoints" / "000000.json").write_text(
        json.dumps(record_cp), encoding="utf-8"
    )
    out = tmp_path / "cp.epi"
    manifest = ManifestModel()
    EPIContainer.pack(ws, manifest, out)

    ok, messages, _records = verify_checkpoints(out, steps)
    assert ok is False
    assert any("CHECKPOINT TIMESTAMP INVALID" in m for m in messages)


def test_pinned_roots_ship_with_package() -> None:
    from importlib.resources import files

    from epi_core import __version__ as core_version

    base = files("epi_core") / "assets" / "tsa_roots"
    assert (base / "ROOTS.json").is_file()
    roots = load_pinned_tsa_roots()
    assert len(roots) >= 3
    assert {name for name, _cert in roots} >= {
        "FreeTSA Root CA",
        "DigiCert Trusted Root G4",
        "DigiCert Assured ID Root CA",
    }


@pytest.mark.slow
def test_built_wheel_contains_tsa_roots(tmp_path: Path) -> None:
    """Built wheel must include the pinned TSA roots (not only source trees)."""
    import zipfile

    from epi_core import __version__ as core_version

    dist = Path(__file__).resolve().parents[1] / "dist"
    wheels = sorted(
        dist.glob(f"epi_recorder-{core_version}*.whl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not wheels:
        pytest.skip("No wheel in dist/; run `python -m build` first or full packaging CI")
    with zipfile.ZipFile(wheels[0]) as zf:
        names = zf.namelist()
    assert any(n.endswith("epi_core/assets/tsa_roots/ROOTS.json") for n in names)
    assert any(n.endswith("epi_core/assets/tsa_roots/freetsa_root.pem") for n in names)
    assert any(n.endswith("epi_core/assets/tsa_roots/digicert_g4_root.pem") for n in names)
    assert any(n.endswith("epi_core/tsa_verify.py") for n in names)


@pytest.mark.network
@pytest.mark.skipif(
    os.environ.get("EPI_RUN_NETWORK_TESTS") != "1",
    reason="live TSA check is manual-only (run with EPI_RUN_NETWORK_TESTS=1)",
)
def test_live_tsas_validate_against_pinned_roots() -> None:
    """Manual_PT check: real FreeTSA + DigiCert tokens validate offline.

    Run: EPI_RUN_NETWORK_TESTS=1 pytest tests/test_tsa_validation.py -k live -q
    Paste the output into the PR description.
    """
    import httpx

    from epi_core.notarize import _build_rfc3161_request, _submit_rfc3161

    for url in ("https://freetsa.org/tsr", "http://timestamp.digicert.com"):
        query, nonce = _build_rfc3161_request(hashlib.sha256(url.encode()).digest())
        try:
            resp = httpx.post(
                url,
                content=query,
                headers={"Content-Type": "application/timestamp-query"},
                timeout=30,
            )
        except httpx.HTTPError as exc:
            pytest.skip(f"{url} unreachable from this network ({exc})")
        assert resp.status_code == 200, url
        token = _submit_rfc3161(hashlib.sha256(url.encode()).hexdigest(), url)
        assert token, url
        v = validate_tsr(token, hashlib.sha256(url.encode()).digest())
        assert v.status == "valid", (url, v.status, v.detail)
        print(f"{url}: {v.status} gen_time={v.gen_time} root={v.tsa_root}")


def test_unreadable_signed_attributes_report_malformed_not_crash(
    monkeypatch, pki: MiniPKI
) -> None:
    """A parse error while reading signed attributes must yield 'malformed', never raise."""
    import epi_core.tsa_verify as tv

    digest = hashlib.sha256(b"attrs").digest()
    token = make_tsr(digest, pki)

    def _boom(_obj):
        raise ValueError("odd encoding")

    monkeypatch.setattr(tv, "_tst_raw_octets", _boom)
    result = tv.validate_tsr(token, digest, trust_roots=[pki.root_cert])
    assert result.status == "malformed"
    assert "odd encoding" in result.detail
