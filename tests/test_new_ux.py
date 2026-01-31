"""
Tests for the new simplified UX (epi run, @record, zero-config).
"""

import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from epi_recorder.api import _auto_generate_output_path, _resolve_output_path, record


class TestAutoNaming:
    """Test automatic filename generation."""
    
    def test_auto_generate_with_hint(self, tmp_path, monkeypatch):
        """Test auto-generation with a name hint."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", "epi-recordings")
        
        path = _auto_generate_output_path("my_script.py")
        
        assert path.parent.name == "epi-recordings"
        assert path.stem.startswith("my_script_")
        assert path.suffix == ".epi"
        assert len(path.stem.split("_")) >= 3  # name_YYYYMMDD_HHMMSS
    
    def test_auto_generate_without_hint(self, tmp_path, monkeypatch):
        """Test auto-generation without a name hint."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", "epi-recordings")
        
        path = _auto_generate_output_path()
        
        assert path.parent.name == "epi-recordings"
        assert path.stem.startswith("recording_")
        assert path.suffix == ".epi"
    
    def test_timestamp_format(self, tmp_path, monkeypatch):
        """Test that timestamp is correctly formatted."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", "epi-recordings")
        
        path = _auto_generate_output_path("test")
        
        # Extract timestamp part
        parts = path.stem.split("_")
        assert len(parts) >= 3
        
        # Verify timestamp format (YYYYMMDD_HHMMSS)
        date_part = parts[-2]
        time_part = parts[-1]
        
        assert len(date_part) == 8  # YYYYMMDD
        assert len(time_part) == 6  # HHMMSS
        assert date_part.isdigit()
        assert time_part.isdigit()


class TestPathResolution:
    """Test path resolution logic."""
    
    def test_resolve_none_generates_auto(self, tmp_path, monkeypatch):
        """Test that None generates auto path."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", "epi-recordings")
        
        path = _resolve_output_path(None)
        
        assert path.parent.name == "epi-recordings"
        assert path.suffix == ".epi"
    
    def test_resolve_adds_extension(self, tmp_path, monkeypatch):
        """Test that .epi extension is added if missing."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", "epi-recordings")
        
        path = _resolve_output_path("my_test")
        
        assert path.suffix == ".epi"
        assert path.name == "my_test.epi"
    
    def test_resolve_preserves_extension(self, tmp_path, monkeypatch):
        """Test that existing .epi extension is preserved."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", "epi-recordings")
        
        path = _resolve_output_path("my_test.epi")
        
        assert path.suffix == ".epi"
        assert path.name == "my_test.epi"
    
    def test_resolve_uses_recordings_dir(self, tmp_path, monkeypatch):
        """Test that files go to epi-recordings/ by default."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", "epi-recordings")
        
        path = _resolve_output_path("test.epi")
        
        assert path.parent.name == "epi-recordings"
    
    def test_resolve_respects_absolute_path(self, tmp_path, monkeypatch):
        """Test that absolute paths are respected."""
        monkeypatch.chdir(tmp_path)
        
        absolute_path = tmp_path / "custom" / "location" / "test.epi"
        path = _resolve_output_path(str(absolute_path))
        
        assert path == absolute_path


class TestDecoratorUsage:
    """Test the @record decorator."""
    
    def test_decorator_auto_names_from_function(self, tmp_path, monkeypatch):
        """Test that decorator uses function name for auto-naming."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", str(tmp_path / "recordings"))
        
        @record
        def my_test_function():
            return 42
        
        result = my_test_function()
        
        assert result == 42
        
        # Check that recording was created
        recordings_dir = tmp_path / "recordings"
        assert recordings_dir.exists()
        
        epi_files = list(recordings_dir.glob("*.epi"))
        assert len(epi_files) == 1
        assert epi_files[0].stem.startswith("my_test_function_")


class TestZeroConfigContextManager:
    """Test the zero-config context manager."""
    
    def test_zero_config_creates_file(self, tmp_path, monkeypatch):
        """Test that zero-config creates a file in recordings dir."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", str(tmp_path / "recordings"))
        
        with record():
            # Simple code
            x = 1 + 1
        
        # Check that recording was created
        recordings_dir = tmp_path / "recordings"
        assert recordings_dir.exists()
        
        epi_files = list(recordings_dir.glob("*.epi"))
        assert len(epi_files) == 1
    
    def test_with_custom_name(self, tmp_path, monkeypatch):
        """Test context manager with custom name."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EPI_RECORDINGS_DIR", str(tmp_path / "recordings"))
        
        with record("my_custom_name"):
            x = 1 + 1
        
        # Check that recording was created with custom name
        recordings_dir = tmp_path / "recordings"
        epi_files = list(recordings_dir.glob("my_custom_name*.epi"))
        assert len(epi_files) == 1
        assert epi_files[0].name == "my_custom_name.epi"


