"""
Lock the ManifestModel field set. Any addition or removal fails the test,
forcing an explicit compatibility decision.
"""

from epi_core.schemas import ManifestModel, PolicyModel

# The exact field set of epi-recorder 4.9.0's ManifestModel, read from the
# PyPI wheel. Anything outside this set must not appear at the manifest top
# level: 4.9.0 drops unknown fields before re-hashing and would report a
# genuine new file as SIGNATURE INVALID.
FROZEN_49_MANIFEST_FIELDS = {
    "analysis_error",
    "analysis_status",
    "approved_by",
    "cli_command",
    "container_format",
    "content_truncated",
    "corrected",
    "created_at",
    "env_snapshot_hash",
    "failed",
    "file_manifest",
    "goal",
    "governance",
    "metrics",
    "notes",
    "passed",
    "policy",
    "policy_load_status",
    "producer_version",
    "public_key",
    "signature",
    "source",
    "spec_version",
    "tags",
    "total_llm_calls",
    "total_steps",
    "total_validators",
    "trust",
    "viewer_version",
    "workflow_id",
}

FROZEN_MANIFEST_FIELDS = {
    "spec_version",
    "workflow_id",
    "created_at",
    "cli_command",
    "env_snapshot_hash",
    "file_manifest",
    "public_key",
    "signature",
    "container_format",
    "analysis_status",
    "analysis_error",
    "goal",
    "case_id",
    "notes",
    "metrics",
    "source",
    "total_steps",
    "total_validators",
    "total_llm_calls",
    "passed",
    "failed",
    "corrected",
    "trust",
    "approved_by",
    "tags",
    "governance",
    "viewer_version",
    "policy",
    "content_truncated",
    "policy_load_status",
    "producer_version",
    "seal_chain",
    "record_kind",
    "release",
    "release_ref",
    "runtime_components",
}


def test_manifest_model_fields_are_frozen():
    actual = set(ManifestModel.model_fields.keys())
    assert actual == FROZEN_MANIFEST_FIELDS, (
        f"ManifestModel fields changed.\n"
        f"Added: {actual - FROZEN_MANIFEST_FIELDS}\n"
        f"Removed: {FROZEN_MANIFEST_FIELDS - actual}"
    )


def test_policy_model_exists_for_manifest():
    """PolicyModel is referenced by ManifestModel.policy; ensure it is stable."""
    assert "policy_id" in PolicyModel.model_fields
    assert "version" in PolicyModel.model_fields
    assert "status" in PolicyModel.model_fields
    assert "rules" in PolicyModel.model_fields
    assert "violation_count" in PolicyModel.model_fields
    assert "remediation" in PolicyModel.model_fields


def test_every_post_49_field_is_member_backed():
    """New fields must be stored as members, not at the manifest top level.

    This is the regression guard for the 4.10.0 launch blocker: adding a
    top-level field silently breaks every older verifier.
    """
    from epi_core.manifest_members import MANIFEST_MEMBER_FIELDS

    added = set(ManifestModel.model_fields) - FROZEN_49_MANIFEST_FIELDS
    assert added == set(MANIFEST_MEMBER_FIELDS), (
        f"Manifest fields added after 4.9.0 changed.\n"
        f"Top-level additions: {added - set(MANIFEST_MEMBER_FIELDS)}\n"
        f"Member list: {set(MANIFEST_MEMBER_FIELDS) - added}"
    )


def test_manifest_storage_dict_is_a_49_subset():
    """The bytes written to manifest.json contain only 4.9.0-known fields."""
    from epi_core.manifest_members import (
        MANIFEST_MEMBER_FIELDS,
        manifest_storage_dict,
    )
    from epi_core.schemas import (
        ManifestModel,
        ReleaseModel,
        ReleaseRefModel,
        SealChainModel,
    )

    manifest = ManifestModel(
        goal="compat",
        case_id="CASE-1",
        record_kind="decision",
        seal_chain=SealChainModel(
            ledger_id="ledger-1",
            key_fingerprint="abcdef0123456789",
            seq=1,
            prev_seq=0,
            prev_content_digest="genesis",
        ),
        release_ref=ReleaseRefModel(release_id="rel-1", release_digest="d" * 64),
        runtime_components=[{"type": "policy", "name": "p"}],
        release=ReleaseModel(
            release_id="rel-1",
            name="demo",
            version="1.0",
            created_at="2026-01-01T00:00:00Z",
            components=[],
            release_digest="d" * 64,
        ),
    )
    stored = manifest_storage_dict(manifest)
    assert set(stored) <= FROZEN_49_MANIFEST_FIELDS
    assert not (set(stored) & set(MANIFEST_MEMBER_FIELDS))
