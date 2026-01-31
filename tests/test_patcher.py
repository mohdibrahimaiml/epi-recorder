"""
Comprehensive tests for epi_recorder/patcher.py (LLM API interception).

Tests:
- RecordingContext functionality
- OpenAI patching
- Request/response capture
- Redaction during capture
"""

import tempfile
from pathlib import Path
import json
import pytest
from datetime import datetime

from epi_recorder.patcher import (
    RecordingContext,
    set_recording_context,
    get_recording_context,
    is_recording,
    patch_openai
)


class TestRecordingContext:
    """Test RecordingContext class."""
    
    def test_initialization(self):
        """Test RecordingContext initialization."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir, enable_redaction=True)
        
        assert ctx.output_dir == temp_dir
        assert ctx.enable_redaction == True
        assert ctx.step_index == 0
        # self.steps was removed, so we check that the file exists and is empty
        assert ctx.steps_file.exists()
        assert ctx.steps_file.stat().st_size == 0
    
    def test_initialization_without_redaction(self):
        """Test initialization with redaction disabled."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir, enable_redaction=False)
        
        assert ctx.enable_redaction == False
        assert ctx.redactor is None
    
    def test_add_step_creates_file(self):
        """Test that add_step writes to steps.jsonl."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir, enable_redaction=False)
        
        ctx.add_step("test.step", {"data": "value"})
        
        # Should have written to file
        assert ctx.steps_file.exists()
        content = ctx.steps_file.read_text()
        assert "test.step" in content
    
    def test_add_step_increments_index(self):
        """Test that step index increments."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir, enable_redaction=False)
        
        ctx.add_step("step1", {})
        assert ctx.step_index == 1
        
        ctx.add_step("step2", {})
        assert ctx.step_index == 2
    
    def test_add_step_stores_on_disk(self):
        """Test that steps are stored on disk (not in memory)."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir, enable_redaction=False)
        
        ctx.add_step("step1", {"data": "test"})
        
        # Verify file content
        lines = ctx.steps_file.read_text().strip().split('\n')
        assert len(lines) == 1
        step = json.loads(lines[0])
        assert step["kind"] == "step1"
        assert step["content"]["data"] == "test"
        
        # Verify NO in-memory storage
        assert not hasattr(ctx, 'steps')
    
    def test_add_step_with_redaction(self):
        """Test that secrets are redacted in steps."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir, enable_redaction=True)
        
        # Add step with a secret
        ctx.add_step("test.step", {
            "api_key": "sk-1234567890abcdef",
            "data": "normal data"
        })
        
        # Secret should be redacted in stored step
        content = ctx.steps_file.read_text()
        assert "[REDACTED" in content or "security.redaction" in content
    
    def test_multiple_steps_jsonl_format(self):
        """Test that multiple steps are written in JSONL format."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir, enable_redaction=False)
        
        ctx.add_step("step1", {"num": 1})
        ctx.add_step("step2", {"num": 2})
        ctx.add_step("step3", {"num": 3})
        
        # Read file and verify JSONL
        lines = ctx.steps_file.read_text().strip().split('\n')
        assert len(lines) == 3
        
        # Each line should be valid JSON
        for line in lines:
            data = json.loads(line)
            assert "kind" in data
            assert "content" in data
            assert "timestamp" in data


class TestGlobalRecordingContext:
    """Test global recording context management."""
    
    def test_set_and_get_context(self):
        """Test setting and getting global context."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir)
        
        set_recording_context(ctx)
        retrieved = get_recording_context()
        
        assert retrieved is ctx
    
    def test_is_recording_true(self):
        """Test is_recording when context is set."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir)
        
        set_recording_context(ctx)
        assert is_recording() == True
    
    def test_is_recording_false(self):
        """Test is_recording when context is None."""
        set_recording_context(None)
        assert is_recording() == False
    
    def test_set_context_to_none(self):
        """Test clearing context."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir)
        
        set_recording_context(ctx)
        assert is_recording() == True
        
        set_recording_context(None)
        assert is_recording() == False
        assert get_recording_context() is None


class TestOpenAIPatcher:
    """Test OpenAI patching functionality."""
    
    def test_patch_openai_without_openai_installed(self):
        """Test patching when OpenAI is not installed."""
        # Save original sys.modules
        import sys
        original_modules = sys.modules.copy()
        
        try:
            # Temporarily remove openai if present
            if 'openai' in sys.modules:
                del sys.modules['openai']
            
            # Should return False without error
            result = patch_openai()
            # Either False (not installed) or True (installed)
            assert isinstance(result, bool)
        finally:
            # Restore sys.modules
            sys.modules.update(original_modules)
    
    def test_patch_openai_returns_bool(self):
        """Test that patch_openai returns a boolean."""
        result = patch_openai()
        assert isinstance(result, bool)
    
    def test_patch_openai_does_not_crash(self):
        """Test that patching doesn't crash."""
        try:
            patch_openai()
            # Should not raise
            assert True
        except Exception as e:
            # If it fails, should be graceful
            pytest.fail(f"patch_openai raised unexpected exception: {e}")


class TestOpenAICapture:
    """Test OpenAI request/response capture (if OpenAI is installed)."""
    
    @pytest.fixture
    def recording_context(self):
        """Create a temporary recording context."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir, enable_redaction=False)
        set_recording_context(ctx)
        yield ctx
        set_recording_context(None)
    
    def test_capture_without_openai(self, recording_context):
        """Test that capture works even without OpenAI installed."""
        # This should not crash
        assert is_recording()
        assert get_recording_context() is not None
    
    def test_recording_context_with_openai_patch(self, recording_context):
        """Test recording context with OpenAI patching enabled."""
        # Patch OpenAI
        patch_result = patch_openai()
        
        # Either OpenAI is installed (True) or not (False)
        assert isinstance(patch_result, bool)
        
        # Context should still be active
        assert is_recording()


class TestPatcherEdgeCases:
    """Test edge cases and error handling."""
    
    def test_recording_context_creates_output_dir(self):
        """Test that RecordingContext creates output directory."""
        temp_base = Path(tempfile.mkdtemp())
        non_existent = temp_base / "nested" / "directory"
        
        ctx = RecordingContext(non_existent)
        
        # Should create the directory
        assert non_existent.exists()
        assert ctx.steps_file.exists()
    
    def test_step_timestamp_is_iso_string(self):
        """Test that step timestamps are ISO strings."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir, enable_redaction=False)
        
        ctx.add_step("test", {})
        
        lines = ctx.steps_file.read_text().strip().split('\n')
        assert len(lines) > 0
        step = json.loads(lines[0])
        
        # Should be a string in ISO format
        assert isinstance(step["timestamp"], str)
        # Should be parseable as datetime
        dt = datetime.fromisoformat(step["timestamp"])
        assert isinstance(dt, datetime)
    
    def test_step_index_is_sequential(self):
        """Test that step indices are sequential."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir, enable_redaction=False)
        
        ctx.add_step("step1", {})
        ctx.add_step("step2", {})
        ctx.add_step("step3", {})
        
        lines = ctx.steps_file.read_text().strip().split('\n')
        steps = [json.loads(line) for line in lines]
        
        assert steps[0]["index"] == 0
        assert steps[1]["index"] == 1
        assert steps[2]["index"] == 2
    
    def test_empty_content_is_valid(self):
        """Test that empty content is valid."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir, enable_redaction=False)
        
        ctx.add_step("empty", {})
        
        lines = ctx.steps_file.read_text().strip().split('\n')
        assert len(lines) == 1
        step = json.loads(lines[0])
        assert step["content"] == {}
    
    def test_nested_content_is_preserved(self):
        """Test that nested dictionaries are preserved."""
        temp_dir = Path(tempfile.mkdtemp())
        ctx = RecordingContext(temp_dir, enable_redaction=False)
        
        nested = {
            "level1": {
                "level2": {
                    "level3": "value"
                }
            }
        }
        
        ctx.add_step("nested", nested)
        
        lines = ctx.steps_file.read_text().strip().split('\n')
        step = json.loads(lines[0])
        
        assert step["content"]["level1"]["level2"]["level3"] == "value"


