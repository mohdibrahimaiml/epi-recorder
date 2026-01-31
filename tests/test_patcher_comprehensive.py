"""
Simple tests for patcher module functions
"""
import pytest
from unittest.mock import patch, MagicMock
from epi_recorder.patcher import (
    RecordingContext,
    set_recording_context,
    get_recording_context,
    is_recording,
    patch_all
)


class TestRecordingContext:
    """Test RecordingContext class"""
    
    def test_creates_context(self, tmp_path):
        """Test context creation"""
        ctx = RecordingContext(tmp_path, enable_redaction=True)
        assert ctx is not None
    
    def test_adds_steps(self, tmp_path):
        """Test adding steps"""
        ctx = RecordingContext(tmp_path)
        ctx.add_step("test.step", {"data": "value"})
        # Should not raise
    
    def test_step_file_created(self, tmp_path):
        """Test that steps file is created"""
        ctx = RecordingContext(tmp_path)
        ctx.add_step("test", {})
        
        steps_file = tmp_path / "steps.jsonl"
        assert steps_file.exists()


class TestRecordingContextManagement:
    """Test global context management"""
    
    def test_set_and_get_context(self, tmp_path):
        """Test setting and getting context"""
        ctx = RecordingContext(tmp_path)
        set_recording_context(ctx)
        
        retrieved = get_recording_context()
        assert retrieved == ctx
    
    def test_is_recording_when_context_set(self, tmp_path):
        """Test is_recording() returns True when context is set"""
        ctx = RecordingContext(tmp_path)
        set_recording_context(ctx)
        
        assert is_recording() == True
    
    def test_is_recording_when_no_context(self):
        """Test is_recording() returns False  when no context"""
        set_recording_context(None)
        assert is_recording() == False


class TestPatchAll:
    """Test patch_all function"""
    
    def test_patch_all_returns_dict(self):
        """Test that patch_all returns a dictionary"""
        result = patch_all()
        assert isinstance(result, dict)
    
    def test_patch_all_attempts_patching(self):
        """Test that patch_all attempts to patch providers"""
        result = patch_all()
        # Should have some provider results
        assert len(result) > 0
    
    def test_patch_all_includes_openai(self):
        """Test that patch_all tries to patch OpenAI"""
        result = patch_all()
        assert "openai" in result
    
    def test_patch_all_includes_gemini(self):
        """Test that patch_all tries to patch Gemini"""
        result = patch_all()
        assert "gemini" in result


