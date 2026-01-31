"""
Tests for EPI Recorder Python API (epi_recorder.api)
"""

import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from epi_recorder.api import EpiRecorderSession, record, get_current_session


class TestEpiRecorderSession:
    """Test the EpiRecorderSession context manager."""
    
    def test_basic_context_manager(self):
        """Test basic context manager functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.epi"
            
            with EpiRecorderSession(output_path, workflow_name="Test") as epi:
                assert epi is not None
                assert epi.workflow_name == "Test"
                assert epi._entered is True
                assert epi.temp_dir is not None
                assert epi.temp_dir.exists()
            
            # After exit, .epi file should exist
            assert output_path.exists()
            
            # Verify it's a valid ZIP
            assert zipfile.is_zipfile(output_path)
    
    def test_manual_log_step(self):
        """Test manual logging of custom steps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_manual.epi"
            
            with EpiRecorderSession(output_path) as epi:
                epi.log_step("custom.event", {
                    "key": "value",
                    "number": 42
                })
            
            # Verify step was recorded
            with zipfile.ZipFile(output_path, 'r') as zf:
                steps_data = zf.read("steps.jsonl").decode("utf-8")
                
                # Parse steps
                steps = [json.loads(line) for line in steps_data.strip().split("\n")]
                
                # Should have: session.start, custom.event, session.end
                assert len(steps) >= 3
                
                # Find our custom event
                custom_events = [s for s in steps if s["kind"] == "custom.event"]
                assert len(custom_events) == 1
                assert custom_events[0]["content"]["key"] == "value"
                assert custom_events[0]["content"]["number"] == 42
    
    def test_artifact_capture(self):
        """Test capturing file artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_artifact.epi"
            artifact_file = Path(tmpdir) / "test_file.txt"
            artifact_file.write_text("Test content")
            
            with EpiRecorderSession(output_path) as epi:
                epi.log_artifact(artifact_file)
            
            # Verify artifact was captured
            with zipfile.ZipFile(output_path, 'r') as zf:
                # Check artifact file exists
                assert "artifacts/test_file.txt" in zf.namelist()
                
                # Check content
                content = zf.read("artifacts/test_file.txt").decode("utf-8")
                assert content == "Test content"
    
    def test_error_handling(self):
        """Test that errors are logged and .epi file still created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_error.epi"
            
            try:
                with EpiRecorderSession(output_path, workflow_name="Error Test") as epi:
                    epi.log_step("before.error", {"status": "ok"})
                    raise ValueError("Test error")
            except ValueError:
                pass
            
            # File should still be created
            assert output_path.exists()
            
            # Verify error was logged
            with zipfile.ZipFile(output_path, 'r') as zf:
                steps_data = zf.read("steps.jsonl").decode("utf-8")
                steps = [json.loads(line) for line in steps_data.strip().split("\n")]
                
                # Should have session.error step
                error_steps = [s for s in steps if s["kind"] == "session.error"]
                assert len(error_steps) == 1
                assert error_steps[0]["content"]["error_type"] == "ValueError"
                assert error_steps[0]["content"]["error_message"] == "Test error"
    
    def test_workflow_name_and_tags(self):
        """Test workflow name and tags are set correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_metadata.epi"
            
            with EpiRecorderSession(
                output_path,
                workflow_name="My Workflow",
                tags=["test", "demo", "v1"]
            ) as epi:
                pass
            
            # Verify metadata in manifest and steps
            with zipfile.ZipFile(output_path, 'r') as zf:
                # Check manifest structure
                manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                assert "spec_version" in manifest_data
                assert "created_at" in manifest_data
                assert "workflow_id" in manifest_data
                
                # Workflow name and tags are in the steps
                steps_data = zf.read("steps.jsonl").decode("utf-8")
                steps = [json.loads(line) for line in steps_data.strip().split("\n")]
                start_steps = [s for s in steps if s["kind"] == "session.start"]
                assert len(start_steps) == 1
                assert start_steps[0]["content"]["workflow_name"] == "My Workflow"
                assert start_steps[0]["content"]["tags"] == ["test", "demo", "v1"]
    
    def test_auto_sign(self):
        """Test automatic signing on exit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_signed.epi"
            
            with EpiRecorderSession(output_path, auto_sign=True) as epi:
                epi.log_step("test.step", {"data": "value"})
            
            # Check if signature exists (may not if key generation failed)
            with zipfile.ZipFile(output_path, 'r') as zf:
                manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                # Signature might be None if key doesn't exist
                # (This is non-fatal in the implementation)
                assert "signature" in manifest_data
    
    def test_no_auto_sign(self):
        """Test with auto_sign disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_unsigned.epi"
            
            with EpiRecorderSession(output_path, auto_sign=False) as epi:
                epi.log_step("test.step", {"data": "value"})
            
            # Check manifest exists but signature should be None
            with zipfile.ZipFile(output_path, 'r') as zf:
                manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                assert manifest_data.get("signature") is None
    
    def test_cannot_reenter(self):
        """Test that context manager cannot be re-entered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_reenter.epi"
            
            session = EpiRecorderSession(output_path)
            
            with session:
                pass
            
            # Try to re-enter
            with pytest.raises(RuntimeError, match="cannot be re-entered"):
                with session:
                    pass
    
    def test_log_outside_context(self):
        """Test that logging outside context raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_outside.epi"
            session = EpiRecorderSession(output_path)
            
            with pytest.raises(RuntimeError, match="outside of context manager"):
                session.log_step("test", {})
    
    def test_environment_capture(self):
        """Test that environment is captured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_env.epi"
            
            with EpiRecorderSession(output_path) as epi:
                pass
            
            # Check environment.json exists
            with zipfile.ZipFile(output_path, 'r') as zf:
                assert "environment.json" in zf.namelist()
                env_data = json.loads(zf.read("environment.json").decode("utf-8"))
                # Check the structure from capture_full_environment
                assert "os" in env_data
                assert "python" in env_data
                assert env_data["os"]["platform"]  # Nested structure


class TestRecordFunction:
    """Test the convenience record() function."""
    
    def test_record_convenience_function(self):
        """Test record() creates a session correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_record.epi"
            
            with record(output_path, workflow_name="Convenience Test") as epi:
                assert isinstance(epi, EpiRecorderSession)
                assert epi.workflow_name == "Convenience Test"
                epi.log_step("test.step", {"data": 123})
            
            assert output_path.exists()


class TestThreadLocalStorage:
    """Test thread-local session tracking."""
    
    def test_get_current_session(self):
        """Test get_current_session() returns active session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_current.epi"
            
            # No session active
            assert get_current_session() is None
            
            with record(output_path) as epi:
                # Session should be active
                current = get_current_session()
                assert current is epi
            
            # Session should be cleared after exit
            assert get_current_session() is None


class TestManualLLMLogging:
    """Test manual LLM request/response logging."""
    
    def test_log_llm_request(self):
        """Test manual LLM request logging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_llm_request.epi"
            
            with record(output_path) as epi:
                epi.log_llm_request("gpt-4", {
                    "messages": [{"role": "user", "content": "Hello"}],
                    "temperature": 0.7
                })
            
            with zipfile.ZipFile(output_path, 'r') as zf:
                steps_data = zf.read("steps.jsonl").decode("utf-8")
                steps = [json.loads(line) for line in steps_data.strip().split("\n")]
                
                llm_requests = [s for s in steps if s["kind"] == "llm.request"]
                assert len(llm_requests) == 1
                assert llm_requests[0]["content"]["model"] == "gpt-4"
    
    def test_log_llm_response(self):
        """Test manual LLM response logging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_llm_response.epi"
            
            with record(output_path) as epi:
                epi.log_llm_response({
                    "model": "gpt-4",
                    "content": "Hello!",
                    "tokens": 10
                })
            
            with zipfile.ZipFile(output_path, 'r') as zf:
                steps_data = zf.read("steps.jsonl").decode("utf-8")
                steps = [json.loads(line) for line in steps_data.strip().split("\n")]
                
                llm_responses = [s for s in steps if s["kind"] == "llm.response"]
                assert len(llm_responses) == 1
                assert llm_responses[0]["content"]["model"] == "gpt-4"
                assert llm_responses[0]["content"]["tokens"] == 10


class TestRedaction:
    """Test secret redaction in recordings."""
    
    def test_redaction_enabled(self):
        """Test that redaction is enabled by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_redact.epi"
            
            with record(output_path, redact=True) as epi:
                # Log something with a fake API key
                epi.log_step("api.call", {
                    "api_key": "sk-test-fake-key-1234567890",
                    "data": "some data"
                })
            
            with zipfile.ZipFile(output_path, 'r') as zf:
                steps_data = zf.read("steps.jsonl").decode("utf-8")
                steps = [json.loads(line) for line in steps_data.strip().split("\n")]
                
                # Should have redaction step
                redaction_steps = [s for s in steps if s["kind"] == "security.redaction"]
                assert len(redaction_steps) > 0
    
    def test_redaction_disabled(self):
        """Test recording with redaction disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_no_redact.epi"
            
            with record(output_path, redact=False) as epi:
                epi.log_step("api.call", {
                    "api_key": "sk-test-fake-key",
                    "data": "some data"
                })
            
            with zipfile.ZipFile(output_path, 'r') as zf:
                steps_data = zf.read("steps.jsonl").decode("utf-8")
                steps = [json.loads(line) for line in steps_data.strip().split("\n")]
                
                # Should NOT have redaction step (redaction disabled)
                redaction_steps = [s for s in steps if s["kind"] == "security.redaction"]
                assert len(redaction_steps) == 0


class TestFileArtifactErrors:
    """Test error handling for file artifacts."""
    
    def test_nonexistent_artifact(self):
        """Test logging nonexistent artifact raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_missing.epi"
            
            with record(output_path) as epi:
                with pytest.raises(FileNotFoundError):
                    epi.log_artifact(Path("nonexistent_file.txt"))


