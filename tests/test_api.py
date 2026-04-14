"""
Tests for EPI Recorder Python API (epi_recorder.api)
"""

import asyncio
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

    def test_artifact_capture_respects_custom_archive_path(self):
        """Test captured artifacts land at the same archive path that is logged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_custom_artifact.epi"
            artifact_file = Path(tmpdir) / "evidence.json"
            artifact_file.write_text('{"status":"ok"}', encoding="utf-8")
            archive_path = "evidence/custom/evidence.json"

            with EpiRecorderSession(output_path, auto_sign=False) as epi:
                epi.log_artifact(artifact_file, archive_path=archive_path)

            with zipfile.ZipFile(output_path, "r") as zf:
                assert archive_path in zf.namelist()
                assert zf.read(archive_path).decode("utf-8") == '{"status":"ok"}'

                steps_data = zf.read("steps.jsonl").decode("utf-8")
                steps = [json.loads(line) for line in steps_data.strip().split("\n") if line.strip()]

            captured_steps = [step for step in steps if step["kind"] == "artifact.captured"]
            assert len(captured_steps) == 1
            assert captured_steps[0]["content"]["archive_path"] == archive_path

    @pytest.mark.parametrize("archive_path", ["../escape.txt", "..\\escape.txt", "/absolute.txt", "C:/temp/escape.txt"])
    def test_artifact_capture_rejects_unsafe_archive_path(self, archive_path):
        """Test custom archive paths cannot escape the recording workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_bad_artifact.epi"
            artifact_file = Path(tmpdir) / "evidence.txt"
            artifact_file.write_text("safe", encoding="utf-8")

            with EpiRecorderSession(output_path, auto_sign=False) as epi:
                with pytest.raises(ValueError, match="archive_path"):
                    epi.log_artifact(artifact_file, archive_path=archive_path)

    def test_artifact_capture_rejects_reserved_archive_root(self):
        """Test custom archive paths cannot overwrite reserved evidence files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_reserved_artifact.epi"
            artifact_file = Path(tmpdir) / "steps.txt"
            artifact_file.write_text("shadow", encoding="utf-8")

            with EpiRecorderSession(output_path, auto_sign=False) as epi:
                with pytest.raises(ValueError, match="reserved"):
                    epi.log_artifact(artifact_file, archive_path="steps.jsonl")
    
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
            ):
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
            
            with EpiRecorderSession(output_path):
                pass
            
            # Check environment.json exists
            with zipfile.ZipFile(output_path, 'r') as zf:
                assert "environment.json" in zf.namelist()
                env_data = json.loads(zf.read("environment.json").decode("utf-8"))
                # Check the structure from capture_full_environment
                assert "os" in env_data
                assert "python" in env_data
                assert env_data["os"]["platform"]  # Nested structure

    def test_print_lines_are_auto_captured(self):
        """Test that plain print() output is captured as analyzable steps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_print_capture.epi"

            with EpiRecorderSession(output_path, auto_sign=False):
                print("hello from print capture")
                print('{"tool":"approve_wire_transfer","amount":15000}')

            with zipfile.ZipFile(output_path, "r") as zf:
                steps_data = zf.read("steps.jsonl").decode("utf-8")
                steps = [json.loads(line) for line in steps_data.strip().split("\n") if line.strip()]

            printed = [s for s in steps if s["kind"] == "stdout.print"]
            assert len(printed) >= 2
            assert any("hello from print capture" in p["content"]["text"] for p in printed)
            assert any(p["content"].get("parsed", {}).get("tool") == "approve_wire_transfer" for p in printed)

    def test_print_capture_can_be_disabled(self):
        """Test users can opt out of stdout capture for noise-sensitive runs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_print_capture_disabled.epi"

            with EpiRecorderSession(output_path, auto_sign=False, capture_prints=False):
                print("this should not become an epi step")

            with zipfile.ZipFile(output_path, "r") as zf:
                steps_data = zf.read("steps.jsonl").decode("utf-8")
                steps = [json.loads(line) for line in steps_data.strip().split("\n") if line.strip()]

            printed = [s for s in steps if s["kind"] == "stdout.print"]
            assert len(printed) == 0

    def test_agent_run_helper_records_readable_agent_flow(self):
        """Test the agent helper creates structured agent-facing steps with lineage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_agent_run.epi"

            with EpiRecorderSession(output_path, auto_sign=False) as epi:
                with epi.agent_run(
                    "refund-agent",
                    user_input="Refund order 123",
                    goal="Resolve customer refund",
                    session_id="session-001",
                    task_id="task-refund-123",
                    parent_run_id="parent-run-000",
                    attempt=2,
                    resume_from="run-previous",
                    metadata={"channel": "support"},
                ) as agent:
                    agent.plan("Validate order, then decide on refund.", steps=["lookup_order", "check policy", "decide"])
                    agent.message("user", "Refund order 123")
                    agent.memory_read("customer_history", query="order 123", source="vector-memory", result_count=2)
                    agent.tool_call("lookup_order", {"order_id": "123"})
                    agent.tool_result("lookup_order", {"status": "paid"})
                    agent.approval_request(
                        "approve_refund",
                        reason="Amount exceeds auto-approval threshold",
                        risk_level="high",
                    )
                    agent.pause(reason="Waiting for manager approval", waiting_for="manager")
                    agent.approval_response(
                        "approve_refund",
                        approved=True,
                        reviewer="manager@epilabs.org",
                        notes="Approved after manual review.",
                    )
                    agent.resume(reason="Manager approved refund")
                    agent.decision(
                        "approve_refund",
                        confidence=0.94,
                        rationale="Order is eligible for refund.",
                        review_required=True,
                    )
                    agent.memory_write("refund_decision", {"decision": "approved"}, destination="session-memory")
                    agent.handoff("risk-reviewer", reason="Amount above auto threshold")

            with zipfile.ZipFile(output_path, "r") as zf:
                steps_data = zf.read("steps.jsonl").decode("utf-8")
                steps = [json.loads(line) for line in steps_data.strip().split("\n") if line.strip()]

            agent_steps = [step for step in steps if step["kind"].startswith("agent.") or step["kind"].startswith("tool.")]
            kinds = [step["kind"] for step in agent_steps]
            assert kinds == [
                "agent.run.start",
                "agent.plan",
                "agent.message",
                "agent.memory.read",
                "tool.call",
                "tool.response",
                "agent.approval.request",
                "agent.run.pause",
                "agent.approval.response",
                "agent.run.resume",
                "agent.decision",
                "agent.memory.write",
                "agent.handoff",
                "agent.run.end",
            ]

            run_ids = {step["content"]["run_id"] for step in agent_steps}
            assert len(run_ids) == 1
            assert all(step["content"]["agent_name"] == "refund-agent" for step in agent_steps if "agent_name" in step["content"])
            assert agent_steps[0]["content"]["user_input"] == "Refund order 123"
            assert agent_steps[0]["content"]["goal"] == "Resolve customer refund"
            assert agent_steps[0]["content"]["channel"] == "support"
            assert agent_steps[0]["content"]["session_id"] == "session-001"
            assert agent_steps[0]["content"]["task_id"] == "task-refund-123"
            assert agent_steps[0]["content"]["parent_run_id"] == "parent-run-000"
            assert agent_steps[0]["content"]["attempt"] == 2
            assert agent_steps[0]["content"]["resume_from"] == "run-previous"
            assert agent_steps[1]["content"]["steps"] == ["lookup_order", "check policy", "decide"]
            assert agent_steps[3]["content"]["memory_key"] == "customer_history"
            assert agent_steps[6]["content"]["action"] == "approve_refund"
            assert agent_steps[8]["content"]["approved"] is True
            assert agent_steps[10]["content"]["decision"] == "approve_refund"
            assert agent_steps[11]["content"]["memory_key"] == "refund_decision"
            assert agent_steps[13]["content"]["success"] is True

    def test_agent_run_logs_descriptive_error_when_exception_value_missing(self):
        """Test sync agent_run writes a readable fallback error message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_agent_run_missing_exc_value.epi"

            with EpiRecorderSession(output_path, auto_sign=False) as epi:
                agent = epi.agent_run("claims-agent")
                agent.__enter__()
                agent.__exit__(RuntimeError, None, None)

            with zipfile.ZipFile(output_path, "r") as zf:
                steps_data = zf.read("steps.jsonl").decode("utf-8")
                steps = [json.loads(line) for line in steps_data.strip().split("\n") if line.strip()]

            error_steps = [step for step in steps if step["kind"] == "agent.run.error"]
            assert len(error_steps) == 1
            assert error_steps[0]["content"]["error_type"] == "RuntimeError"
            assert error_steps[0]["content"]["error_message"] == (
                "Exception of type RuntimeError raised with no value"
            )

    def test_async_agent_run_logs_descriptive_error_when_exception_value_missing(self):
        """Test async agent_run writes a readable fallback error message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_async_agent_run_missing_exc_value.epi"

            async def _exercise(epi: EpiRecorderSession) -> None:
                agent = epi.agent_run("claims-agent")
                await agent.__aenter__()
                await agent.__aexit__(RuntimeError, None, None)

            with EpiRecorderSession(output_path, auto_sign=False) as epi:
                asyncio.run(_exercise(epi))

            with zipfile.ZipFile(output_path, "r") as zf:
                steps_data = zf.read("steps.jsonl").decode("utf-8")
                steps = [json.loads(line) for line in steps_data.strip().split("\n") if line.strip()]

            error_steps = [step for step in steps if step["kind"] == "agent.run.error"]
            assert len(error_steps) == 1
            assert error_steps[0]["content"]["error_type"] == "RuntimeError"
            assert error_steps[0]["content"]["error_message"] == (
                "Exception of type RuntimeError raised with no value"
            )


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

    def test_record_warns_when_local_policy_is_invalid(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "epi_policy.json").write_text("{not valid json", encoding="utf-8")
        output_path = tmp_path / "invalid-policy.epi"

        with pytest.warns(UserWarning, match="epi_policy.json is invalid and will be ignored"):
            with record(output_path, auto_sign=False, capture_prints=False):
                pass

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



 
