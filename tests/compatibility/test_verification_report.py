"""
Lock the verification report key sets (success and failure paths).
"""

import re
from pathlib import Path

from epi_core.schemas import ManifestModel
from epi_core.trust import (
    TrustRegistry,
    VerificationPolicy,
    apply_policy,
    create_verification_report,
)
from epi_cli.verify import _build_failure_report

FROZEN_REPORT_KEYS = {
    "facts",
    "identity",
    "metadata",
    "summary",
    "decision",
    "integrity_ok",
    "signature_valid",
    "identity_trusted",
    "has_signature",
    "trust_level",
    "mismatches_count",
    "signer",
    "files_checked",
    "workflow_id",
    "created_at",
    "spec_version",
    "trust_message",
}

FROZEN_FAILURE_KEYS = {
    "facts",
    "identity",
    "summary",
    "decision",
    "integrity_ok",
    "signature_valid",
    "trust_level",
    "has_signature",
    "mismatches_count",
    "signer",
    "files_checked",
    "workflow_id",
    "created_at",
    "spec_version",
    "error",
    "error_type",
}


def test_success_report_keys_are_frozen():
    manifest = ManifestModel()
    report = create_verification_report(
        integrity_ok=True,
        signature_valid=True,
        signer_name="test-key",
        mismatches={},
        manifest=manifest,
        trusted_registry=TrustRegistry(),
    )
    report = apply_policy(report, VerificationPolicy.STANDARD)
    actual = set(report.keys())
    assert actual == FROZEN_REPORT_KEYS, (
        f"Report keys changed.\n"
        f"Added: {actual - FROZEN_REPORT_KEYS}\n"
        f"Removed: {FROZEN_REPORT_KEYS - actual}"
    )


def test_failure_report_keys_are_frozen():
    failure = _build_failure_report("test error", error_type="test_error")
    actual = set(failure.keys())
    assert actual == FROZEN_FAILURE_KEYS, (
        f"Failure report keys changed.\n"
        f"Added: {actual - FROZEN_FAILURE_KEYS}\n"
        f"Removed: {FROZEN_FAILURE_KEYS - actual}"
    )


def test_report_nested_facts_keys():
    manifest = ManifestModel()
    report = create_verification_report(
        integrity_ok=True,
        signature_valid=True,
        signer_name="test-key",
        mismatches={},
        manifest=manifest,
        trusted_registry=TrustRegistry(),
    )
    facts_keys = set(report["facts"].keys())
    expected_facts = {
        "integrity_ok",
        "signature_valid",
        "sequence_ok",
        "completeness_ok",
        "has_signature",
        "mismatches",
    }
    assert facts_keys == expected_facts, (
        f"facts keys changed: {facts_keys ^ expected_facts}"
    )


def test_report_nested_identity_keys():
    manifest = ManifestModel()
    report = create_verification_report(
        integrity_ok=True,
        signature_valid=True,
        signer_name="test-key",
        mismatches={},
        manifest=manifest,
        trusted_registry=TrustRegistry(),
    )
    identity_keys = set(report["identity"].keys())
    expected_identity = {
        "status",
        "name",
        "detail",
        "registry_verified",
        "public_key_id",
    }
    assert identity_keys == expected_identity, (
        f"identity keys changed: {identity_keys ^ expected_identity}"
    )


def test_report_trust_levels_are_frozen():
    """Ensure trust_level values are one of the known set."""
    manifest = ManifestModel()
    registry = TrustRegistry()

    # LOW: valid signature but unknown identity (key substitution scenario)
    report = create_verification_report(
        integrity_ok=True, signature_valid=True, signer_name="k",
        mismatches={}, manifest=manifest, trusted_registry=registry,
    )
    assert report["trust_level"] == "LOW"

    # MEDIUM (unsigned but intact)
    report = create_verification_report(
        integrity_ok=True, signature_valid=None, signer_name=None,
        mismatches={}, manifest=manifest, trusted_registry=registry,
    )
    assert report["trust_level"] == "MEDIUM"

    # NONE (integrity compromised)
    report = create_verification_report(
        integrity_ok=False, signature_valid=False, signer_name="k",
        mismatches={}, manifest=manifest, trusted_registry=registry,
    )
    assert report["trust_level"] == "NONE"

    # HIGH: valid signature AND known trusted identity
    trusted_manifest = ManifestModel(
        public_key="aabbccdd11223344556677889900aabbccdd11223344556677889900aabbccdd"
    )
    report = create_verification_report(
        integrity_ok=True, signature_valid=True, signer_name="epi",
        mismatches={}, manifest=trusted_manifest, trusted_registry=registry,
    )
    assert report["trust_level"] == "LOW"  # No registry entry = LOW even with valid sig

    # Now with a registry entry for that key → HIGH
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        trusted_dir = os.path.join(td, "trusted_keys")
        os.makedirs(trusted_dir)
        with open(os.path.join(trusted_dir, "myorg.pub"), "w") as f:
            f.write(trusted_manifest.public_key)
        reg_with_key = TrustRegistry(trusted_keys_dir=Path(trusted_dir))
        report = create_verification_report(
            integrity_ok=True, signature_valid=True, signer_name="epi",
            mismatches={}, manifest=trusted_manifest, trusted_registry=reg_with_key,
        )
        assert report["trust_level"] == "HIGH"


def test_apply_policy_produces_decision_keys():
    manifest = ManifestModel()
    report = create_verification_report(
        integrity_ok=True, signature_valid=True, signer_name="k",
        mismatches={}, manifest=manifest, trusted_registry=TrustRegistry(),
    )
    report = apply_policy(report, VerificationPolicy.STANDARD)
    decision_keys = set(report["decision"].keys())
    assert decision_keys == {"policy", "status", "reason"}
