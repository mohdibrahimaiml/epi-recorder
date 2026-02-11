"""
Tests for epi_core.container - ZIP container management

Tests the core .epi file format creation and extraction logic.
"""

import tempfile
from pathlib import Path

import pytest

from epi_core.container import EPIContainer, EPI_MIMETYPE
from epi_core.schemas import ManifestModel


class TestEPIContainer:
    """Test suite for EPI container operations."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        with tempfile.TemporaryDirectory(prefix="epi_test_") as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def sample_files(self, temp_workspace):
        """Create sample files for packing."""
        workspace = temp_workspace / "source"
        workspace.mkdir()
        
        # Create test files
        (workspace / "test.txt").write_text("Hello EPI")
        (workspace / "data.json").write_text('{"key": "value"}')
        
        # Create subdirectory with file
        subdir = workspace / "artifacts"
        subdir.mkdir()
        (subdir / "output.log").write_text("Processing complete")
        
        return workspace
    
    def test_pack_creates_valid_epi_file(self, temp_workspace, sample_files):
        """Test basic .epi file creation."""
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        
        EPIContainer.pack(sample_files, manifest, output_path)
        
        assert output_path.exists(), ".epi file should be created"
        assert output_path.stat().st_size > 0, ".epi file should not be empty"
    
    def test_pack_populates_file_manifest(self, temp_workspace, sample_files):
        """Test that pack() populates the file manifest with hashes."""
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        
        EPIContainer.pack(sample_files, manifest, output_path)
        
        assert len(manifest.file_manifest) > 0, "File manifest should be populated"
        assert "test.txt" in manifest.file_manifest, "test.txt should be in manifest"
        assert "data.json" in manifest.file_manifest, "data.json should be in manifest"
        assert "artifacts/output.log" in manifest.file_manifest, "Subdir file should be in manifest"
        
        # Verify hashes are SHA-256 (64 hex characters)
        for filename, file_hash in manifest.file_manifest.items():
            assert len(file_hash) == 64, f"Hash for {filename} should be 64 characters"
            assert file_hash.isalnum(), f"Hash for {filename} should be alphanumeric"
    
    def test_unpack_extracts_all_files(self, temp_workspace, sample_files):
        """Test that unpack() correctly extracts files."""
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        
        # Pack
        EPIContainer.pack(sample_files, manifest, output_path)
        
        # Unpack
        extract_dir = EPIContainer.unpack(output_path)
        
        assert extract_dir.exists(), "Extract directory should exist"
        assert (extract_dir / "test.txt").exists(), "test.txt should be extracted"
        assert (extract_dir / "data.json").exists(), "data.json should be extracted"
        assert (extract_dir / "artifacts" / "output.log").exists(), "Subdir file should be extracted"
        assert (extract_dir / "manifest.json").exists(), "manifest.json should be extracted"
        assert (extract_dir / "mimetype").exists(), "mimetype should be extracted"
    
    def test_mimetype_is_correct(self, temp_workspace, sample_files):
        """Test that mimetype file contains correct value."""
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        
        EPIContainer.pack(sample_files, manifest, output_path)
        extract_dir = EPIContainer.unpack(output_path)
        
        mimetype_content = (extract_dir / "mimetype").read_text().strip()
        assert mimetype_content == EPI_MIMETYPE, f"Mimetype should be {EPI_MIMETYPE}"
    
    def test_read_manifest_without_full_extraction(self, temp_workspace, sample_files):
        """Test reading manifest without extracting all files."""
        output_path = temp_workspace / "test.epi"
        test_command = "epi record --out test.epi -- python script.py"
        manifest = ManifestModel(cli_command=test_command)
        
        EPIContainer.pack(sample_files, manifest, output_path)
        
        # Read manifest directly
        read_manifest = EPIContainer.read_manifest(output_path)
        
        assert read_manifest.cli_command == test_command, "CLI command should match"
        assert read_manifest.spec_version == "2.4.0", "Spec version should match"
        assert len(read_manifest.file_manifest) > 0, "File manifest should be populated"
    
    def test_verify_integrity_success(self, temp_workspace, sample_files):
        """Test integrity verification for untampered .epi file."""
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        
        EPIContainer.pack(sample_files, manifest, output_path)
        
        is_valid, mismatches = EPIContainer.verify_integrity(output_path)
        
        assert is_valid, "Integrity check should pass for untampered file"
        assert len(mismatches) == 0, "There should be no mismatches"
    
    def test_verify_integrity_detects_tampering(self, temp_workspace, sample_files):
        """Test that integrity verification detects file tampering."""
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        
        # Pack original
        EPIContainer.pack(sample_files, manifest, output_path)
        
        # Tamper with the ZIP by modifying a file
        import zipfile
        
        # Extract and modify
        extract_dir = EPIContainer.unpack(output_path)
        (extract_dir / "test.txt").write_text("TAMPERED CONTENT")
        
        # Re-pack without updating hashes (simulating tampering)
        tampered_path = temp_workspace / "tampered.epi"
        with zipfile.ZipFile(tampered_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("mimetype", EPI_MIMETYPE, compress_type=zipfile.ZIP_STORED)
            zf.write(extract_dir / "test.txt", "test.txt")
            zf.write(extract_dir / "data.json", "data.json")
            zf.write(extract_dir / "artifacts" / "output.log", "artifacts/output.log")
            zf.write(extract_dir / "manifest.json", "manifest.json")
        
        # Verify (should detect tampering)
        is_valid, mismatches = EPIContainer.verify_integrity(tampered_path)
        
        assert not is_valid, "Integrity check should fail for tampered file"
        assert len(mismatches) > 0, "Mismatches should be detected"
        assert "test.txt" in mismatches, "test.txt tampering should be detected"
    
    def test_pack_with_nonexistent_source(self, temp_workspace):
        """Test error handling for nonexistent source directory."""
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        fake_source = temp_workspace / "nonexistent"
        
        with pytest.raises(FileNotFoundError):
            EPIContainer.pack(fake_source, manifest, output_path)
    
    def test_unpack_with_nonexistent_file(self, temp_workspace):
        """Test error handling for nonexistent .epi file."""
        fake_epi = temp_workspace / "nonexistent.epi"
        
        with pytest.raises(FileNotFoundError):
            EPIContainer.unpack(fake_epi)
    
    def test_unpack_with_invalid_zip(self, temp_workspace):
        """Test error handling for invalid ZIP file."""
        invalid_file = temp_workspace / "invalid.epi"
        invalid_file.write_text("This is not a ZIP file")
        
        with pytest.raises(ValueError, match="Not a valid ZIP file"):
            EPIContainer.unpack(invalid_file)
    
    def test_read_manifest_with_invalid_json(self, temp_workspace, sample_files):
        """Test error handling for corrupted manifest JSON."""
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        
        EPIContainer.pack(sample_files, manifest, output_path)
        
        # Corrupt the manifest
        import zipfile
        corrupt_path = temp_workspace / "corrupt.epi"
        with zipfile.ZipFile(output_path, "r") as zf_in:
            with zipfile.ZipFile(corrupt_path, "w") as zf_out:
                for item in zf_in.namelist():
                    if item != "manifest.json":
                        zf_out.writestr(item, zf_in.read(item))
                    else:
                        zf_out.writestr(item, "INVALID JSON")
        
        with pytest.raises(ValueError, match="Invalid JSON"):
            EPIContainer.read_manifest(corrupt_path)
    
    def test_forward_slash_in_archive_paths(self, temp_workspace, sample_files):
        """Test that archive paths use forward slashes (ZIP standard)."""
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        
        EPIContainer.pack(sample_files, manifest, output_path)
        
        # Check manifest uses forward slashes
        for path in manifest.file_manifest.keys():
            assert "\\" not in path, f"Path {path} should use forward slashes, not backslashes"
    
    def test_pack_with_file_as_source(self, temp_workspace):
        """Test error handling when source is a file not a directory."""
        file_source = temp_workspace / "file.txt"
        file_source.write_text("I am a file")
        
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        
        with pytest.raises(ValueError, match="must be a directory"):
            EPIContainer.pack(file_source, manifest, output_path)
    
    def test_unpack_with_missing_mimetype(self, temp_workspace, sample_files):
        """Test error handling for .epi file missing mimetype."""
        import zipfile
        
        # Create .epi without mimetype
        output_path = temp_workspace / "no_mimetype.epi"
        with zipfile.ZipFile(output_path, "w") as zf:
            zf.writestr("manifest.json", ManifestModel(cli_command="test").model_dump_json())
        
        with pytest.raises(ValueError, match="Missing mimetype"):
            EPIContainer.unpack(output_path)
    
    def test_unpack_with_wrong_mimetype(self, temp_workspace, sample_files):
        """Test error handling for incorrect mimetype."""
        import zipfile
        
        # Create .epi with wrong mimetype
        output_path = temp_workspace / "wrong_mimetype.epi"
        with zipfile.ZipFile(output_path, "w") as zf:
            zf.writestr("mimetype", "application/zip", compress_type=zipfile.ZIP_STORED)
            zf.writestr("manifest.json", ManifestModel(cli_command="test").model_dump_json())
        
        with pytest.raises(ValueError, match="Invalid mimetype"):
            EPIContainer.unpack(output_path)
    
    def test_read_manifest_with_nonexistent_file(self, temp_workspace):
        """Test read_manifest with nonexistent file."""
        fake_path = temp_workspace / "nonexistent.epi"
        
        with pytest.raises(FileNotFoundError):
            EPIContainer.read_manifest(fake_path)
    
    def test_read_manifest_with_invalid_zip(self, temp_workspace):
        """Test read_manifest with invalid ZIP."""
        invalid_file = temp_workspace / "invalid.epi"
        invalid_file.write_text("Not a ZIP")
        
        with pytest.raises(ValueError, match="Not a valid ZIP"):
            EPIContainer.read_manifest(invalid_file)
    
    def test_read_manifest_with_missing_manifest(self, temp_workspace):
        """Test read_manifest when manifest.json is missing."""
        import zipfile
        
        # Create .epi without manifest.json
        output_path = temp_workspace / "no_manifest.epi"
        with zipfile.ZipFile(output_path, "w") as zf:
            zf.writestr("mimetype", EPI_MIMETYPE, compress_type=zipfile.ZIP_STORED)
        
        with pytest.raises(ValueError, match="Missing manifest.json"):
            EPIContainer.read_manifest(output_path)
    
    def test_verify_integrity_with_missing_file(self, temp_workspace, sample_files):
        """Test verify_integrity when a file in manifest is missing from archive."""
        import zipfile
        
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        
        # Pack normally
        EPIContainer.pack(sample_files, manifest, output_path)
        
        # Create a new .epi with missing file but manifest still references it
        missing_file_path = temp_workspace / "missing_file.epi"
        with zipfile.ZipFile(output_path, "r") as zf_in:
            with zipfile.ZipFile(missing_file_path, "w") as zf_out:
                for item in zf_in.namelist():
                    if item != "test.txt":  # Skip one file
                        zf_out.writestr(item, zf_in.read(item))
        
        is_valid, mismatches = EPIContainer.verify_integrity(missing_file_path)
        
        assert not is_valid
        assert "test.txt" in mismatches
        assert "missing" in mismatches["test.txt"].lower()
    
    def test_verify_integrity_with_nonexistent_file(self, temp_workspace):
        """Test verify_integrity with nonexistent .epi file."""
        fake_path = temp_workspace / "nonexistent.epi"
        
        with pytest.raises(FileNotFoundError):
            EPIContainer.verify_integrity(fake_path)
    
    def test_embedded_viewer_with_steps(self, temp_workspace, sample_files):
        """Test that embedded viewer includes steps data."""
        # Create steps.jsonl
        steps_file = sample_files / "steps.jsonl"
        steps_file.write_text(
            '{"index": 0, "kind": "test", "content": {}}\n'
            '{"index": 1, "kind": "test2", "content": {}}\n'
        )
        
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        
        EPIContainer.pack(sample_files, manifest, output_path)
        
        # Extract and check viewer.html
        extract_dir = EPIContainer.unpack(output_path)
        viewer_html = (extract_dir / "viewer.html").read_text()
        
        assert "epi-data" in viewer_html
        assert "test" in viewer_html
    
    def test_embedded_viewer_with_invalid_json_in_steps(self, temp_workspace, sample_files):
        """Test that embedded viewer handles invalid JSON in steps.jsonl gracefully."""
        # Create steps.jsonl with invalid JSON
        steps_file = sample_files / "steps.jsonl"
        steps_file.write_text(
            '{"index": 0, "kind": "test", "content": {}}\n'
            '{invalid json}\n'
            '{"index": 2, "kind": "test2", "content": {}}\n'
        )
        
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        
        # Should not crash, just skip invalid lines
        EPIContainer.pack(sample_files, manifest, output_path)
        
        assert output_path.exists()
    
    def test_minimal_viewer_fallback(self, temp_workspace, sample_files, monkeypatch):
        """Test that minimal viewer is used when template is missing."""
        # Mock template path to non-existent location
        def mock_create_viewer(source_dir, manifest):
            # Force use of minimal viewer
            from epi_core.container import EPIContainer
            return EPIContainer._create_minimal_viewer(manifest)
        
        monkeypatch.setattr(EPIContainer, "_create_embedded_viewer", mock_create_viewer)
        
        output_path = temp_workspace / "test.epi"
        manifest = ManifestModel(cli_command="test command")
        
        EPIContainer.pack(sample_files, manifest, output_path)
        
        # Extract and verify minimal viewer was used
        extract_dir = EPIContainer.unpack(output_path)
        viewer_html = (extract_dir / "viewer.html").read_text()
        
        assert "EPI Viewer" in viewer_html
        assert "<!DOCTYPE html>" in viewer_html



 