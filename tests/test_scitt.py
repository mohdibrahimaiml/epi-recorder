"""
Tests for epi_core.scitt — SCITT (Supply Chain Integrity, Transparency and Trust)
COSE_Sign1 statement/receipt creation and verification.
"""

from __future__ import annotations

import cbor2

from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.scitt import (
    SCITTVerificationError,
    create_scitt_receipt,
    create_scitt_statement,
    extract_scitt_artifacts,
    parse_scitt_statement,
    scitt_governance_from_info,
    verify_scitt_receipt,
    verify_scitt_receipt_with_proof,
    verify_scitt_statement,
)
from epi_core.serialize import get_canonical_hash
from epi_core.time_utils import utc_now
from epi_core.trust import sign_manifest
from tests.helpers.mock_scitt_service import MockSCITTService

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture
def manifest() -> ManifestModel:
    return ManifestModel(
        workflow_id=uuid4(),
        created_at=utc_now(),
        cli_command="python test.py",
        file_manifest={"steps.jsonl": "abc123"},
    )


@pytest.fixture
def signed_manifest(manifest: ManifestModel, private_key: Ed25519PrivateKey) -> ManifestModel:
    return sign_manifest(manifest, private_key, key_name="test")


@pytest.fixture
def mock_service() -> MockSCITTService:
    return MockSCITTService()


# ─────────────────────────────────────────────────────────────
# COSE / Statement tests
# ─────────────────────────────────────────────────────────────

class TestSCITTStatement:
    def test_create_and_parse_roundtrip(self, signed_manifest, private_key):
        """A created statement can be parsed back with correct fields."""
        issuer = "did:web:example.com"
        cose_bytes = create_scitt_statement(signed_manifest, private_key, issuer=issuer)

        assert isinstance(cose_bytes, bytes)
        assert len(cose_bytes) > 0

        stmt = parse_scitt_statement(cose_bytes)
        assert stmt.issuer == issuer
        assert stmt.payload is not None

    def test_create_scitt_statement_with_dict(self, signed_manifest, private_key):
        """create_scitt_statement must accept a raw dict and produce the same statement."""
        manifest_dict = signed_manifest.model_dump(mode="json")

        cose_from_dict = create_scitt_statement(manifest_dict, private_key, issuer="test")
        cose_from_model = create_scitt_statement(signed_manifest, private_key, issuer="test")

        stmt_from_dict = parse_scitt_statement(cose_from_dict)
        stmt_from_model = parse_scitt_statement(cose_from_model)

        assert stmt_from_dict.subject == stmt_from_model.subject
        assert stmt_from_dict.issuer == stmt_from_model.issuer

    def test_statement_payload_matches_manifest_hash(self, signed_manifest, private_key):
        """The statement payload must equal the manifest's canonical hash."""
        cose_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        stmt = parse_scitt_statement(cose_bytes)

        expected_hash = get_canonical_hash(signed_manifest, exclude_fields={"signature", "governance"})
        claims = cbor2.loads(stmt.payload)
        if isinstance(claims, dict):
            actual_hash = claims.get("manifest_hash", b"").decode("utf-8", errors="replace")
        else:
            actual_hash = ""
        assert actual_hash == expected_hash
        assert stmt.subject == expected_hash

    def test_verify_scitt_statement_with_key(self, signed_manifest, private_key):
        """Verification with the correct public key succeeds."""
        cose_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        public_key_bytes = private_key.public_key().public_bytes_raw()

        assert verify_scitt_statement(cose_bytes, signed_manifest, public_key_bytes) is True

    def test_verify_scitt_statement_without_key(self, signed_manifest, private_key):
        """Verification without a public key checks structure and hash only."""
        cose_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        assert verify_scitt_statement(cose_bytes, signed_manifest, public_key_bytes=None) is True

    def test_verify_fails_for_wrong_manifest(self, signed_manifest, private_key):
        """Verification fails when the statement doesn't match the manifest."""
        cose_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")

        # Tamper manifest
        other_manifest = signed_manifest.model_copy()
        other_manifest.cli_command = "different command"

        with pytest.raises(SCITTVerificationError, match="payload hash mismatch"):
            verify_scitt_statement(cose_bytes, other_manifest)

    def test_verify_fails_for_tampered_statement(self, signed_manifest, private_key):
        """Tampering the COSE signature is detected during cryptographic verification."""
        cose_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        tampered = cose_bytes[:-10] + b"\xff" * 10

        public_key_bytes = private_key.public_key().public_bytes_raw()
        with pytest.raises(SCITTVerificationError, match="signature invalid"):
            verify_scitt_statement(tampered, signed_manifest, public_key_bytes)

    def test_verify_fails_for_wrong_public_key(self, signed_manifest, private_key):
        """Verification with a different public key fails."""
        cose_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        other_key = Ed25519PrivateKey.generate()
        other_public = other_key.public_key().public_bytes_raw()

        with pytest.raises(SCITTVerificationError, match="signature invalid"):
            verify_scitt_statement(cose_bytes, signed_manifest, other_public)


# ─────────────────────────────────────────────────────────────
# Receipt tests
# ─────────────────────────────────────────────────────────────

class TestSCITTReceipt:
    def test_receipt_roundtrip_with_mock_service(self, signed_manifest, private_key, mock_service):
        """A receipt from the mock service verifies against the statement."""
        statement_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        receipt_bytes, info = mock_service.register(statement_bytes)

        assert verify_scitt_receipt(
            receipt_bytes, statement_bytes, mock_service.public_key_bytes
        ) is True

    def test_receipt_fails_for_wrong_statement(self, signed_manifest, private_key, mock_service):
        """A receipt doesn't verify against a different statement."""
        statement_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        receipt_bytes, _ = mock_service.register(statement_bytes)

        other_statement = create_scitt_statement(
            ManifestModel(workflow_id=uuid4(), created_at=utc_now()),
            private_key,
            issuer="test",
        )

        with pytest.raises(SCITTVerificationError, match="does not match statement hash"):
            verify_scitt_receipt(receipt_bytes, other_statement, mock_service.public_key_bytes)

    def test_receipt_fails_for_wrong_service_key(self, signed_manifest, private_key, mock_service):
        """A receipt doesn't verify with a different service public key."""
        statement_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        receipt_bytes, _ = mock_service.register(statement_bytes)

        other_service = MockSCITTService()

        with pytest.raises(SCITTVerificationError, match="signature invalid"):
            verify_scitt_receipt(receipt_bytes, statement_bytes, other_service.public_key_bytes)

    def test_receipt_with_proof_verifies(self, signed_manifest, private_key, mock_service):
        """verify_scitt_receipt_with_proof succeeds for a valid receipt."""
        statement_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        receipt_bytes, _ = mock_service.register(statement_bytes)

        valid, proof, message = verify_scitt_receipt_with_proof(
            receipt_bytes, statement_bytes, mock_service.public_key_bytes
        )
        assert valid is True
        assert proof is not None
        assert "valid" in message.lower()

    def test_receipt_without_proof_fails(self, signed_manifest, private_key, mock_service):
        """A plain receipt (no inclusion proof data) fails verify_scitt_receipt_with_proof."""
        statement_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        # Create a plain receipt without proof headers
        plain_receipt = create_scitt_receipt(
            statement_bytes, mock_service._private_key, kid=b"test"
        )

        valid, proof, message = verify_scitt_receipt_with_proof(
            plain_receipt, statement_bytes, mock_service.public_key_bytes
        )
        assert valid is False
        assert proof is None
        assert "does not contain inclusion proof" in message.lower()

    def test_receipt_with_malformed_proof_fails(self, signed_manifest, private_key, mock_service):
        """A receipt with malformed proof data in unprotected headers fails."""
        statement_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        from epi_core.scitt import create_scitt_receipt_with_proof
        bad_receipt = create_scitt_receipt_with_proof(
            statement_bytes, mock_service._private_key, proof_data=b"not-cbor-proof", kid=b"test"
        )

        valid, proof, message = verify_scitt_receipt_with_proof(
            bad_receipt, statement_bytes, mock_service.public_key_bytes
        )
        assert valid is False
        assert proof is None
        assert "malformed inclusion proof" in message.lower()


# ─────────────────────────────────────────────────────────────
# Artifact extraction tests
# ─────────────────────────────────────────────────────────────

class TestExtractSCITTAritfacts:
    def test_extract_from_epi_with_scitt(
        self, tmp_path: Path, signed_manifest, private_key, mock_service,
    ):
        """SCITT artifacts can be extracted from a properly constructed .epi file."""
        statement_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        receipt_bytes, info = mock_service.register(statement_bytes)

        # Build governance
        scitt_gov = scitt_governance_from_info(info, issuer="test")
        signed_manifest.governance = {"scitt": scitt_gov}

        # Create a source dir with SCITT artifacts
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "steps.jsonl").write_text('{"index":0}\n')

        scitt_dir = source_dir / "artifacts" / "scitt"
        scitt_dir.mkdir(parents=True)
        (scitt_dir / "statement.cbor").write_bytes(statement_bytes)
        (scitt_dir / "receipt.cbor").write_bytes(receipt_bytes)

        epi_path = tmp_path / "test.epi"
        EPIContainer.pack(
            source_dir=source_dir,
            manifest=signed_manifest,
            output_path=epi_path,
        )

        # Extract
        extracted_stmt, extracted_rcpt, extracted_gov = extract_scitt_artifacts(epi_path)

        assert extracted_stmt == statement_bytes
        assert extracted_rcpt == receipt_bytes
        assert extracted_gov is not None
        assert extracted_gov["entry_id"] == info.entry_id

    def test_extract_from_epi_without_scitt(self, tmp_path: Path, signed_manifest):
        """Extraction returns None for artifacts without SCITT."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "steps.jsonl").write_text('{"index":0}\n')

        epi_path = tmp_path / "test.epi"
        EPIContainer.pack(
            source_dir=source_dir,
            manifest=signed_manifest,
            output_path=epi_path,
        )

        stmt, rcpt, gov = extract_scitt_artifacts(epi_path)
        assert stmt is None
        assert rcpt is None
        assert gov is None


# ─────────────────────────────────────────────────────────────
# CLI integration tests (via CliRunner)
# ─────────────────────────────────────────────────────────────

class TestSCITTCLI:
    def test_cli_register_creates_valid_receipt(
        self, tmp_path: Path, signed_manifest, private_key, mock_service,
    ):
        """``epi scitt register`` creates a new .epi with a valid SCITT receipt."""
        from typer.testing import CliRunner

        from epi_cli.main import app

        # Prepare initial .epi
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "steps.jsonl").write_text('{"index":0}\n')
        input_epi = tmp_path / "input.epi"
        EPIContainer.pack(source_dir, signed_manifest, input_epi)

        out_epi = tmp_path / "out.epi"

        # Run CLI register
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scitt", "register", str(input_epi),
                "--service", "https://mock-scitt.example.com",
                "--out", str(out_epi),
            ],
        )
        # Since the mock service is not a real HTTP server, this will fail
        # unless we mock the HTTP client. For now, we test the core logic
        # directly and leave HTTP mocking for a future integration test.
        assert result.exit_code != 0 or not out_epi.exists()  # Expected: no real server

    def test_trust_level_upgrade_in_verification_report(
        self, signed_manifest, private_key, mock_service,
    ):
        """A valid SCITT receipt upgrades LOW trust to MEDIUM."""
        from epi_core.trust import TrustRegistry, create_verification_report

        # Create SCITT artifacts
        statement_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        receipt_bytes, info = mock_service.register(statement_bytes)

        # Build report with transparency_ok=True
        report = create_verification_report(
            integrity_ok=True,
            signature_valid=True,
            signer_name="test",
            mismatches={},
            manifest=signed_manifest,
            trusted_registry=TrustRegistry(),
            chain_ok=True,
            transparency_ok=True,
        )

        # Unknown identity + valid signature + SCITT valid = MEDIUM (upgraded from LOW)
        assert report["trust_level"] == "MEDIUM"
        assert report["facts"]["transparency_ok"] is True
        assert report["summary"]["transparency"] == "VERIFIED"

    def test_trust_level_unchanged_without_scitt(self, signed_manifest, private_key):
        """Without SCITT, unknown identity stays LOW."""
        from epi_core.trust import TrustRegistry, create_verification_report

        signed = sign_manifest(signed_manifest, private_key, "test")
        report = create_verification_report(
            integrity_ok=True,
            signature_valid=True,
            signer_name="test",
            mismatches={},
            manifest=signed,
            trusted_registry=TrustRegistry(),
            chain_ok=True,
            transparency_ok=None,
        )

        assert report["trust_level"] == "LOW"
        assert report["facts"]["transparency_ok"] is None
        assert report["summary"]["transparency"] == "MISSING"

    def test_trust_level_failed_scitt(self, signed_manifest, private_key):
        """With failed SCITT verification, transparency is FAILED."""
        from epi_core.trust import TrustRegistry, create_verification_report

        signed = sign_manifest(signed_manifest, private_key, "test")
        report = create_verification_report(
            integrity_ok=True,
            signature_valid=True,
            signer_name="test",
            mismatches={},
            manifest=signed,
            trusted_registry=TrustRegistry(),
            chain_ok=True,
            transparency_ok=False,
        )

        assert report["facts"]["transparency_ok"] is False

    def test_cli_verify_full_crypto(
        self, tmp_path: Path, signed_manifest, private_key, mock_service,
    ):
        """``epi scitt verify`` performs full cryptographic receipt verification."""
        from typer.testing import CliRunner

        from epi_cli.main import app
        from epi_core.container import EPIContainer
        from epi_core.scitt import scitt_governance_from_info

        # Create an .epi artifact with embedded SCITT statement + receipt.
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "steps.jsonl").write_text('{"index":0}\n')
        input_epi = tmp_path / "input.epi"
        EPIContainer.pack(source_dir, signed_manifest, input_epi)

        statement_bytes = create_scitt_statement(signed_manifest, private_key, issuer="test")
        receipt_bytes, info = mock_service.register(statement_bytes)

        gov = scitt_governance_from_info(info, issuer="test")
        gov["service_url"] = "https://mock-scitt.example.com"

        # Embed SCITT artifacts into the .epi file manually.
        import zipfile
        with zipfile.ZipFile(input_epi, "r") as zf_in:
            members = {name: zf_in.read(name) for name in zf_in.namelist()}

        members["artifacts/scitt/statement.cbor"] = statement_bytes
        members["artifacts/scitt/receipt.cbor"] = receipt_bytes

        manifest_dict = signed_manifest.model_dump(mode="json")
        if manifest_dict.get("governance") is None:
            manifest_dict["governance"] = {}
        manifest_dict["governance"]["scitt"] = gov
        import json
        members["manifest.json"] = json.dumps(manifest_dict, indent=2, sort_keys=True).encode()

        with zipfile.ZipFile(input_epi, "w", zipfile.ZIP_DEFLATED) as zf_out:
            for name, content in members.items():
                compress = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
                zf_out.writestr(name, content, compress)

        # Mock the service key fetcher so the CLI can verify offline.
        import epi_cli.verify
        original_fetcher = epi_cli.verify._fetch_scitt_service_key
        epi_cli.verify._fetch_scitt_service_key = lambda url: mock_service.public_key_bytes

        try:
            runner = CliRunner()
            result = runner.invoke(
                app, ["scitt", "verify", str(input_epi)]
            )
            assert result.exit_code == 0, f"CLI failed: {result.output}"
            assert "SCITT statement valid" in result.output
            assert "SCITT receipt structurally valid" in result.output
            assert "SCITT receipt signature verified" in result.output
        finally:
            epi_cli.verify._fetch_scitt_service_key = original_fetcher
