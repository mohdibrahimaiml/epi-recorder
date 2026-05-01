"""
Golden-file compatibility tests.

These tests verify that previously-generated .epi artifacts still parse,
verify cryptographically, and conform to the frozen contract.

If a code change breaks these tests, the change has broken backward
compatibility with existing artifacts in the wild.

To regenerate golden artifacts after an intentional contract change:
    python tests/compatibility/_generate_golden.py
"""

import re
from pathlib import Path

import pytest

from epi_core.container import EPIContainer, EPI_ENVELOPE_MAGIC
from epi_core.schemas import ManifestModel
from epi_core.trust import verify_embedded_manifest_signature

GOLDEN_DIR = Path(__file__).with_suffix("").parent / "golden"
SIG_REGEX = re.compile(r"^ed25519:[^:]+:[a-f0-9]{128}$")


def _load_manifest(epi_path: Path) -> ManifestModel:
    return EPIContainer.read_manifest(epi_path)


class TestGoldenLegacy:
    @pytest.fixture(scope="class")
    def manifest(self):
        path = GOLDEN_DIR / "golden_legacy.epi"
        if not path.exists():
            pytest.skip("Golden legacy artifact not found — run _generate_golden.py")
        return _load_manifest(path)

    def test_artifact_exists(self, manifest):
        assert manifest is not None

    def test_spec_version_is_current(self, manifest):
        assert manifest.spec_version == "4.0.1"

    def test_manifest_fields_match_frozen_set(self, manifest):
        from tests.compatibility.test_manifest_schema import FROZEN_MANIFEST_FIELDS
        actual = set(manifest.model_dump().keys())
        # model_dump may omit None values; check against model_fields instead
        actual = set(ManifestModel.model_fields.keys())
        assert actual == FROZEN_MANIFEST_FIELDS

    def test_signature_format_valid(self, manifest):
        assert SIG_REGEX.match(manifest.signature)

    def test_public_key_is_64_hex(self, manifest):
        assert len(manifest.public_key) == 64
        int(manifest.public_key, 16)

    def test_embedded_signature_verifies(self, manifest):
        valid, signer, message = verify_embedded_manifest_signature(manifest)
        assert valid is True, f"Golden artifact signature failed: {message}"
        assert signer == "golden"

    def test_container_format_is_legacy(self, manifest):
        assert manifest.container_format == "legacy-zip"

    def test_file_manifest_present(self, manifest):
        assert "steps.jsonl" in manifest.file_manifest
        assert "environment.json" in manifest.file_manifest

    def test_integrity_check_passes(self):
        path = GOLDEN_DIR / "golden_legacy.epi"
        if not path.exists():
            pytest.skip("Golden legacy artifact not found")
        ok, mismatches = EPIContainer.verify_integrity(path)
        assert ok is True, f"Integrity mismatch: {mismatches}"


class TestGoldenEnvelope:
    @pytest.fixture(scope="class")
    def manifest(self):
        path = GOLDEN_DIR / "golden_envelope.epi"
        if not path.exists():
            pytest.skip("Golden envelope artifact not found — run _generate_golden.py")
        return _load_manifest(path)

    def test_artifact_exists(self, manifest):
        assert manifest is not None

    def test_spec_version_is_current(self, manifest):
        assert manifest.spec_version == "4.0.1"

    def test_manifest_fields_match_frozen_set(self, manifest):
        from tests.compatibility.test_manifest_schema import FROZEN_MANIFEST_FIELDS
        actual = set(ManifestModel.model_fields.keys())
        assert actual == FROZEN_MANIFEST_FIELDS

    def test_signature_format_valid(self, manifest):
        assert SIG_REGEX.match(manifest.signature)

    def test_public_key_is_64_hex(self, manifest):
        assert len(manifest.public_key) == 64
        int(manifest.public_key, 16)

    def test_embedded_signature_verifies(self, manifest):
        valid, signer, message = verify_embedded_manifest_signature(manifest)
        assert valid is True, f"Golden artifact signature failed: {message}"
        assert signer == "golden"

    def test_container_format_is_envelope(self, manifest):
        assert manifest.container_format == "envelope-v2"

    def test_file_starts_with_magic_bytes(self):
        path = GOLDEN_DIR / "golden_envelope.epi"
        if not path.exists():
            pytest.skip("Golden envelope artifact not found")
        first_bytes = path.read_bytes()[:4]
        assert first_bytes == EPI_ENVELOPE_MAGIC

    def test_integrity_check_passes(self):
        path = GOLDEN_DIR / "golden_envelope.epi"
        if not path.exists():
            pytest.skip("Golden envelope artifact not found")
        ok, mismatches = EPIContainer.verify_integrity(path)
        assert ok is True, f"Integrity mismatch: {mismatches}"
