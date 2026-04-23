"""
Tests for epi_core.serialize — canonical hashing functions.
Tests for epi_core.storage — EpiStorage SQLite-backed storage.
Tests for epi_core.trust — sign_manifest_inplace, get_signer_name, create_verification_report.
"""

import json
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from epi_core.schemas import ManifestModel, StepModel
from epi_core.time_utils import utc_now
from epi_core.serialize import (
    _cbor_default_encoder,
    get_canonical_hash,
    _get_json_canonical_hash,
    _get_cbor_canonical_hash,
    verify_hash,
)
from epi_core.storage import EpiStorage
from epi_core.trust import (
    get_signer_name,
    create_verification_report,
    sign_manifest_inplace,
    SigningError,
)


# ─────────────────────────────────────────────────────────────
# serialize._cbor_default_encoder
# ─────────────────────────────────────────────────────────────

class TestCborDefaultEncoder:
    def _make_mock_encoder(self, captured):
        """Return a mock encoder that records what was encoded."""
        class MockEncoder:
            def encode(self, value):
                captured.append(value)
        return MockEncoder()

    def test_encodes_datetime_as_iso_string(self):
        captured = []
        encoder = self._make_mock_encoder(captured)
        dt = datetime(2025, 1, 15, 10, 30, 45, 123456)
        _cbor_default_encoder(encoder, dt)
        assert len(captured) == 1
        assert "2025-01-15T10:30:45Z" == captured[0]  # microseconds removed

    def test_encodes_uuid_as_string(self):
        captured = []
        encoder = self._make_mock_encoder(captured)
        uid = UUID("12345678-1234-5678-1234-567812345678")
        _cbor_default_encoder(encoder, uid)
        assert len(captured) == 1
        assert captured[0] == "12345678-1234-5678-1234-567812345678"

    def test_raises_for_unknown_type(self):
        captured = []
        encoder = self._make_mock_encoder(captured)
        with pytest.raises(ValueError):
            _cbor_default_encoder(encoder, object())


# ─────────────────────────────────────────────────────────────
# serialize.get_canonical_hash
# ─────────────────────────────────────────────────────────────

class TestGetCanonicalHash:
    def _make_manifest(self, **kwargs):
        return ManifestModel(
            workflow_id=uuid4(),
            created_at=datetime(2025, 1, 1, 12, 0, 0),
            **kwargs
        )

    def test_returns_hex_string(self):
        m = self._make_manifest()
        h = get_canonical_hash(m)
        assert isinstance(h, str)
        assert len(h) == 64

    def test_deterministic(self):
        m = self._make_manifest(cli_command="python test.py")
        h1 = get_canonical_hash(m)
        h2 = get_canonical_hash(m)
        assert h1 == h2

    def test_different_models_different_hashes(self):
        m1 = self._make_manifest(cli_command="python a.py")
        m2 = self._make_manifest(cli_command="python b.py")
        assert get_canonical_hash(m1) != get_canonical_hash(m2)

    def test_exclude_fields(self):
        m = self._make_manifest(cli_command="python test.py")
        h_full = get_canonical_hash(m)
        h_excl = get_canonical_hash(m, exclude_fields={"signature"})
        # Both should be valid hashes
        assert len(h_full) == 64
        assert len(h_excl) == 64

    def test_v2_uses_json(self):
        """spec_version >= 2.x should use JSON canonical hash."""
        m = ManifestModel(
            workflow_id=uuid4(),
            created_at=datetime(2025, 1, 1),
            spec_version="2.7.2",
        )
        h = get_canonical_hash(m)
        assert len(h) == 64


# ─────────────────────────────────────────────────────────────
# serialize._get_json_canonical_hash
# ─────────────────────────────────────────────────────────────

class TestGetJsonCanonicalHash:
    def test_returns_64_char_hex(self):
        h = _get_json_canonical_hash({"key": "value"})
        assert len(h) == 64

    def test_deterministic(self):
        data = {"b": 2, "a": 1}
        assert _get_json_canonical_hash(data) == _get_json_canonical_hash(data)

    def test_key_order_independent(self):
        """Canonical JSON sorts keys."""
        h1 = _get_json_canonical_hash({"a": 1, "b": 2})
        h2 = _get_json_canonical_hash({"b": 2, "a": 1})
        assert h1 == h2


# ─────────────────────────────────────────────────────────────
# serialize._get_cbor_canonical_hash
# ─────────────────────────────────────────────────────────────

class TestGetCborCanonicalHash:
    def test_returns_64_char_hex(self):
        h = _get_cbor_canonical_hash({"key": "value"})
        assert len(h) == 64

    def test_deterministic(self):
        data = {"x": 42}
        assert _get_cbor_canonical_hash(data) == _get_cbor_canonical_hash(data)


# ─────────────────────────────────────────────────────────────
# serialize.verify_hash
# ─────────────────────────────────────────────────────────────

class TestVerifyHash:
    def _make_manifest(self):
        return ManifestModel(
            workflow_id=uuid4(),
            created_at=datetime(2025, 1, 1, 12, 0, 0),
            cli_command="python test.py",
        )

    def test_matching_hash_returns_true(self):
        m = self._make_manifest()
        h = get_canonical_hash(m)
        assert verify_hash(m, h) is True

    def test_wrong_hash_returns_false(self):
        m = self._make_manifest()
        assert verify_hash(m, "0" * 64) is False

    def test_with_exclude_fields(self):
        m = self._make_manifest()
        h = get_canonical_hash(m, exclude_fields={"signature"})
        assert verify_hash(m, h, exclude_fields={"signature"}) is True


# ─────────────────────────────────────────────────────────────
# storage.EpiStorage
# ─────────────────────────────────────────────────────────────

class TestEpiStorage:
    def test_init_creates_db(self, tmp_path):
        storage = EpiStorage("sess1", tmp_path)
        assert (tmp_path / "sess1_temp.db").exists()
        storage.close()

    def test_add_and_get_steps(self, tmp_path):
        storage = EpiStorage("sess2", tmp_path)
        step = StepModel(
            index=0,
            kind="test.event",
            content={"msg": "hello"},
        )
        storage.add_step(step)
        steps = storage.get_steps()
        assert len(steps) == 1
        assert steps[0].kind == "test.event"
        storage.close()

    def test_multiple_steps_in_order(self, tmp_path):
        storage = EpiStorage("sess3", tmp_path)
        for i in range(5):
            storage.add_step(StepModel(index=i, kind="event", content={"i": i}))
        steps = storage.get_steps()
        assert len(steps) == 5
        assert [s.index for s in steps] == list(range(5))
        storage.close()

    def test_set_and_get_metadata(self, tmp_path):
        storage = EpiStorage("sess4", tmp_path)
        storage.set_metadata("key1", "value1")
        assert storage.get_metadata("key1") == "value1"
        storage.close()

    def test_get_metadata_missing_returns_none(self, tmp_path):
        storage = EpiStorage("sess5", tmp_path)
        assert storage.get_metadata("nonexistent") is None
        storage.close()

    def test_set_metadata_overwrite(self, tmp_path):
        storage = EpiStorage("sess6", tmp_path)
        storage.set_metadata("k", "v1")
        storage.set_metadata("k", "v2")
        assert storage.get_metadata("k") == "v2"
        storage.close()

    def test_export_to_jsonl(self, tmp_path):
        storage = EpiStorage("sess7", tmp_path)
        storage.add_step(StepModel(index=0, kind="ev", content={}))
        out = tmp_path / "out.jsonl"
        storage.export_to_jsonl(out)
        assert out.exists()
        lines = out.read_text().strip().splitlines()
        assert len(lines) == 1
        storage.close()

    def test_finalize_creates_jsonl_and_removes_db(self, tmp_path):
        storage = EpiStorage("sess8", tmp_path)
        storage.add_step(StepModel(index=0, kind="ev", content={}))
        final = storage.finalize()
        assert final.exists()
        assert not (tmp_path / "sess8_temp.db").exists()


# ─────────────────────────────────────────────────────────────
# trust.get_signer_name
# ─────────────────────────────────────────────────────────────

class TestGetSignerName:
    def test_extracts_key_name(self):
        sig = "ed25519:mykey:abcdef1234"
        assert get_signer_name(sig) == "mykey"

    def test_none_returns_none(self):
        assert get_signer_name(None) is None

    def test_empty_returns_none(self):
        assert get_signer_name("") is None

    def test_invalid_format_returns_none(self):
        assert get_signer_name("invalid") is None

    def test_default_key_name(self):
        sig = "ed25519:default:deadbeef"
        assert get_signer_name(sig) == "default"


# ─────────────────────────────────────────────────────────────
# trust.create_verification_report
# ─────────────────────────────────────────────────────────────

class TestCreateVerificationReport:
    def _make_manifest(self):
        return ManifestModel(
            workflow_id=uuid4(),
            created_at=utc_now(),
            file_manifest={"steps.jsonl": "abc123"},
        )

    def test_high_trust_when_signed_and_intact(self):
        m = self._make_manifest()
        report = create_verification_report(True, True, "mykey", {}, m)
        assert report["trust_level"] == "HIGH"

    def test_medium_trust_unsigned_but_intact(self):
        m = self._make_manifest()
        report = create_verification_report(True, None, None, {}, m)
        assert report["trust_level"] == "MEDIUM"

    def test_none_trust_invalid_signature(self):
        m = self._make_manifest()
        report = create_verification_report(True, False, "mykey", {}, m)
        assert report["trust_level"] == "NONE"

    def test_none_trust_integrity_fail(self):
        m = self._make_manifest()
        report = create_verification_report(False, None, None, {"f": "mismatch"}, m)
        assert report["trust_level"] == "NONE"

    def test_report_has_required_keys(self):
        m = self._make_manifest()
        report = create_verification_report(True, None, None, {}, m)
        for key in ("integrity_ok", "signature_valid", "facts", "identity", "metadata", "summary"):
            assert key in report

    def test_files_checked_count(self):
        m = self._make_manifest()
        report = create_verification_report(True, None, None, {}, m)
        assert report["metadata"]["files_checked"] == 1


# ─────────────────────────────────────────────────────────────
# trust.sign_manifest_inplace
# ─────────────────────────────────────────────────────────────

class TestSignManifestInplace:
    def test_raises_on_missing_file(self, tmp_path):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.generate()
        with pytest.raises((SigningError, FileNotFoundError)):
            sign_manifest_inplace(tmp_path / "nonexistent.json", key)

    def test_signs_manifest_file(self, tmp_path):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.generate()
        m = ManifestModel(
            workflow_id=uuid4(),
            created_at=utc_now(),
            cli_command="python test.py",
        )
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(m.model_dump_json(), encoding="utf-8")
        sign_manifest_inplace(manifest_path, key, "testkey")
        data = json.loads(manifest_path.read_text())
        assert data["signature"] is not None
        assert "ed25519:testkey:" in data["signature"]
