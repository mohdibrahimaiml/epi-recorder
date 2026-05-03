"""
Full-system E2E test — proves the entire EPI contract works as one unit.

Creates artifacts, verifies them, tampers with them, and asserts that
all compatibility guarantees still hold.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.trust import verify_embedded_manifest_signature
from epi_recorder.api import EpiRecorderSession
from tests.helpers.artifacts import make_decision_epi, read_legacy_member_json, rewrite_legacy_member

# Import frozen compatibility contracts so this test breaks if they drift
from tests.compatibility.test_manifest_schema import FROZEN_MANIFEST_FIELDS
from tests.compatibility.test_verification_report import FROZEN_REPORT_KEYS

pytestmark = pytest.mark.e2e
runner = CliRunner()


@pytest.fixture
def fresh_env(monkeypatch, tmp_path: Path):
    """Simulate a machine with no EPI installation, keys, or trust registry."""
    fresh_home = tmp_path / "fresh_epi_home"
    fresh_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPI_HOME", str(fresh_home))
    monkeypatch.setenv("EPI_KEYS_DIR", str(fresh_home / "keys"))
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(fresh_home / "trusted_keys"))
    return fresh_home


class TestFreshEnvironmentVerification:
    """Tier 1: Signed artifacts verify cryptographically with zero external state."""

    def test_legacy_artifact_verifies_offline(self, fresh_env, tmp_path: Path):
        artifact, _ = make_decision_epi(tmp_path, signed=True, container_format="legacy-zip")
        result = runner.invoke(cli_app, ["verify", "--json", str(artifact)])

        assert result.exit_code == 0, f"CLI exited {result.exit_code}: {result.output}"
        report = json.loads(result.stdout)

        assert set(report.keys()) == FROZEN_REPORT_KEYS
        assert report["facts"]["integrity_ok"] is True
        assert report["facts"]["signature_valid"] is True
        assert report["identity"]["status"] == "UNKNOWN"
        assert report["decision"]["status"] == "PASS"

        manifest = EPIContainer.read_manifest(artifact)
        assert set(ManifestModel.model_fields.keys()) == FROZEN_MANIFEST_FIELDS
        assert verify_embedded_manifest_signature(manifest)[0] is True

    def test_envelope_artifact_verifies_offline(self, fresh_env, tmp_path: Path):
        artifact, _ = make_decision_epi(tmp_path, signed=True, container_format="envelope-v2")
        result = runner.invoke(cli_app, ["verify", "--json", str(artifact)])

        assert result.exit_code == 0, f"CLI exited {result.exit_code}: {result.output}"
        report = json.loads(result.stdout)

        assert report["facts"]["integrity_ok"] is True
        assert report["facts"]["signature_valid"] is True
        assert report["identity"]["status"] == "UNKNOWN"

        manifest = EPIContainer.read_manifest(artifact)
        assert verify_embedded_manifest_signature(manifest)[0] is True


class TestArtifactLifecycleTamperResistance:
    """Any modification to a signed artifact must be detected."""

    def test_payload_tamper_fails_integrity(self, tmp_path: Path):
        artifact, _ = make_decision_epi(tmp_path, signed=True)
        rewrite_legacy_member(artifact, "steps.jsonl", b'{"tampered":true}\n')

        result = runner.invoke(cli_app, ["verify", "--json", str(artifact)])
        assert result.exit_code == 1

        report = json.loads(result.stdout)
        assert report["facts"]["integrity_ok"] is False
        assert "steps.jsonl" in str(report)

    def test_manifest_tamper_fails_signature(self, tmp_path: Path):
        artifact, _ = make_decision_epi(tmp_path, signed=True)
        manifest = read_legacy_member_json(artifact, "manifest.json")
        manifest["goal"] = "Tampered goal"
        rewrite_legacy_member(
            artifact, "manifest.json", json.dumps(manifest, indent=2).encode("utf-8")
        )

        result = runner.invoke(cli_app, ["verify", "--json", str(artifact)])
        assert result.exit_code == 1

        report = json.loads(result.stdout)
        # Changing manifest.json alters both file hash and signed hash;
        # at minimum the signature must be invalid.
        assert (
            report["facts"]["signature_valid"] is False
            or report["facts"]["integrity_ok"] is False
        )

    def test_signature_replay_between_artifacts_fails(self, tmp_path: Path):
        key = Ed25519PrivateKey.generate()
        first, _ = make_decision_epi(tmp_path, name="first.epi", signed=True, private_key=key)
        second, _ = make_decision_epi(
            tmp_path,
            name="second.epi",
            signed=True,
            private_key=key,
            prompt="A different prompt changes the manifest hash",
        )

        first_manifest = read_legacy_member_json(first, "manifest.json")
        second_manifest = read_legacy_member_json(second, "manifest.json")
        second_manifest["signature"] = first_manifest["signature"]
        rewrite_legacy_member(
            second,
            "manifest.json",
            json.dumps(second_manifest, indent=2).encode("utf-8"),
        )

        valid, _, message = verify_embedded_manifest_signature(EPIContainer.read_manifest(second))
        assert valid is False
        assert "invalid" in message.lower() or "tamper" in message.lower()

    def test_removed_public_key_cannot_verify(self, tmp_path: Path):
        artifact, _ = make_decision_epi(tmp_path, signed=True)
        manifest = read_legacy_member_json(artifact, "manifest.json")
        manifest["public_key"] = None
        rewrite_legacy_member(
            artifact,
            "manifest.json",
            json.dumps(manifest, indent=2).encode("utf-8"),
        )

        valid, _, _ = verify_embedded_manifest_signature(EPIContainer.read_manifest(artifact))
        assert valid is False


class TestDidWebOptionalContract:
    """DID:WEB must remain additive and must not break offline verification."""

    def test_did_web_identity_binding_and_resolution(self, monkeypatch, tmp_path: Path):
        epi_home = tmp_path / "epi_home"
        epi_home.mkdir()
        monkeypatch.setenv("EPI_HOME", str(epi_home))
        monkeypatch.setenv("EPI_KEYS_DIR", str(epi_home / "keys"))
        monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(epi_home / "trusted_keys"))

        artifact_path = tmp_path / "did_web_artifact.epi"
        with EpiRecorderSession(
            output_path=artifact_path,
            workflow_name="did-web-e2e",
            did_web="did:web:example.com",
            auto_sign=True,
        ) as epi:
            epi.log_step("test.step", {"message": "hello"})

        manifest = EPIContainer.read_manifest(artifact_path)
        assert manifest.governance is not None
        assert manifest.governance.get("did") == "did:web:example.com"
        assert manifest.trust is not None
        assert "fingerprint" in manifest.trust

        # Mock DID resolution with the matching key
        did_doc = {
            "id": "did:web:example.com",
            "verificationMethod": [
                {
                    "id": "#key-1",
                    "type": "Ed25519VerificationKey2020",
                    "publicKeyHex": manifest.public_key,
                }
            ],
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = did_doc

        with patch("epi_core.did_web.requests.get", return_value=mock_resp):
            result = runner.invoke(cli_app, ["verify", "--json", str(artifact_path)])

        assert result.exit_code == 0, f"CLI exited {result.exit_code}: {result.output}"
        report = json.loads(result.stdout)
        assert report["facts"]["signature_valid"] is True
        assert report["facts"]["integrity_ok"] is True
        assert report["identity"]["status"] == "KNOWN"
        assert "DID:WEB" in report["identity"]["detail"]

    def test_did_web_resolution_failure_gracefully_downgrades(self, monkeypatch, tmp_path: Path):
        epi_home = tmp_path / "epi_home"
        epi_home.mkdir()
        monkeypatch.setenv("EPI_HOME", str(epi_home))
        monkeypatch.setenv("EPI_KEYS_DIR", str(epi_home / "keys"))
        monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(epi_home / "trusted_keys"))

        artifact_path = tmp_path / "did_web_offline.epi"
        with EpiRecorderSession(
            output_path=artifact_path,
            workflow_name="did-web-offline",
            did_web="did:web:unreachable.example",
            auto_sign=True,
        ) as epi:
            epi.log_step("test.step", {"message": "hello"})

        with patch("epi_core.did_web.requests.get", side_effect=ConnectionError("unreachable")):
            result = runner.invoke(cli_app, ["verify", "--json", str(artifact_path)])

        assert result.exit_code == 0, f"CLI exited {result.exit_code}: {result.output}"
        report = json.loads(result.stdout)
        assert report["facts"]["signature_valid"] is True
        assert report["facts"]["integrity_ok"] is True
        assert report["identity"]["status"] == "UNKNOWN"
        assert "DID resolution failed" in report["identity"]["detail"]
        assert report["decision"]["status"] == "PASS"


class TestGoldenArtifactsStillVerify:
    """Committed golden artifacts must continue to parse, verify, and integrate."""

    def test_legacy_golden_artifact_verifies(self):
        path = Path(__file__).with_suffix("").parent.parent / "compatibility" / "golden" / "golden_legacy.epi"
        if not path.exists():
            pytest.skip("Golden legacy artifact not found")

        manifest = EPIContainer.read_manifest(path)
        assert set(ManifestModel.model_fields.keys()) == FROZEN_MANIFEST_FIELDS
        assert verify_embedded_manifest_signature(manifest)[0] is True

        ok, mismatches = EPIContainer.verify_integrity(path)
        assert ok is True, f"Integrity mismatch: {mismatches}"

    def test_envelope_golden_artifact_verifies(self):
        path = Path(__file__).with_suffix("").parent.parent / "compatibility" / "golden" / "golden_envelope.epi"
        if not path.exists():
            pytest.skip("Golden envelope artifact not found")

        manifest = EPIContainer.read_manifest(path)
        assert set(ManifestModel.model_fields.keys()) == FROZEN_MANIFEST_FIELDS
        assert verify_embedded_manifest_signature(manifest)[0] is True

        ok, mismatches = EPIContainer.verify_integrity(path)
        assert ok is True, f"Integrity mismatch: {mismatches}"


class TestReportStructureStability:
    """The verification report shape must not drift."""

    def test_success_report_keys_match_frozen_set(self, fresh_env, tmp_path: Path):
        artifact, _ = make_decision_epi(tmp_path, signed=True)
        result = runner.invoke(cli_app, ["verify", "--json", str(artifact)])

        assert result.exit_code == 0
        report = json.loads(result.stdout)

        assert set(report.keys()) == FROZEN_REPORT_KEYS
        assert set(report["facts"].keys()) == {
            "integrity_ok",
            "signature_valid",
            "sequence_ok",
            "completeness_ok",
            "has_signature",
            "mismatches",
        }
        assert set(report["identity"].keys()) == {
            "status",
            "name",
            "detail",
            "registry_verified",
            "public_key_id",
            "did",
        }
        assert set(report["metadata"].keys()) == {
            "spec_version",
            "workflow_id",
            "created_at",
            "files_checked",
        }
        assert set(report["summary"].keys()) == {"integrity", "trust"}
        assert set(report["decision"].keys()) == {"policy", "status", "reason"}
        assert report["trust_level"] in {"HIGH", "MEDIUM", "LOW", "NONE", "INVALID"}
