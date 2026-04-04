"""
Tests for EPI wrapper clients and explicit API.

Tests the new v2.3.0 architecture without monkey patching.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock
from datetime import datetime


class TestExplicitAPI:
    """Test explicit logging API (log_llm_call, log_chat)."""
    
    def test_log_chat_records_request_and_response(self, tmp_path):
        """log_chat should record both request and response steps."""
        from epi_recorder import record
        
        epi_file = tmp_path / "test.epi"
        
        with record(str(epi_file)) as epi:
            epi.log_chat(
                model="gpt-4",
                messages=[{"role": "user", "content": "Hello"}],
                response_content="Hi there!",
                provider="openai"
            )
        
        # Verify file was created
        assert epi_file.exists()
        
        # Verify steps were recorded
        import zipfile
        import json
        
        with zipfile.ZipFile(epi_file, 'r') as zf:
            steps_content = zf.read("steps.jsonl").decode("utf-8")
            steps = [json.loads(line) for line in steps_content.strip().split("\n") if line]
        
        # Should have: session.start, llm.request, llm.response, environment.captured, session.end
        step_kinds = [s["kind"] for s in steps]
        assert "llm.request" in step_kinds
        assert "llm.response" in step_kinds
    
    def test_log_llm_call_with_mock_openai_response(self, tmp_path):
        """log_llm_call should auto-detect OpenAI response format."""
        from epi_recorder import record
        
        epi_file = tmp_path / "test.epi"
        
        # Create mock OpenAI response
        mock_response = Mock()
        mock_response.model = "gpt-4"
        mock_response.choices = [
            Mock(
                message=Mock(role="assistant", content="Hello!"),
                finish_reason="stop"
            )
        ]
        mock_response.usage = Mock(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15
        )
        
        with record(str(epi_file)) as epi:
            epi.log_llm_call(
                mock_response,
                messages=[{"role": "user", "content": "Hi"}]
            )
        
        assert epi_file.exists()
        
        # Verify LLM steps
        import zipfile
        import json
        
        with zipfile.ZipFile(epi_file, 'r') as zf:
            steps_content = zf.read("steps.jsonl").decode("utf-8")
            steps = [json.loads(line) for line in steps_content.strip().split("\n") if line]
        
        llm_response = [s for s in steps if s["kind"] == "llm.response"]
        assert len(llm_response) == 1
        assert llm_response[0]["content"]["provider"] == "openai"
        assert llm_response[0]["content"]["model"] == "gpt-4"
    
    def test_record_without_patching_no_auto_capture(self, tmp_path):
        """Without legacy_patching, LLM calls are NOT auto-captured."""
        from epi_recorder import record
        
        epi_file = tmp_path / "test.epi"
        
        # This should NOT capture any LLM calls automatically
        with record(str(epi_file)) as epi:
            # Simulate what would happen with a real LLM call
            # Without patching, nothing is auto-logged
            pass
        
        assert epi_file.exists()
        
        # Only session steps should exist
        import zipfile
        import json
        
        with zipfile.ZipFile(epi_file, 'r') as zf:
            steps_content = zf.read("steps.jsonl").decode("utf-8")
            steps = [json.loads(line) for line in steps_content.strip().split("\n") if line]
        
        step_kinds = [s["kind"] for s in steps]
        # Should only have session.start, environment.captured, session.end
        assert "llm.request" not in step_kinds
        assert "llm.response" not in step_kinds


class TestWrapperClients:
    """Test wrapper client architecture."""
    
    def test_traced_openai_import(self):
        """TracedOpenAI should be importable from main package."""
        from epi_recorder import wrap_openai, TracedOpenAI
        assert wrap_openai is not None
        assert TracedOpenAI is not None
    
    def test_wrap_openai_creates_traced_client(self):
        """wrap_openai should wrap an OpenAI client."""
        from epi_recorder.wrappers import wrap_openai, TracedOpenAI
        
        # Create mock client
        mock_client = Mock()
        mock_client.chat = Mock()
        mock_client.chat.completions = Mock()
        
        wrapped = wrap_openai(mock_client)
        
        assert isinstance(wrapped, TracedOpenAI)
        assert hasattr(wrapped, "chat")
        assert hasattr(wrapped.chat, "completions")
    
    def test_traced_completions_logs_to_session(self, tmp_path):
        """TracedCompletions.create should log to active session."""
        from epi_recorder import record
        from epi_recorder.wrappers.openai import TracedCompletions
        
        epi_file = tmp_path / "test.epi"
        
        # Create mock completions object
        mock_completions = Mock()
        mock_response = Mock()
        mock_response.model = "gpt-4"
        mock_response.choices = [
            Mock(
                message=Mock(role="assistant", content="Test response"),
                finish_reason="stop"
            )
        ]
        mock_response.usage = Mock(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15
        )
        mock_completions.create.return_value = mock_response
        
        # Create traced wrapper
        traced = TracedCompletions(mock_completions)
        
        with record(str(epi_file)):
            result = traced.create(
                model="gpt-4",
                messages=[{"role": "user", "content": "Hello"}]
            )
        
        # Verify response was returned
        assert result == mock_response
        
        # Verify steps were logged
        import zipfile
        import json
        
        with zipfile.ZipFile(epi_file, 'r') as zf:
            steps_content = zf.read("steps.jsonl").decode("utf-8")
            steps = [json.loads(line) for line in steps_content.strip().split("\n") if line]
        
        step_kinds = [s["kind"] for s in steps]
        assert "llm.request" in step_kinds
        assert "llm.response" in step_kinds


class TestLegacyPatching:
    """Test deprecated legacy patching mode."""
    
    def test_legacy_patching_shows_deprecation_warning(self, tmp_path):
        """legacy_patching=True should emit deprecation warning."""
        from epi_recorder import record
        
        epi_file = tmp_path / "test.epi"
        
        with pytest.warns(DeprecationWarning, match="legacy_patching is deprecated"):
            with record(str(epi_file), legacy_patching=True):
                pass
        
        assert epi_file.exists()


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""
    
    def test_record_context_manager_still_works(self, tmp_path):
        """Basic record() usage should still work."""
        from epi_recorder import record
        
        epi_file = tmp_path / "test.epi"
        
        with record(str(epi_file), workflow_name="Test"):
            pass
        
        assert epi_file.exists()
    
    def test_log_step_still_works(self, tmp_path):
        """Manual log_step should still work."""
        from epi_recorder import record
        
        epi_file = tmp_path / "test.epi"
        
        with record(str(epi_file)) as epi:
            epi.log_step("custom.event", {"data": "test"})
        
        import zipfile
        import json
        
        with zipfile.ZipFile(epi_file, 'r') as zf:
            steps_content = zf.read("steps.jsonl").decode("utf-8")
            steps = [json.loads(line) for line in steps_content.strip().split("\n") if line]
        
        custom_steps = [s for s in steps if s["kind"] == "custom.event"]
        assert len(custom_steps) == 1
        assert custom_steps[0]["content"]["data"] == "test"
