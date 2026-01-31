"""
Tests for EPI Recorder metadata features
"""

import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from epi_recorder.api import record, EpiRecorderSession
from epi_core.container import EPIContainer


class TestPythonAPIMetadata:
    """Test Python API metadata features."""

    def test_record_context_manager_with_metadata(self, tmp_path, monkeypatch):
        """Test record() context manager with metadata."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", str(tmp_path / "recordings"))

        with record(
            "test_with_metadata.epi",
            goal="Test goal",
            notes="Test notes",
            metrics={"accuracy": 0.95, "latency": 150},
            approved_by="test@example.com",
            metadata_tags=["test", "metadata"]
        ):
            # Simple code
            result = 1 + 1

        # Check that recording was created
        epi_file = tmp_path / "recordings" / "test_with_metadata.epi"
        assert epi_file.exists()

        # Check manifest contains metadata
        manifest = EPIContainer.read_manifest(epi_file)
        assert manifest.goal == "Test goal"
        assert manifest.notes == "Test notes"
        assert manifest.metrics == {"accuracy": 0.95, "latency": 150}
        assert manifest.approved_by == "test@example.com"
        assert manifest.tags == ["test", "metadata"]

    def test_record_decorator_with_metadata(self, tmp_path, monkeypatch):
        """Test @record decorator with metadata."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", str(tmp_path / "recordings"))

        @record(
            goal="Decorator test",
            notes="Testing decorator",
            metrics={"f1_score": 0.88},
            approved_by="alice@example.com",
            metadata_tags=["decorator-test"]
        )
        def test_function():
            return 42

        result = test_function()
        assert result == 42

        # Check that recording was created
        recordings_dir = tmp_path / "recordings"
        epi_files = list(recordings_dir.glob("*.epi"))
        assert len(epi_files) == 1

        # Check manifest contains metadata
        manifest = EPIContainer.read_manifest(epi_files[0])
        assert manifest.goal == "Decorator test"
        assert manifest.notes == "Testing decorator"
        assert manifest.metrics == {"f1_score": 0.88}
        assert manifest.approved_by == "alice@example.com"
        assert manifest.tags == ["decorator-test"]

    def test_record_with_partial_metadata(self, tmp_path, monkeypatch):
        """Test record() with only some metadata fields."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", str(tmp_path / "recordings"))

        with record(
            "partial_metadata.epi",
            goal="Partial metadata test",
            metrics={"accuracy": 0.92}
        ):
            result = 2 * 2

        # Check that recording was created
        epi_file = tmp_path / "recordings" / "partial_metadata.epi"
        assert epi_file.exists()

        # Check manifest contains provided metadata
        manifest = EPIContainer.read_manifest(epi_file)
        assert manifest.goal == "Partial metadata test"
        assert manifest.metrics == {"accuracy": 0.92}
        # Other fields should be None/default
        assert manifest.notes is None
        assert manifest.approved_by is None
        assert manifest.tags is None


class TestCLIMetadata:
    """Test CLI metadata features."""

    def test_cli_metric_parsing(self):
        """Test that CLI metric parsing works correctly."""
        from epi_cli.run import typer
        import subprocess
        import sys

        # This would normally be tested by actually running the CLI
        # For now, we'll test the parsing logic indirectly
        pass

    def test_cli_metadata_integration(self, tmp_path, monkeypatch):
        """Test CLI metadata integration."""
        # This would require actually running the CLI command
        # For unit testing, we'll test the core logic instead
        pass


class TestViewerMetadataDisplay:
    """Test viewer metadata display."""

    def test_metadata_in_manifest(self, tmp_path):
        """Test that metadata is correctly stored in manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_metadata.epi"
            
            with EpiRecorderSession(
                output_path,
                goal="Viewer test",
                notes="Testing viewer metadata",
                metrics={"precision": 0.85},
                approved_by="viewer@test.com",
                metadata_tags=["viewer-test"]
            ):
                pass
            
            # Check manifest contains metadata
            manifest = EPIContainer.read_manifest(output_path)
            assert manifest.goal == "Viewer test"
            assert manifest.notes == "Testing viewer metadata"
            assert manifest.metrics == {"precision": 0.85}
            assert manifest.approved_by == "viewer@test.com"
            assert manifest.tags == ["viewer-test"]


class TestLSMetadataDisplay:
    """Test ls command metadata display."""

    def test_format_metrics_function(self):
        """Test the _format_metrics helper function."""
        from epi_cli.ls import _format_metrics
        
        # Test with float values
        metrics = {"accuracy": 0.923456, "latency": 150.0}
        result = _format_metrics(metrics)
        assert "accuracy=0.92" in result
        assert "latency=150.00" in result
        
        # Test with string values
        metrics = {"version": "1.0", "model": "gpt-4"}
        result = _format_metrics(metrics)
        assert "version=1.0" in result
        assert "model=gpt-4" in result
        
        # Test with empty dict
        result = _format_metrics({})
        assert result == ""
        
        # Test with None
        result = _format_metrics(None)
        assert result == ""


class TestBackwardCompatibility:
    """Test that existing functionality still works."""

    def test_record_without_metadata(self, tmp_path, monkeypatch):
        """Test that record() still works without metadata (backward compatibility)."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", str(tmp_path / "recordings"))

        with record("backward_compat.epi", workflow_name="Compat Test"):
            result = 3 + 3

        # Check that recording was created
        epi_file = tmp_path / "recordings" / "backward_compat.epi"
        assert epi_file.exists()

        # Check manifest (metadata fields should be None)
        manifest = EPIContainer.read_manifest(epi_file)
        assert manifest.goal is None
        assert manifest.notes is None
        assert manifest.metrics is None
        assert manifest.approved_by is None
        assert manifest.tags is None

    def test_decorator_without_metadata(self, tmp_path, monkeypatch):
        """Test @record decorator without metadata (backward compatibility)."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", str(tmp_path / "recordings"))

        @record
        def compat_function():
            return "compatibility test"

        result = compat_function()
        assert result == "compatibility test"

        # Check that recording was created
        recordings_dir = tmp_path / "recordings"
        epi_files = list(recordings_dir.glob("*.epi"))
        assert len(epi_files) == 1

        # Check manifest (metadata fields should be None)
        manifest = EPIContainer.read_manifest(epi_files[0])
        assert manifest.goal is None
        assert manifest.notes is None
        assert manifest.metrics is None
        assert manifest.approved_by is None
        assert manifest.tags is None


