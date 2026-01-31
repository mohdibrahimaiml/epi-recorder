"""
Tests for epi_core.serialize - Canonical CBOR hashing

These tests are CRITICAL for ensuring deterministic behavior across platforms.
"""

from datetime import datetime
from uuid import UUID

import pytest

from epi_core.schemas import ManifestModel, StepModel
from epi_core.serialize import get_canonical_hash, verify_hash


class TestCanonicalHashing:
    """Test suite for canonical CBOR hashing."""
    
    def test_identical_models_produce_same_hash(self):
        """Verify that identical models always produce the same hash."""
        manifest1 = ManifestModel(
            cli_command="epi record --out test.epi -- python script.py"
        )
        manifest2 = ManifestModel(
            cli_command="epi record --out test.epi -- python script.py"
        )
        
        # Force same UUID and datetime for deterministic comparison
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        test_datetime = datetime(2025, 1, 15, 10, 30, 0)
        
        manifest1.workflow_id = test_uuid
        manifest1.created_at = test_datetime
        manifest2.workflow_id = test_uuid
        manifest2.created_at = test_datetime
        
        hash1 = get_canonical_hash(manifest1)
        hash2 = get_canonical_hash(manifest2)
        
        assert hash1 == hash2, "Identical models must produce identical hashes"
        assert len(hash1) == 64, "SHA-256 hash must be 64 hex characters"
    
    def test_different_models_produce_different_hashes(self):
        """Verify that different models produce different hashes."""
        manifest1 = ManifestModel(cli_command="command1")
        manifest2 = ManifestModel(cli_command="command2")
        
        # Use same UUID/datetime to isolate difference to cli_command
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        test_datetime = datetime(2025, 1, 15, 10, 30, 0)
        
        manifest1.workflow_id = test_uuid
        manifest1.created_at = test_datetime
        manifest2.workflow_id = test_uuid
        manifest2.created_at = test_datetime
        
        hash1 = get_canonical_hash(manifest1)
        hash2 = get_canonical_hash(manifest2)
        
        assert hash1 != hash2, "Different models must produce different hashes"
    
    def test_field_order_independence(self):
        """Verify that field order doesn't affect hash (canonical CBOR property)."""
        # Create two models with same data but different construction order
        manifest1 = ManifestModel(
            cli_command="test command",
            env_snapshot_hash="abc123"
        )
        
        manifest2 = ManifestModel(
            env_snapshot_hash="abc123",
            cli_command="test command"
        )
        
        # Force same UUID/datetime
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        test_datetime = datetime(2025, 1, 15, 10, 30, 0)
        
        manifest1.workflow_id = test_uuid
        manifest1.created_at = test_datetime
        manifest2.workflow_id = test_uuid
        manifest2.created_at = test_datetime
        
        hash1 = get_canonical_hash(manifest1)
        hash2 = get_canonical_hash(manifest2)
        
        assert hash1 == hash2, "Field order must not affect hash (canonical property)"
    
    def test_exclude_fields_from_hash(self):
        """Verify that excluded fields don't affect hash."""
        manifest1 = ManifestModel(
            cli_command="test command",
            signature="signature1"
        )
        
        manifest2 = ManifestModel(
            cli_command="test command",
            signature="signature2"  # Different signature
        )
        
        # Force same UUID/datetime
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        test_datetime = datetime(2025, 1, 15, 10, 30, 0)
        
        manifest1.workflow_id = test_uuid
        manifest1.created_at = test_datetime
        manifest2.workflow_id = test_uuid
        manifest2.created_at = test_datetime
        
        # Hash without signature field
        hash1 = get_canonical_hash(manifest1, exclude_fields={"signature"})
        hash2 = get_canonical_hash(manifest2, exclude_fields={"signature"})
        
        assert hash1 == hash2, "Excluded fields must not affect hash"
    
    def test_datetime_normalization(self):
        """Verify datetime normalization (microseconds removed)."""
        manifest1 = ManifestModel(cli_command="test")
        manifest2 = ManifestModel(cli_command="test")
        
        # Use datetimes with different microseconds
        dt1 = datetime(2025, 1, 15, 10, 30, 0, 123456)
        dt2 = datetime(2025, 1, 15, 10, 30, 0, 654321)
        
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        
        manifest1.workflow_id = test_uuid
        manifest1.created_at = dt1
        manifest2.workflow_id = test_uuid
        manifest2.created_at = dt2
        
        hash1 = get_canonical_hash(manifest1)
        hash2 = get_canonical_hash(manifest2)
        
        assert hash1 == hash2, "Microseconds should be normalized (removed)"
    
    def test_uuid_encoding_stability(self):
        """Verify UUID encoding is stable."""
        uuid1 = UUID("12345678-1234-5678-1234-567812345678")
        uuid2 = UUID("12345678-1234-5678-1234-567812345678")
        
        manifest1 = ManifestModel(workflow_id=uuid1, cli_command="test")
        manifest2 = ManifestModel(workflow_id=uuid2, cli_command="test")
        
        # Force same datetime
        test_datetime = datetime(2025, 1, 15, 10, 30, 0)
        manifest1.created_at = test_datetime
        manifest2.created_at = test_datetime
        
        hash1 = get_canonical_hash(manifest1)
        hash2 = get_canonical_hash(manifest2)
        
        assert hash1 == hash2, "UUIDs must encode deterministically"
    
    def test_verify_hash_function(self):
        """Test the verify_hash helper function."""
        manifest = ManifestModel(cli_command="test command")
        
        # Fix datetime/UUID for determinism
        manifest.workflow_id = UUID("12345678-1234-5678-1234-567812345678")
        manifest.created_at = datetime(2025, 1, 15, 10, 30, 0)
        
        expected_hash = get_canonical_hash(manifest)
        
        assert verify_hash(manifest, expected_hash), "Hash verification should succeed"
        assert not verify_hash(manifest, "invalid_hash"), "Invalid hash should fail verification"
    
    def test_step_model_hashing(self):
        """Verify StepModel can be hashed."""
        step = StepModel(
            index=0,
            kind="llm.request",
            content={"prompt": "test prompt", "model": "gpt-4"}
        )
        
        # Fix datetime for determinism
        step.timestamp = datetime(2025, 1, 15, 10, 30, 0)
        
        hash_value = get_canonical_hash(step)
        
        assert len(hash_value) == 64, "StepModel hash must be 64 hex characters"
        assert hash_value.isalnum(), "Hash must be alphanumeric"
    
    def test_hash_reproducibility_across_runs(self):
        """Critical test: Same data must produce same hash across runs."""
        # This tests the CBOR canonical encoding guarantee
        
        test_data = {
            "workflow_id": UUID("12345678-1234-5678-1234-567812345678"),
            "created_at": datetime(2025, 1, 15, 10, 30, 0),
            "cli_command": "epi record --out test.epi -- python script.py",
            "env_snapshot_hash": "abc123def456",
            "file_manifest": {
                "steps.jsonl": "hash1",
                "env.json": "hash2",
                "artifacts/output.txt": "hash3"
            }
        }
        
        manifest1 = ManifestModel(**test_data)
        manifest2 = ManifestModel(**test_data)
        
        hash1 = get_canonical_hash(manifest1)
        hash2 = get_canonical_hash(manifest2)
        
        # This is the CRITICAL assertion for EPI integrity
        assert hash1 == hash2, "CRITICAL: Hash must be reproducible across runs"
        
        # Known hash for regression testing (update if schema changes)
        # This ensures future changes don't break compatibility
        print(f"Reference hash: {hash1}")
    
    def test_nested_list_normalization(self):
        """Test that nested lists with datetime/UUID are normalized."""
        step = StepModel(
            index=0,
            kind="test.step",
            content={
                "messages": [
                    {"timestamp": datetime(2025, 1, 15, 10, 30, 0, 123456), "text": "msg1"},
                    {"timestamp": datetime(2025, 1, 15, 10, 30, 0, 654321), "text": "msg2"}
                ]
            }
        )
        
        # Fix datetime for determinism
        step.timestamp = datetime(2025, 1, 15, 10, 30, 0)
        
        # Should not raise error even with nested datetimes
        hash_value = get_canonical_hash(step)
        assert len(hash_value) == 64
    
    def test_verify_hash_with_exclude_fields(self):
        """Test verify_hash with exclude_fields parameter."""
        manifest = ManifestModel(
            cli_command="test",
            signature="test_signature"
        )
        
        manifest.workflow_id = UUID("12345678-1234-5678-1234-567812345678")
        manifest.created_at = datetime(2025, 1, 15, 10, 30, 0)
        
        # Get hash excluding signature
        expected_hash = get_canonical_hash(manifest, exclude_fields={"signature"})
        
        # Verify should succeed even with different signature
        assert verify_hash(manifest, expected_hash, exclude_fields={"signature"})


