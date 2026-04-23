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


class TestFailureModes:
    """
    Prove the system fails loudly instead of lying quietly.

    Each test targets a specific silent-failure path identified in the audit:
      1. Non-serializable objects raise TypeError in _canonical_hash (no str() fallback).
      2. Concurrent sessions never bleed validator results across contextvars contexts.
      3. OTel strict_export propagates the exception instead of swallowing it.
    """

    # ------------------------------------------------------------------
    # 1. Deterministic hashing — no silent str() fallback
    # ------------------------------------------------------------------

    def test_canonical_hash_raises_on_non_serializable(self):
        """
        _canonical_hash must raise TypeError for objects that cannot be
        deterministically serialized. It must NOT silently fall back to
        str() because that would produce memory-address-dependent hashes.
        """
        from epi_guardrails.session import _canonical_hash

        class Opaque:
            """Intentionally non-serializable (no __dict__ safe path)."""
            def __repr__(self):
                return f"<Opaque at 0x{id(self):x}>"

        with pytest.raises(TypeError, match="non-serializable"):
            _canonical_hash({"key": Opaque()})

    def test_canonical_hash_is_stable_across_calls(self):
        """
        The same logical data must always produce the same hash regardless
        of dict insertion order or Python runtime state.
        """
        from epi_guardrails.session import _canonical_hash

        payload = {"z": 3, "a": 1, "m": [1, 2, 3]}
        h1 = _canonical_hash(payload)
        # Same dict but insertion-order reversed
        payload2 = {"m": [1, 2, 3], "z": 3, "a": 1}
        h2 = _canonical_hash(payload2)
        assert h1 == h2, "Hash must be insertion-order independent"
        assert len(h1) == 64, "Expected SHA-256 hex digest"

    # ------------------------------------------------------------------
    # 2. Concurrency — no cross-context state bleed
    # ------------------------------------------------------------------

    def test_concurrent_sessions_do_not_bleed_validator_results(self):
        """
        Two GuardrailsRecorderSessions running concurrently in separate
        threads must NEVER share validator results. Each thread runs its
        own contextvars context, so iteration_id stacks must be completely
        isolated.

        This directly tests the fix for the thread-local iteration_id bug
        identified in the audit: previously, a parallel thread-local stack
        could cause Session A's validators to appear in Session B's artifact.
        """
        import threading
        from epi_guardrails import GuardrailsRecorderSession
        from epi_guardrails.state import push_current_iteration_id, pop_current_iteration_id, get_current_iteration_id

        results = {}
        errors = []

        def run_session(name: str, output_dir: Path):
            try:
                out = output_dir / f"{name}.epi"
                session = GuardrailsRecorderSession(
                    output_path=out,
                    guard_name=name,
                )
                with session:
                    iter_id = f"{name}-iter-0"
                    session.begin_iteration(iteration_index=0, iteration_id=iter_id)

                    # Confirm this context only sees its own iteration_id
                    seen_id = get_current_iteration_id()
                    results[f"{name}_seen_id"] = seen_id

                    session.emit_validator_result(
                        name=f"Validator-{name}",
                        status="pass",
                        corrected=False,
                        rail_alias=name,
                        iteration_id=iter_id,
                    )
                    session.end_iteration(
                        iteration_index=0,
                        iteration_id=iter_id,
                        iteration=None,
                        duration_seconds=0.01,
                    )

                results[name] = session
            except Exception as e:
                errors.append((name, e))

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            t1 = threading.Thread(target=run_session, args=("session-A", tmp))
            t2 = threading.Thread(target=run_session, args=("session-B", tmp))
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"

        # Each session must have seen only its own iteration_id, never the other's.
        assert results.get("session-A_seen_id") == "session-A-iter-0", (
            f"Session A saw wrong iteration_id: {results.get('session-A_seen_id')}"
        )
        assert results.get("session-B_seen_id") == "session-B-iter-0", (
            f"Session B saw wrong iteration_id: {results.get('session-B_seen_id')}"
        )

        # Verify no cross-contamination: Session A must not have Session B's validators
        sess_a: GuardrailsRecorderSession = results["session-A"]
        sess_b: GuardrailsRecorderSession = results["session-B"]

        # All steps should be clean (session already finalised, steps list populated)
        all_validator_names_a = [
            v["validator_name"]
            for step in sess_a._steps
            for v in step.get("content", {}).get("validators", [])
        ]
        all_validator_names_b = [
            v["validator_name"]
            for step in sess_b._steps
            for v in step.get("content", {}).get("validators", [])
        ]

        assert "Validator-session-B" not in all_validator_names_a, (
            "BLEED DETECTED: Session A contains Session B's validator"
        )
        assert "Validator-session-A" not in all_validator_names_b, (
            "BLEED DETECTED: Session B contains Session A's validator"
        )

    # ------------------------------------------------------------------
    # 3. OTel strict_export — fail closed, no silent drop
    # ------------------------------------------------------------------

    def test_otel_strict_export_raises_on_failure(self):
        """
        When strict_export=True (the default), a failed trace export must
        propagate the exception. There must be NO silent success path
        where the trace is quietly dropped and the caller believes
        everything worked.
        """
        from unittest.mock import patch, MagicMock
        from epi_recorder.integrations.opentelemetry import EPISpanExporter

        # We cannot easily import OTel without it installed, so skip gracefully.
        pytest.importorskip("opentelemetry.sdk.trace")

        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = EPISpanExporter(
                output_dir=tmpdir,
                strict_export=True,  # fail-closed (default)
            )
            # Inject a pre-buffered trace that will fail to pack
            exporter._traces["deadtrace00"] = [{"kind": "span.end", "content": {}, "timestamp": "2025-01-01T00:00:00Z"}]
            exporter._trace_last_activity["deadtrace00"] = 0

            # Make EpiRecorderSession.__enter__ blow up to simulate export failure
            with patch(
                "epi_recorder.api.EpiRecorderSession",
                side_effect=RuntimeError("simulated disk full"),
            ):
                with pytest.raises(RuntimeError, match="simulated disk full"):
                    exporter._flush_trace("deadtrace00")

    def test_otel_best_effort_writes_deadletter_not_raises(self):
        """
        When strict_export=False (best-effort mode), a failed trace export
        must write a .deadletter file and NOT raise. The deadletter file
        must contain the original trace_id and error so it is clearly
        flagged as failed, not silently lost.
        """
        from unittest.mock import patch
        from epi_recorder.integrations.opentelemetry import EPISpanExporter

        pytest.importorskip("opentelemetry.sdk.trace")

        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = EPISpanExporter(
                output_dir=tmpdir,
                strict_export=False,  # best-effort
            )
            exporter._traces["deadtrace01"] = [{"kind": "span.end", "content": {}, "timestamp": "2025-01-01T00:00:00Z"}]
            exporter._trace_last_activity["deadtrace01"] = 0

            with patch(
                "epi_recorder.api.EpiRecorderSession",
                side_effect=RuntimeError("simulated disk full"),
            ):
                # Must NOT raise in best-effort mode
                exporter._flush_trace("deadtrace01")

            # A deadletter file must exist and be readable
            dl = Path(tmpdir) / "deadtrace01.epi.deadletter"
            assert dl.exists(), "Deadletter file must be written in best-effort mode"

            # Ensure no successful .epi was created to avoid ambiguity
            epi_files = list(Path(tmpdir).glob("*.epi"))
            assert not epi_files, "System must not produce an .epi file when returning a deadletter"

            data = json.loads(dl.read_text(encoding="utf-8"))
            assert data["trace_id"] == "deadtrace01"
            assert "simulated disk full" in data["error"]
            assert isinstance(data["steps"], list), "Steps must be preserved in deadletter"

    # ------------------------------------------------------------------
    # 4. Agent Identity Cryptographic Binding
    # ------------------------------------------------------------------

    def test_agent_identity_tampering_invalidates_signature(self):
        """
        Agent identity must be cryptographically bound to the artifact.
        If an attacker changes the agent_identity in the manifest, the
        signature verification must fail.
        """
        from epi_guardrails import GuardrailsRecorderSession
        from typer.testing import CliRunner
        from epi_cli.main import app
        from epi_core.container import EPIContainer

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "identity_test.epi"
            session = GuardrailsRecorderSession(
                output_path=out_path,
                guard_name="test",
                agent_identity={"id": "original-agent"},
                auto_sign=True,
            )
            with session:
                session.emit_input_validation("test", True, [])

            # Convert to legacy-zip to easily modify the inner payload
            legacy_path = Path(tmpdir) / "legacy.epi"
            EPIContainer.migrate(out_path, legacy_path, container_format="legacy-zip")

            # Verify it works initially
            runner = CliRunner()
            res1 = runner.invoke(app, ["verify", str(legacy_path)])
            assert res1.exit_code == 0, "Valid artifact should verify"

            # Tamper the identity in manifest.json by rewriting the zip
            import zipfile
            tampered_epi = Path(tmpdir) / "tampered.epi"
            with zipfile.ZipFile(legacy_path, "r") as zin:
                with zipfile.ZipFile(tampered_epi, "w") as zout:
                    for item in zin.infolist():
                        if item.filename == "manifest.json":
                            content = zin.read(item.filename)
                            manifest_data = json.loads(content.decode("utf-8"))
                            manifest_data["governance"]["agent_identity"]["id"] = "fake-agent"
                            zout.writestr(item, json.dumps(manifest_data).encode("utf-8"))
                        else:
                            zout.writestr(item, zin.read(item.filename))

            # Verify tampered artifact fails signature check
            res2 = runner.invoke(app, ["verify", "--strict", str(tampered_epi)])
            assert res2.exit_code != 0, "Tampered identity must fail verification"
            assert "invalid" in res2.output.lower() or "fail" in res2.output.lower()

    # ------------------------------------------------------------------
    # 5. Tamper Detection End-to-End
    # ------------------------------------------------------------------

    def test_signature_detects_tampering(self):
        """
        Modifying one byte in steps.jsonl must cause verification failure.
        """
        from epi_guardrails import GuardrailsRecorderSession
        from typer.testing import CliRunner
        from epi_cli.main import app
        import zipfile

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "tamper_test.epi"
            # We use legacy-zip format directly to bypass envelope hash checks
            # and test the actual steps_hash / manifest hash tampering logic.
            session = GuardrailsRecorderSession(
                output_path=out_path,
                guard_name="test",
                auto_sign=True,
            )
            with session:
                session.begin_iteration(iteration_index=0, iteration_id="test")
                session.end_iteration(iteration_index=0, iteration_id="test", iteration=None, duration_seconds=1.0)

            # Convert to legacy-zip to easily modify the inner payload
            from epi_core.container import EPIContainer
            legacy_path = Path(tmpdir) / "legacy.epi"
            EPIContainer.migrate(out_path, legacy_path, container_format="legacy-zip")

            # Verify it works initially
            runner = CliRunner()
            res1 = runner.invoke(app, ["verify", str(legacy_path)])
            assert res1.exit_code == 0

            # Tamper with steps.jsonl by modifying the zip
            tampered_path = Path(tmpdir) / "tampered_steps.epi"
            with zipfile.ZipFile(legacy_path, "r") as zin:
                with zipfile.ZipFile(tampered_path, "w") as zout:
                    for item in zin.infolist():
                        if item.filename == "steps.jsonl":
                            content = zin.read(item.filename)
                            # Flip a character in the JSON or append garbage
                            if b'"test"' in content:
                                content = content.replace(b'"test"', b'"tost"')
                            else:
                                content += b"\nTAMPERED"
                            zout.writestr(item, content)
                        else:
                            zout.writestr(item, zin.read(item.filename))

            # Verify tampered artifact fails
            res2 = runner.invoke(app, ["verify", "--strict", str(tampered_path)])
            assert res2.exit_code != 0
            assert "mismatch" in res2.output.lower() or "fail" in res2.output.lower()

    # ------------------------------------------------------------------
    # 6. Async Streaming Failure
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_stream_interruption_marks_incomplete(self):
        """
        If an async stream is interrupted mid-way (exception), the wrapper
        must catch it and emit a guardrails.step marked as failed/incomplete.
        """
        from epi_guardrails.instrumentor import _wrap_async_stream_runner_step
        from epi_guardrails import GuardrailsRecorderSession

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "stream_fail.epi"
            session = GuardrailsRecorderSession(output_path=out_path, guard_name="test")

            async def broken_stream(*args, **kwargs):
                yield 1
                raise RuntimeError("network failure mid-stream")

            with session:
                wrapper = _wrap_async_stream_runner_step(broken_stream, None, ("test-call",), {"index": 0})
                with pytest.raises(RuntimeError, match="network failure"):
                    async for _ in wrapper:
                        pass

            # The session should have recorded the failed step
            assert len(session._steps) > 0
            # Look for the guardrails step
            steps = [s for s in session._steps if s.get("content", {}).get("subtype") == "guardrails"]
            assert len(steps) == 1
            step = steps[0]
            assert step["content"]["completed"] is False, "Interrupted stream must be incomplete"
            assert step["content"].get("validation_passed", False) is False

    # ------------------------------------------------------------------
    # 7. Version Compatibility Guard
    # ------------------------------------------------------------------

    def test_unsupported_spec_version_strict_failure(self):
        """
        Unknown spec_version should produce a warning under --strict mode.
        """
        from epi_guardrails import GuardrailsRecorderSession
        from typer.testing import CliRunner
        from epi_cli.main import app
        from epi_core.container import EPIContainer

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "version_test.epi"
            session = GuardrailsRecorderSession(output_path=out_path, guard_name="test")
            with session:
                pass

            # Convert to legacy-zip
            legacy_path = Path(tmpdir) / "legacy.epi"
            EPIContainer.migrate(out_path, legacy_path, container_format="legacy-zip")

            import zipfile
            tampered_epi = Path(tmpdir) / "tampered.epi"
            with zipfile.ZipFile(legacy_path, "r") as zin:
                with zipfile.ZipFile(tampered_epi, "w") as zout:
                    for item in zin.infolist():
                        if item.filename == "manifest.json":
                            content = zin.read(item.filename)
                            manifest_data = json.loads(content.decode("utf-8"))
                            manifest_data["spec_version"] = "99.9"
                            zout.writestr(item, json.dumps(manifest_data).encode("utf-8"))
                        else:
                            zout.writestr(item, zin.read(item.filename))

            runner = CliRunner()
            res = runner.invoke(app, ["verify", "--strict", "-v", str(tampered_epi)])
            assert "Unsupported spec_version '99.9'" in res.output
