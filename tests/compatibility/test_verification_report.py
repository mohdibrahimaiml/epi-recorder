"""
Lock the verification report key sets (success and failure paths).
"""

from pathlib import Path

from epi_cli.verify import _build_failure_report
from epi_core.schemas import ManifestModel
from epi_core.trust import (
    TrustRegistry,
    VerificationPolicy,
    apply_policy,
    create_verification_report,
)

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
    "steps_count",
    # Added for the capture manifest + forward-secure checkpoints features:
    # verify_command attaches the embedded scope declaration, the
    # enforcement-downgrade flag, and checkpoint reconciliation results to
    # every success report. Additive only — no existing key was renamed
    # or removed.
    "capture_manifest",
    "capture_manifest_present",
    "enforcement_downgraded",
    "enforcement_downgrade_count",
    "checkpoints",
    # Added for capture-time checkpoints on gateway exports: verify_command
    # attaches raw-event chain reconciliation to every success report.
    # Additive only.
    "capture_checkpoints",
    # Added for the customer witness: verify_command attaches the
    # --witness-log comparison to every success report. Additive only.
    "witness",
    # Added for offline RFC 3161 validation: verify_command attaches the
    # timestamps block to every success report. Additive only.
    "timestamps",
    # Added for human-signed approvals (step 3a): verify_command attaches the
    # human_approval classification to every success report. Defaults to None in
    # the factory (never evaluated by direct consumers). Additive only.
    "human_approval",
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

FROZEN_FACTS_KEYS = {
    "integrity_ok",
    "signature_valid",
    "sequence_ok",
    "completeness_ok",
    "chain_ok",
    # Added by the red-team fix for F-13: False means the steps carry no
    # prev_hash links at all, so the chain check passed *vacuously* and the
    # recorded order is not provable. Distinct from chain_ok=False (broken).
    "chain_present",
    "has_signature",
    "mismatches",
    "transparency_ok",
    "completeness_gaps",
    "forensic_reason",
    "content_truncated",
    "content_complete_asserted",
    # Added for offline RFC 3161 validation (defaults False in factory-only
    # reports; verify_command overwrites with the validated result).
    "timestamp_verified",
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
    assert facts_keys == FROZEN_FACTS_KEYS, (
        f"facts keys changed: {facts_keys ^ FROZEN_FACTS_KEYS}"
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
        # Added by the red-team fix for F-19: says WHERE the trust came from.
        # "local_pin" is a pin the verifier chose; "did_web" means the signer
        # published their own key at their own domain (self-asserted).
        "pin_source",
        "public_key_id",
        "public_key_fingerprint",
        "fingerprint",
        "local_key_name",
        "did",
        "pinned_names",
        "scitt",
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

    # LOW (unsigned but intact) — since 4.4.6 unsigned ranks LOW, never
    # above a valid signature with unknown identity (trust.py)
    report = create_verification_report(
        integrity_ok=True, signature_valid=None, signer_name=None,
        mismatches={}, manifest=manifest, trusted_registry=registry,
    )
    assert report["trust_level"] == "LOW"

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
    import os
    import tempfile
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
