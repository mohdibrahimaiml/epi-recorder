"""
Simple functional tests for bootstrap module
"""
import io
import json
from unittest.mock import patch
from epi_recorder.bootstrap import initialize_recording, _finalize_bootstrap_recording, _restore_stdio_capture
from epi_recorder.api import get_current_session
from epi_recorder.patcher import RecordingContext, set_recording_context


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
        _restore_stdio_capture()
    
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
        _restore_stdio_capture()

    def test_initialize_recording_captures_stdout_prints(self, tmp_path, monkeypatch):
        steps_dir = tmp_path / "steps"
        steps_dir.mkdir()

        monkeypatch.setenv('EPI_RECORD', '1')
        monkeypatch.setenv('EPI_STEPS_DIR', str(steps_dir))
        monkeypatch.setenv('EPI_CAPTURE_PRINTS', '1')
        _restore_stdio_capture()

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch('sys.stdout', stdout), patch('sys.stderr', stderr):
            initialize_recording()
            print("hello from bootstrap")
            _finalize_bootstrap_recording()

        steps_path = steps_dir / "steps.jsonl"
        assert steps_path.exists()
        lines = [json.loads(line) for line in steps_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert any(step["kind"] == "stdout.print" for step in lines)
        assert any(step["content"].get("text") == "hello from bootstrap" for step in lines)
        set_recording_context(None)
        _restore_stdio_capture()


class TestBootstrapSessionProxy:
    def test_get_current_session_returns_proxy_in_bootstrap_mode(self, tmp_path):
        steps_dir = tmp_path / "steps"
        steps_dir.mkdir()

        context = RecordingContext(steps_dir, enable_redaction=False)
        try:
            set_recording_context(context)
            session = get_current_session()
            assert session is not None
            session.log_step("custom.event", {"value": 1})
            context.finalize()

            steps_path = steps_dir / "steps.jsonl"
            assert steps_path.exists()
            payload = steps_path.read_text(encoding="utf-8")
            assert "custom.event" in payload
        finally:
            set_recording_context(None)

    def test_bootstrap_proxy_supports_agent_run_helper(self, tmp_path):
        steps_dir = tmp_path / "steps"
        steps_dir.mkdir()

        context = RecordingContext(steps_dir, enable_redaction=False)
        try:
            set_recording_context(context)
            session = get_current_session()
            assert session is not None

            with session.agent_run(
                "ops-agent",
                user_input="Check order 77",
                session_id="bootstrap-session",
                task_id="bootstrap-task",
                attempt=3,
                resume_from="prev-bootstrap-run",
            ) as agent:
                agent.plan("Check order history before deciding")
                agent.message("user", "Check order 77")
                agent.memory_read("order_history", query="77", result_count=1)
                agent.tool_call("lookup_order", {"order_id": "77"})
                agent.tool_result("lookup_order", {"status": "paid"})
                agent.approval_request("approve_refund", reason="High-value refund", risk_level="high")
                agent.approval_response("approve_refund", approved=True, reviewer="manager@example.com")
                agent.decision("approve_refund", confidence=0.88)
                agent.memory_write("refund_decision", {"approved": True})

            context.finalize()

            steps_path = steps_dir / "steps.jsonl"
            assert steps_path.exists()
            steps = [
                json.loads(line)
                for line in steps_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            kinds = [step["kind"] for step in steps]
            assert "agent.run.start" in kinds
            assert "agent.plan" in kinds
            assert "agent.message" in kinds
            assert "agent.memory.read" in kinds
            assert "tool.call" in kinds
            assert "tool.response" in kinds
            assert "agent.approval.request" in kinds
            assert "agent.approval.response" in kinds
            assert "agent.decision" in kinds
            assert "agent.memory.write" in kinds
            assert "agent.run.end" in kinds

            start = next(step for step in steps if step["kind"] == "agent.run.start")
            assert start["content"]["session_id"] == "bootstrap-session"
            assert start["content"]["task_id"] == "bootstrap-task"
            assert start["content"]["attempt"] == 3
            assert start["content"]["resume_from"] == "prev-bootstrap-run"
        finally:
            set_recording_context(None)

    def test_get_current_session_none_without_bootstrap_context(self):
        set_recording_context(None)
        assert get_current_session() is None



 
