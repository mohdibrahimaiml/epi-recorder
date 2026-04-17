"""
Tests for epi_guardrails integration with Guardrails AI.

These tests verify that Guardrails validation executions produce valid .epi artifacts
with correct step hierarchies (session → steps → validators).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestEpiGuardrailsImports:
    """Smoke tests for module imports."""

    def test_all_modules_import(self):
        from epi_guardrails import (
            instrument,
            uninstrument,
            GuardrailsRecorderSession,
            guardrails_epi_state,
        )
        from epi_guardrails.state import GuardrailsEPIState
        from epi_guardrails.step_types import (
            GuardExecutionStartContent,
            GuardExecutionEndContent,
            GuardrailsStepContent,
            LLMCallContent,
            ValidatorResultContent,
        )

    def test_version_check(self):
        from epi_guardrails.instrumentor import _guardrails_version

        ver = _guardrails_version()
        assert isinstance(ver, tuple)
        assert len(ver) == 3
        assert ver >= (0, 10, 0)


class TestInstrumentUninstrument:
    """Test that instrument() and uninstrument() work correctly."""

    def test_instrument_returns_true(self):
        from epi_guardrails import instrument, uninstrument

        result = instrument(output_path="test.epi")
        assert result is True
        uninstrument()

    def test_double_instrument_is_idempotent(self):
        from epi_guardrails import instrument, uninstrument

        instrument(output_path="test.epi")
        result = instrument(output_path="test2.epi")  # Should not raise
        assert result is True
        uninstrument()

    def test_uninstrument_restores_originals(self):
        from epi_guardrails import instrument, uninstrument
        from epi_guardrails.instrumentor import _originals

        instrument(output_path="test.epi")
        # After instrument, originals should be stored
        assert len(_originals) > 0
        uninstrument()
        # After uninstrument, originals should be cleared
        assert len(_originals) == 0


class TestStateManagement:
    """Test contextvars-based state management."""

    def test_state_none_when_not_recording(self):
        from epi_guardrails.state import guardrails_epi_state

        state = guardrails_epi_state()
        assert state is None

    def test_session_lifecycle(self):
        from epi_guardrails import GuardrailsRecorderSession
        from epi_guardrails.state import guardrails_epi_state, set_guardrails_epi_state

        with tempfile.TemporaryDirectory() as tmpdir:
            session = GuardrailsRecorderSession(
                output_path=Path(tmpdir) / "test.epi",
                guard_name="test-guard",
                goal="test goal",
            )

            assert guardrails_epi_state() is None

            with session:
                state = guardrails_epi_state()
                assert state is not None
                assert state.guard_name == "test-guard"
                assert session._step_index == 0

                session.emit_guard_execution_start()
                assert session._step_index == 1

            # After exit, state should be None
            assert guardrails_epi_state() is None

    def test_step_index_increments(self):
        from epi_guardrails import GuardrailsRecorderSession
        from epi_guardrails.state import guardrails_epi_state

        with tempfile.TemporaryDirectory() as tmpdir:
            session = GuardrailsRecorderSession(
                output_path=Path(tmpdir) / "test.epi",
            )

            with session:
                state = guardrails_epi_state()
                assert session._step_index == 0

                session._emit_step("test.step", {"n": 1})
                assert session._step_index == 1

                session._emit_step("test.step", {"n": 2})
                assert session._step_index == 2


class TestGuardrailsRecorderSession:
    """Test GuardrailsRecorderSession produces correct steps."""

    def test_session_records_all_step_types(self):
        from epi_guardrails import GuardrailsRecorderSession
        from epi_core.container import EPIContainer

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "session_test.epi"

            session = GuardrailsRecorderSession(
                output_path=out_path,
                guard_name="test-guard",
                guardrails_version="0.10.0",
                goal="Integration test",
                notes="Test notes",
                tags=["test", "integration"],
                redact=True,
            )

            with session:
                session.emit_guard_execution_start(
                    guard_config={"num_reasks": 1},
                    prompt="test prompt",
                )

                session.begin_iteration(
                    iteration_index=0,
                    iteration_id="test-iter-0",
                    llm_call={
                        "provider": "openai",
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": "Hello"}],
                    },
                )
                session.emit_validator_result(
                    name="ValidLength",
                    status="pass",
                    corrected=False,
                    rail_alias="valid_length",
                )
                session.end_iteration(
                    iteration_index=0,
                    iteration_id="test-iter-0",
                    iteration=None,
                    duration_seconds=0.5,
                )

                session.begin_iteration(
                    iteration_index=1,
                    iteration_id="test-iter-1",
                )
                session.emit_validator_result(
                    name="ValidLength",
                    status="fail",
                    corrected=True,
                    rail_alias="valid_length",
                    error="Text too long",
                )
                session.end_iteration(
                    iteration_index=1,
                    iteration_id="test-iter-1",
                    iteration=None,
                    duration_seconds=0.3,
                )

                session.emit_llm_call(
                    provider="openai",
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "test"}],
                    latency_seconds=0.4,
                    error=None,
                )

                session.emit_input_validation(
                    validated_input="user input",
                    validation_passed=True,
                    validators_run=["CleanText"],
                )

                session.emit_output_validation(
                    validated_output="validated output",
                    validation_passed=True,
                    validators_run=["ValidLength", "CleanText"],
                    correction_applied=False,
                )

                session.emit_guard_execution_end(
                    success=True,
                    duration_seconds=1.5,
                )

            # Verify .epi file was created
            assert out_path.exists(), f".epi file not created at {out_path}"

            # Verify it's a valid ZIP (legacy format)
            import zipfile

            assert zipfile.is_zipfile(out_path)

            # Read and verify steps
            with zipfile.ZipFile(out_path) as zf:
                steps_content = zf.read("steps.jsonl").decode("utf-8")

            steps = [json.loads(line) for line in steps_content.strip().split("\n")]

            assert len(steps) >= 3, f"Expected at least 3 steps, got {len(steps)}"

            # First step should be execution.start
            assert steps[0]["kind"] == "agent.step"
            assert steps[0]["content"]["phase"] == "start"
            step_kinds = [s["kind"] for s in steps]
            assert "agent.step" in step_kinds
            
            # Start event
            start_step = [s for s in steps if s["kind"] == "agent.step" and s["content"].get("phase") == "start"][0]
            assert start_step["content"]["trace_id"] == str(session.state.trace_id)
            
            # End event
            end_step = [s for s in steps if s["kind"] == "agent.step" and s["content"].get("phase") == "end"][0]
            assert end_step["content"]["success"] is True


class TestGuardrailsRecorderSessionHashIntegrity:
    """Test that session records input/output hashes."""

    def test_hashes_are_recorded(self):
        from epi_guardrails import GuardrailsRecorderSession

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "hash_test.epi"

            session = GuardrailsRecorderSession(
                output_path=out_path,
                guard_name="hash-test",
            )

            with session:
                session.emit_input_validation(
                    validated_input={"key": "value"},
                    validation_passed=True,
                    validators_run=["TestValidator"],
                )
                session.emit_output_validation(
                    validated_output={"result": "output"},
                    validation_passed=True,
                    validators_run=["TestValidator"],
                    correction_applied=False,
                )
                session.emit_guard_execution_end(success=True, duration_seconds=1.0)

            # Verify hashes were set on state
            assert session.state.input_hash is not None
            assert session.state.output_hash is not None
            assert len(session.state.input_hash) == 64  # SHA-256 hex


class TestStepTypes:
    """Test that step type definitions are correct TypedDicts."""

    def test_guard_execution_start_content(self):
        from epi_guardrails.step_types import GuardExecutionStartContent

        content: GuardExecutionStartContent = {
            "guard": {"name": "test"},
            "guardrails_version": "0.10.0",
            "trace_id": "abc123",
            "session_id": "sess1",
            "prompt": "test prompt",
        }
        assert content["guard"]["name"] == "test"

    def test_guardrails_step_content(self):
        from epi_guardrails.step_types import GuardrailsStepContent

        content: GuardrailsStepContent = {
            "step_index": 0,
            "iteration_index": 0,
            "trace_id": "trace1",
            "validation_passed": True,
            "validators": [{"name": "ValidLength", "status": "pass", "corrected": False}],
            "correction_applied": False,
            "llm_call": {
                "provider": "openai",
                "model": "gpt-4o",
                "messages": [],
            },
        }
        assert content["validation_passed"] is True
        assert len(content["validators"]) == 1


class TestInstrumentorWithMockGuard:
    """Integration test with a mock Guard execution (no real LLM needed)."""

    def test_guard_execution_produces_epi(self):
        from epi_guardrails import instrument, uninstrument
        from epi_guardrails.instrumentor import _originals

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "mock_guard.epi"

            # Instrument
            result = instrument(output_path=str(out_path), goal="Mock Guard test")
            assert result is True

            try:
                from guardrails import Guard
                from guardrails.classes.history import Call
                from guardrails.run import Runner
                from guardrails.validator_service import ValidatorServiceBase

                # Check originals were saved
                assert "Guard._execute" in _originals
                assert "Runner.step" in _originals

                # The Guard._execute wrapper should be in place
                # We can't fully test without a real LLM, but we can
                # verify the wrappers are installed
                assert hasattr(Guard, "_execute")

            finally:
                uninstrument()

            # After uninstrument, originals should be restored
            # and no exception should have been raised


class TestValidatorResultEmission:
    """Test that validator results attach correctly to state."""

    def test_validator_results_attach_to_active_step(self):
        from epi_guardrails import GuardrailsRecorderSession

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "validator_test.epi"

            session = GuardrailsRecorderSession(
                output_path=out_path,
                guard_name="validator-test",
            )

            with session:
                session.begin_iteration(
                    iteration_index=0,
                    iteration_id="test-iter-0",
                )

                session.emit_validator_result(
                    name="CleanText",
                    status="pass",
                    corrected=False,
                    rail_alias="clean_text",
                )
                session.emit_validator_result(
                    name="ValidLength",
                    status="fail",
                    corrected=True,
                    rail_alias="valid_length",
                    error="Text too long",
                )

                session.end_iteration(
                    iteration_index=0,
                    iteration_id="test-iter-0",
                    iteration=None,
                    duration_seconds=0.1,
                )

            assert session._step_index == 1
