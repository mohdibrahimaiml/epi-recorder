"""
Tests for epi_core.trust and epi_cli.keys - Trust layer verification.

Tests Ed25519 key generation, signing, and verification.
"""

import tempfile
from pathlib import Path
from datetime import datetime
from uuid import UUID

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.schemas import ManifestModel
from epi_core.trust import (
    sign_manifest,
    verify_signature,
    sign_manifest_inplace,
    get_signer_name,
    create_verification_report,
    SigningError
)
from epi_cli.keys import KeyManager


class TestKeyManagement:
    """Test Ed25519 key pair management."""
    
    @pytest.fixture
    def temp_keys_dir(self):
        """Create temporary keys directory."""
        with tempfile.TemporaryDirectory(prefix="epi_test_keys_") as tmpdir:
            yield Path(tmpdir)
    
    def test_generate_keypair_creates_files(self, temp_keys_dir):
        """Test that key generation creates both private and public keys."""
        key_manager = KeyManager(keys_dir=temp_keys_dir)
        
        private_path, public_path = key_manager.generate_keypair("test_key")
        
        assert private_path.exists(), "Private key should be created"
        assert public_path.exists(), "Public key should be created"
        assert private_path.name == "test_key.key"
        assert public_path.name == "test_key.pub"
    
    def test_generate_keypair_prevents_overwrite(self, temp_keys_dir):
        """Test that existing keys are not overwritten without flag."""
        key_manager = KeyManager(keys_dir=temp_keys_dir)
        
        # Generate first time
        key_manager.generate_keypair("test_key")
        
        # Try to generate again without overwrite flag
        with pytest.raises(FileExistsError):
            key_manager.generate_keypair("test_key", overwrite=False)
    
    def test_generate_keypair_allows_overwrite(self, temp_keys_dir):
        """Test that overwrite flag allows key replacement."""
        key_manager = KeyManager(keys_dir=temp_keys_dir)
        
        # Generate first time
        key_manager.generate_keypair("test_key")
        
        # Generate again with overwrite flag
        private_path, public_path = key_manager.generate_keypair("test_key", overwrite=True)
        
        assert private_path.exists()
        assert public_path.exists()
    
    def test_load_private_key(self, temp_keys_dir):
        """Test loading private key from disk."""
        key_manager = KeyManager(keys_dir=temp_keys_dir)
        key_manager.generate_keypair("test_key")
        
        private_key = key_manager.load_private_key("test_key")
        
        assert isinstance(private_key, Ed25519PrivateKey)
    
    def test_load_public_key(self, temp_keys_dir):
        """Test loading public key from disk."""
        key_manager = KeyManager(keys_dir=temp_keys_dir)
        key_manager.generate_keypair("test_key")
        
        public_key_bytes = key_manager.load_public_key("test_key")
        
        assert isinstance(public_key_bytes, bytes)
        assert len(public_key_bytes) == 32, "Ed25519 public key should be 32 bytes"
    
    def test_load_nonexistent_key_raises_error(self, temp_keys_dir):
        """Test that loading nonexistent key raises FileNotFoundError."""
        key_manager = KeyManager(keys_dir=temp_keys_dir)
        
        with pytest.raises(FileNotFoundError):
            key_manager.load_private_key("nonexistent")
        
        with pytest.raises(FileNotFoundError):
            key_manager.load_public_key("nonexistent")
    
    def test_list_keys(self, temp_keys_dir):
        """Test listing available keys."""
        key_manager = KeyManager(keys_dir=temp_keys_dir)
        
        # Generate multiple keys
        key_manager.generate_keypair("key1")
        key_manager.generate_keypair("key2")
        
        keys_list = key_manager.list_keys()
        
        assert len(keys_list) == 2
        key_names = [k["name"] for k in keys_list]
        assert "key1" in key_names
        assert "key2" in key_names
    
    def test_export_public_key(self, temp_keys_dir):
        """Test exporting public key as base64."""
        key_manager = KeyManager(keys_dir=temp_keys_dir)
        key_manager.generate_keypair("test_key")
        
        public_key_b64 = key_manager.export_public_key("test_key")
        
        assert isinstance(public_key_b64, str)
        assert len(public_key_b64) > 0
        # Base64 of 32 bytes should be 44 characters (with padding)
        assert len(public_key_b64) == 44
    
    def test_has_default_key(self, temp_keys_dir):
        """Test checking for default key existence."""
        key_manager = KeyManager(keys_dir=temp_keys_dir)
        
        assert not key_manager.has_default_key()
        
        key_manager.generate_keypair("default")
        
        assert key_manager.has_default_key()


class TestSigning:
    """Test Ed25519 signing operations."""
    
    @pytest.fixture
    def test_manifest(self):
        """Create test manifest."""
        return ManifestModel(
            workflow_id=UUID("12345678-1234-5678-1234-567812345678"),
            created_at=datetime(2025, 1, 15, 10, 30, 0),
            cli_command="epi record --out test.epi -- python script.py",
            file_manifest={
                "steps.jsonl": "abc123",
                "env.json": "def456"
            }
        )
    
    @pytest.fixture
    def test_keypair(self):
        """Generate test Ed25519 keypair."""
        from cryptography.hazmat.primitives import serialization
        
        private_key = Ed25519PrivateKey.generate()
        public_key_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return private_key, public_key_bytes
    
    def test_sign_manifest(self, test_manifest, test_keypair):
        """Test signing a manifest."""
        from cryptography.hazmat.primitives import serialization
        
        private_key, _ = test_keypair
        
        signed_manifest = sign_manifest(test_manifest, private_key, "test_key")
        
        assert signed_manifest.signature is not None
        assert signed_manifest.signature.startswith("ed25519:test_key:")
        assert signed_manifest.workflow_id == test_manifest.workflow_id
    
    def test_verify_signature_valid(self, test_manifest, test_keypair):
        """Test verifying a valid signature."""
        from cryptography.hazmat.primitives import serialization
        
        private_key, public_key_bytes = test_keypair
        
        # Sign manifest
        signed_manifest = sign_manifest(test_manifest, private_key, "test_key")
        
        # Verify signature
        is_valid, message = verify_signature(signed_manifest, public_key_bytes)
        
        assert is_valid, "Signature should be valid"
        assert "valid" in message.lower()
    
    def test_verify_signature_invalid(self, test_manifest, test_keypair):
        """Test detecting invalid signature."""
        from cryptography.hazmat.primitives import serialization
        
        private_key, _ = test_keypair
        
        # Sign with first key
        signed_manifest = sign_manifest(test_manifest, private_key, "test_key")
        
        # Try to verify with different key
        different_key = Ed25519PrivateKey.generate()
        different_public = different_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        is_valid, message = verify_signature(signed_manifest, different_public)
        
        assert not is_valid, "Signature should be invalid"
        assert "invalid" in message.lower() or "tamper" in message.lower()
    
    def test_verify_unsigned_manifest(self, test_manifest, test_keypair):
        """Test verifying unsigned manifest."""
        _, public_key_bytes = test_keypair
        
        is_valid, message = verify_signature(test_manifest, public_key_bytes)
        
        assert not is_valid
        assert "no signature" in message.lower()
    
    def test_sign_manifest_inplace(self, test_manifest):
        """Test signing manifest file in-place."""
        from cryptography.hazmat.primitives import serialization
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            
            # Write unsigned manifest
            manifest_path.write_text(test_manifest.model_dump_json())
            
            # Generate keypair
            private_key = Ed25519PrivateKey.generate()
            
            # Sign in-place
            sign_manifest_inplace(manifest_path, private_key, "test_key")
            
            # Read back and verify signature exists
            import json
            signed_data = json.loads(manifest_path.read_text())
            
            assert "signature" in signed_data
            assert signed_data["signature"].startswith("ed25519:test_key:")
    
    def test_get_signer_name(self):
        """Test extracting signer name from signature."""
        signature = "ed25519:my_key:abc123def456"
        
        signer = get_signer_name(signature)
        
        assert signer == "my_key"
    
    def test_get_signer_name_invalid(self):
        """Test handling invalid signature format."""
        assert get_signer_name(None) is None
        assert get_signer_name("invalid_format") is None
        assert get_signer_name("ed25519:only_two_parts") is None


class TestVerificationReport:
    """Test verification report generation."""
    
    def test_create_report_high_trust(self):
        """Test creating report for fully verified package."""
        manifest = ManifestModel(
            cli_command="test command",
            file_manifest={"test.txt": "abc123"}
        )
        
        report = create_verification_report(
            integrity_ok=True,
            signature_valid=True,
            signer_name="default",
            mismatches={},
            manifest=manifest
        )
        
        assert report["trust_level"] == "HIGH"
        assert report["integrity_ok"] is True
        assert report["signature_valid"] is True
        assert report["signer"] == "default"
        assert report["mismatches_count"] == 0
    
    def test_create_report_medium_trust(self):
        """Test creating report for unsigned but intact package."""
        manifest = ManifestModel(
            cli_command="test command",
            file_manifest={"test.txt": "abc123"}
        )
        
        report = create_verification_report(
            integrity_ok=True,
            signature_valid=None,
            signer_name=None,
            mismatches={},
            manifest=manifest
        )
        
        assert report["trust_level"] == "MEDIUM"
        assert report["integrity_ok"] is True
        assert report["signature_valid"] is None
    
    def test_create_report_no_trust(self):
        """Test creating report for compromised package."""
        manifest = ManifestModel(
            cli_command="test command",
            file_manifest={"test.txt": "abc123"}
        )
        
        report = create_verification_report(
            integrity_ok=False,
            signature_valid=None,
            signer_name=None,
            mismatches={"test.txt": "Hash mismatch"},
            manifest=manifest
        )
        
        assert report["trust_level"] == "NONE"
        assert report["integrity_ok"] is False
        assert report["mismatches_count"] == 1
    
    def test_create_report_invalid_signature(self):
        """Test creating report for package with invalid signature."""
        manifest = ManifestModel(
            cli_command="test command",
            file_manifest={"test.txt": "abc123"},
            signature="ed25519:fake:fakesig"
        )
        
        report = create_verification_report(
            integrity_ok=True,
            signature_valid=False,
            signer_name="fake",
            mismatches={},
            manifest=manifest
        )
        
        assert report["trust_level"] == "NONE"
        assert report["signature_valid"] is False
        assert "trust_message" in report
    
    def test_verify_signature_with_unsupported_algorithm(self):
        """Test verify_signature rejects unsupported algorithms."""
        from cryptography.hazmat.primitives import serialization
        
        test_manifest = ManifestModel(cli_command="test")
        private_key = Ed25519PrivateKey.generate()
        public_key_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        # Manually craft a signature with unsupported algorithm
        test_manifest.signature = "rsa:test_key:abc123"
        
        is_valid, message = verify_signature(test_manifest, public_key_bytes)
        
        assert not is_valid
        assert "unsupported" in message.lower()
    
    def test_verify_signature_with_malformed_signature(self):
        """Test verify_signature handles malformed signatures."""
        from cryptography.hazmat.primitives import serialization
        
        test_manifest = ManifestModel(cli_command="test")
        private_key = Ed25519PrivateKey.generate()
        public_key_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        # Test invalid format (only 2 parts)
        test_manifest.signature = "ed25519:keyname"
        is_valid, message = verify_signature(test_manifest, public_key_bytes)
        assert not is_valid
        assert "format" in message.lower()
    
    def test_verify_signature_generic_error(self):
        """Test verify_signature handles generic errors."""
        from cryptography.hazmat.primitives import serialization
        
        test_manifest = ManifestModel(cli_command="test")
        private_key = Ed25519PrivateKey.generate()
        public_key_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        # Invalid base64 in signature
        test_manifest.signature = "ed25519:test:not-valid-base64!!!"
        is_valid, message = verify_signature(test_manifest, public_key_bytes)
        
        assert not is_valid
        assert "error" in message.lower()
    
    def test_sign_manifest_error_handling(self):
        """Test sign_manifest error handling."""
        from cryptography.hazmat.primitives import serialization
        from epi_core.trust import SigningError
        
        manifest = ManifestModel(cli_command="test")
        
        # Pass invalid key type (should raise SigningError)
        with pytest.raises(SigningError):
            sign_manifest(manifest, "not-a-key", "test")  # type: ignore
    
    def test_sign_manifest_inplace_missing_file(self):
        """Test sign_manifest_inplace with non-existent file."""
        from cryptography.hazmat.primitives import serialization
        
        private_key = Ed25519PrivateKey.generate()
        non_existent = Path("/tmp/nonexistent_manifest.json")
        
        with pytest.raises(FileNotFoundError):
            sign_manifest_inplace(non_existent, private_key)
    
    def test_sign_manifest_inplace_error_handling(self):
        """Test sign_manifest_inplace error handling."""
        from cryptography.hazmat.primitives import serialization
        from epi_core.trust import SigningError
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            
            # Write invalid JSON
            manifest_path.write_text("{invalid json}")
            
            private_key = Ed25519PrivateKey.generate()
            
            with pytest.raises(SigningError):
                sign_manifest_inplace(manifest_path, private_key)


