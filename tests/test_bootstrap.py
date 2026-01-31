"""
Simple functional tests for bootstrap module
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from epi_recorder.bootstrap import initialize_recording


class TestBootstrapInitialization:
    """Test bootstrap initialization"""
    
    def test_initialize_recording_disabled_without_env(self):
        """Test that recording is disabled without EPI_RECORD=1"""
        with patch.dict('os.environ', {}, clear=True):
            # Should do nothing
            initialize_recording()
    
    def test_initialize_recording_requires_steps_dir(self, monkeypatch):
        """Test that steps directory is required"""
        monkeypatch.setenv('EPI_RECORD', '1')
        # No EPI_STEPS_DIR set
        
        with patch('sys.stderr'):
            initialize_recording()
            # Should print warning and return
    
    def test_initialize_recording_with_valid_setup(self, tmp_path, monkeypatch):
        """Test successful initialization"""
        steps_dir = tmp_path / "steps"
        steps_dir.mkdir()
        
        monkeypatch.setenv('EPI_RECORD', '1')
        monkeypatch.setenv('EPI_STEPS_DIR', str(steps_dir))
        
        with patch('epi_recorder.patcher.RecordingContext'), \
             patch('epi_recorder.patcher.set_recording_context'), \
             patch('epi_recorder.patcher.patch_all'):
            
            initialize_recording()
            # Should complete without error
    
    def test_initialize_recording_handles_errors(self, tmp_path, monkeypatch):
        """Test error handling"""
        steps_dir = tmp_path / "steps"
        steps_dir.mkdir()
        
        monkeypatch.setenv('EPI_RECORD', '1')
        monkeypatch.setenv('EPI_STEPS_DIR', str(steps_dir))
        
        with patch('epi_recorder.patcher.RecordingContext', side_effect=Exception("Test error")), \
             patch('sys.stderr'):
            
            # Should not raise
            initialize_recording()


