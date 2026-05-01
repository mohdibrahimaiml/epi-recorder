"""
Lock the ManifestModel field set. Any addition or removal fails the test,
forcing an explicit compatibility decision.
"""

from epi_core.schemas import ManifestModel, PolicyModel

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
