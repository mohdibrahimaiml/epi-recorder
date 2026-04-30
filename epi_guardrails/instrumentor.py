"""
epi_guardrails.instrumentor — Guardrails AI 0.10.x → EPI recording.

Hooks (no source modification):
  1. Runner.step              → begin_iteration/end_iteration pair with explicit step_id
  2. StreamRunner.step        → final output only (streaming)
  3. ValidatorServiceBase.after_run_validator → attach validator to _step_records

Key invariants:
  - ONE .epi per Guard execution
  - Step → validator linkage via explicit iteration_id → step_id mapping (UUID-based)
  - No global mutable state (contextvars + thread-local only)
  - Streaming: only final validation state captured
  - Ordering: event_index monotonic counter per session
  - Correction tracking: original_output_hash, corrected_output_hash per step
  - Recorder lifecycle: exactly-once start/end enforced
"""

from __future__ import annotations

import logging
import time as time_module
from importlib import import_module
from typing import Any, Callable, Optional, TYPE_CHECKING

try:
    from wrapt import wrap_function_wrapper

    _HAS_WRAPT = True
except ImportError:
    _HAS_WRAPT = False

from epi_guardrails.session import GuardrailsRecorderSession
from epi_guardrails.state import (
    guardrails_epi_state,
    get_current_iteration_id,
    pop_current_iteration_id,
    push_current_iteration_id,
    set_guardrails_epi_state,
    push_iteration_id,
    pop_iteration_id,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

_GUARD_MODULE = "guardrails.guard"
_RUNNER_MODULE = "guardrails.run"
_VALIDATOR_MODULE = "guardrails.validator_service"

# Stored originals for uninstrument()
_originals: dict[str, Any] = {}

# Instrumentation settings (set by instrument())
_settings: dict[str, Any] = {}


# ==============================================================================
# Version
# ==============================================================================


def _guardrails_version() -> tuple:
    """Detect Guardrails AI version robustly using importlib.metadata."""
    try:
        from importlib.metadata import version
        v_str = version("guardrails-ai")
        parts = v_str.split(".")[:3]
        return tuple(int(p) for p in parts)
    except Exception:
        try:
            from guardrails.version import GUARDRAILS_VERSION
            parts = GUARDRAILS_VERSION.split(".")[:3]
            return tuple(int(p) for p in parts)
        except Exception:
            return (0, 0, 0)


def _safe_get(
    wrapped: Callable,
    args: tuple,
    kwargs: dict,
    param_name: str,
    default: Any = None,
) -> Any:
    """Extract a parameter value from args/kwargs using signature inspection.

    Falls back to kwargs, then positional index from inspect.signature,
    then the provided default. This survives Guardrails signature changes.
    """
    if param_name in kwargs:
        return kwargs[param_name]
    try:
        import inspect

        sig = inspect.signature(wrapped)
        for idx, (name, param) in enumerate(sig.parameters.items()):
            if name == param_name:
                if idx < len(args):
                    return args[idx]
                if param.default is not inspect.Parameter.empty:
                    return param.default
                return default
    except (ValueError, TypeError):
        pass
    return default


# ==============================================================================
# Runner.step wrapper — non-streaming iteration step
# ==============================================================================


def _wrap_runner_step(
    wrapped: Callable,
    instance: Any,
    args: tuple,
    kwargs: dict,
) -> Any:
    """
    Wrap Runner.step.

    Guardrails 0.10.0: step(index, output_schema, call_log, api=..., messages=...,
                          prompt_params=..., output=...) → Iteration

    Lifecycle per step:
      1. begin_iteration: push iteration_id, set _active_step
      2. Call original Runner.step
         → Inside: validators call after_run_validator → emit_validator_result
           → each validator attaches to current _active_step via context stack
      3. end_iteration: emit complete guardrails.step (validators from _active_step)
      4. pop iteration_id (guaranteed, even if end_iteration raises)

    Strict step→validator linkage:
      - begin_iteration creates GuardrailsStepRecord with unique iteration_id
      - _active_step is set so validators attach only to this step
      - end_iteration verifies iteration_id match before emitting
    """
    state = guardrails_epi_state()
    if state is None or not hasattr(state, "guard_name"):
        return wrapped(*args, **kwargs)

    call_log = _safe_get(wrapped, args, kwargs, "call_log", default=None)
    step_index_arg = _safe_get(wrapped, args, kwargs, "index", default=0)

    iteration_id = None
    if call_log is not None:
        call_id = getattr(call_log, "id", None) or str(id(call_log))
        iteration_id = f"{call_id}-step-{step_index_arg}"

    if not iteration_id:
        return wrapped(*args, **kwargs)

    session = _find_session(state)
    if session is None:
        return wrapped(*args, **kwargs)

    step_start_time = time_module.monotonic()

    session.begin_iteration(
        iteration_index=step_index_arg or 0,
        iteration_id=iteration_id,
    )

    result = None
    try:
        result = wrapped(*args, **kwargs)
        return result
    finally:
        duration = time_module.monotonic() - step_start_time

        try:
            session.end_iteration(
                iteration_index=step_index_arg or 0,
                iteration_id=iteration_id,
                iteration=result,
                duration_seconds=round(duration, 4),
            )
        finally:
            pop_current_iteration_id()


def _hash_val(value: Any) -> Optional[str]:
    """Compute SHA-256 hash of a value using canonical normalization."""
    from epi_guardrails.session import _canonical_hash
    if value is None:
        return None
    try:
        return _canonical_hash(value)
    except TypeError:
        # Value is not canonically serializable (e.g. raw Guardrails object).
        # Log at debug level — this is expected for opaque types.
        logger.debug("_hash_val: skipping non-serializable type %s", type(value).__name__)
        return None


# ==============================================================================
# StreamRunner.step wrapper — streaming iteration
# ==============================================================================


def _wrap_stream_runner_step(
    wrapped: Callable,
    instance: Any,
    args: tuple,
    kwargs: dict,
) -> Any:
    """
    Wrap StreamRunner.step for streaming LLM responses.

    Guardrails 0.10.0: step(...) → Iterator[ValidationOutcome]

    Streaming validators do NOT call after_run_validator, so we cannot attach
    per-validator results. Instead, we emit the step with the final aggregated
    validation state when the stream completes.

    We wrap the returned iterator to:
      1. Capture the final ValidationOutcome
      2. Emit guardrails.step with final output + aggregated validator info
    """
    state = guardrails_epi_state()
    if state is None or not hasattr(state, "guard_name"):
        return wrapped(*args, **kwargs)

    call_log = _safe_get(wrapped, args, kwargs, "call_log", default=None)
    step_index = _safe_get(wrapped, args, kwargs, "index", default=0)
    iteration_id = (
        f"{getattr(call_log, 'id', id(call_log) if call_log else 'stream')}-step-{step_index}"
    )

    step_start_time = time_module.monotonic()

    try:
        push_current_iteration_id(iteration_id)
        result_iter = wrapped(*args, **kwargs)
        return _StreamingIterationWrapper(
            result_iter,
            state=state,
            iteration_id=iteration_id,
            iteration_index=step_index or 0,
            step_start_time=step_start_time,
        )

    except Exception as e:
        duration = time_module.monotonic() - step_start_time
        if iteration_id:
            pop_current_iteration_id()
        session = _find_session(state)
        if session:
            session.emit_guardrails_step(
                iteration_index=step_index or 0,
                iteration_id=iteration_id,
                validation_passed=False,
                validators=[],
                correction_applied=False,
                duration_seconds=round(duration, 4),
                completed=False,
            )
        raise


class _StreamingIterationWrapper:
    """
    Wraps the Iterator[ValidationOutcome] returned by StreamRunner.step.

    On first iteration: capture the first ValidationOutcome
    On exhaustion: emit the guardrails.step with final state
    """

    def __init__(
        self,
        inner: Any,
        state: Any,
        iteration_id: str,
        iteration_index: int,
        step_start_time: float,
    ):
        self._inner = inner
        self._state = state
        self._iteration_id = iteration_id
        self._iteration_index = iteration_index
        self._step_start_time = step_start_time
        self._consumed = False
        self._final_outcome = None

    def __iter__(self):
        return self

    def __next__(self):
        try:
            item = next(self._inner)
            self._final_outcome = item
            return item
        except StopIteration:
            self._consumed = True
            duration = time_module.monotonic() - self._step_start_time
            pop_current_iteration_id()
            self._emit_streaming_step(duration)
            raise

    def close(self) -> None:
        """Ensure cleanup on early break or GeneratorExit."""
        if not self._consumed:
            self._consumed = True
            try:
                pop_current_iteration_id()
                duration = time_module.monotonic() - self._step_start_time
                self._emit_streaming_step(duration)
            except Exception as exc:
                logger.warning("epi_guardrails: streaming cleanup failed: %s", exc)
            if hasattr(self._inner, "close"):
                try:
                    self._inner.close()
                except Exception as exc:
                    logger.warning("epi_guardrails: inner iterator close failed: %s", exc)

    def __del__(self):
        """Last-resort cleanup if close() was not called."""
        if not getattr(self, "_consumed", False):
            try:
                pop_current_iteration_id()
                duration = time_module.monotonic() - self._step_start_time
                self._emit_streaming_step(duration)
            except Exception:
                pass

    def _emit_streaming_step(self, duration: float) -> None:
        """Emit guardrails.step for streaming after iterator is exhausted."""
        session = _find_session(self._state)
        if session is None:
            return

        validated_output = None
        validation_passed = True
        correction_applied = False
        guarded_output = None

        if self._final_outcome is not None:
            try:
                guarded_output = str(getattr(self._final_outcome, "guarded_output", "") or "")[
                    :2000
                ]
                validated_output = str(getattr(self._final_outcome, "validated_output", "") or "")[
                    :2000
                ]

                if guarded_output != validated_output:
                    correction_applied = True

                validation_passed = getattr(self._final_outcome, "validation_passed", True)
            except (AttributeError, TypeError) as exc:
                logger.warning(
                    "epi_guardrails: could not read streaming outcome fields: %s", exc
                )

        session.emit_guardrails_step(
            iteration_index=self._iteration_index,
            iteration_id=self._iteration_id,
            validated_output=validated_output,
            guarded_output=guarded_output,
            validation_passed=validation_passed,
            correction_applied=correction_applied,
            validators=[],  # Streaming validators don't call after_run_validator
            duration_seconds=round(duration, 4),
            completed=self._consumed,
        )


# ==============================================================================
# ValidatorServiceBase.after_run_validator wrapper
# ==============================================================================


def _wrap_validator_after_run(
    wrapped: Callable,
    instance: Any,
    args: tuple,
    kwargs: dict,
) -> Any:
    """
    Wrap ValidatorServiceBase.after_run_validator.

    Guardrails 0.10.0: after_run_validator(validator, validator_logs, result)
                       → ValidatorLogs

    This is called after each individual validator runs, for BOTH sync and
    streaming validators. It is the correct hook point because it receives the
    FINAL validator result (not intermediate fragments).

    We emit a guardrails.validator.result event and attach it to the current
    iteration step via the iteration_id context stack.

    NOTE: For streaming validators in run_validators_stream_fix, after_run_validator
    IS called (via run_validator → run_validator_sync → after_run_validator).
    So this hook captures BOTH sync and streaming validator results.
    """
    state = guardrails_epi_state()
    if state is None or not hasattr(state, "guard_name"):
        return wrapped(*args, **kwargs)

    session = _find_session(state)
    if session is None:
        return wrapped(*args, **kwargs)

    # Extract validator + logs + result
    validator = _safe_get(wrapped, args, kwargs, "validator", default=None)
    validator_logs = _safe_get(wrapped, args, kwargs, "validator_logs", default=None)
    result = _safe_get(wrapped, args, kwargs, "result", default=None)

    validator_name = getattr(validator, "rail_alias", "unknown") if validator else "unknown"
    rail_alias = getattr(validator, "on_fail_descriptor", "unknown") if validator else "unknown"

    # Call original first to get the final result
    try:
        logs_out = wrapped(*args, **kwargs)
    except Exception as e:
        # Record as error
        session.emit_validator_result(
            name=validator_name,
            status="error",
            corrected=False,
            rail_alias=rail_alias,
            error=f"{type(e).__name__}: {e}",
            iteration_id=get_current_iteration_id(),
        )
        raise

    # Extract result info
    status = "pass"
    corrected = False
    error_msg = None
    value = None
    parsed = None
    original_hash = None
    corrected_hash = None

    try:
        if result is not None:
            from guardrails_ai.types.validation_result import Outcome

            outcome = getattr(result, "outcome", None)
            if outcome == Outcome.PASS:
                status = "pass"
            elif outcome == Outcome.FAIL:
                status = "fail"

            # Check for correction
            try:
                corrected = bool(getattr(result, "corrected", False))
            except (AttributeError, TypeError) as exc:
                logger.warning(
                    "epi_guardrails: validator=%s could not read 'corrected' field: %s",
                    validator_name, exc,
                )
                corrected = False

            # Get fix_value (corrected output)
            try:
                fix_val = getattr(result, "fix_value", None)
                if fix_val is not None:
                    corrected = True
                    corrected_hash = _hash_val(fix_val)
            except (AttributeError, TypeError) as exc:
                logger.warning(
                    "epi_guardrails: validator=%s could not read 'fix_value' field: %s",
                    validator_name, exc,
                )

            if getattr(result, "error", None):
                try:
                    error_msg = str(getattr(result, "error", ""))
                    if error_msg:
                        status = "error"
                except (AttributeError, TypeError) as exc:
                    logger.warning(
                        "epi_guardrails: validator=%s could not read 'error' field: %s",
                        validator_name, exc,
                    )

            value = getattr(result, "value", None)
            parsed = getattr(result, "parsed_output", None)

    except Exception as exc:
        # Unexpected schema change — surface it so integration drift is visible.
        logger.warning(
            "epi_guardrails: validator=%s unexpected result schema, some fields may be missing: %s",
            validator_name, exc,
        )

    # Get value_before_validation and value_after_validation from logs
    if validator_logs is not None:
        try:
            vbv = getattr(validator_logs, "value_before_validation", None)
            vav = getattr(validator_logs, "value_after_validation", None)
            if original_hash is None:
                original_hash = _hash_val(vbv)
            if corrected_hash is None and vav != vbv:
                corrected_hash = _hash_val(vav)
        except (AttributeError, TypeError) as exc:
            logger.warning(
                "epi_guardrails: validator=%s could not read logs values: %s",
                validator_name, exc,
            )

    # Get iteration_id from context stack
    iteration_id = get_current_iteration_id()

    session.emit_validator_result(
        name=validator_name,
        status=status,
        corrected=corrected,
        rail_alias=rail_alias,
        value=value,
        parsed=parsed,
        error=error_msg,
        original_value_hash=original_hash,
        corrected_value_hash=corrected_hash,
        iteration_id=iteration_id,
    )

    return logs_out


# ==============================================================================
# Runner.call wrapper — LLM interactions
# ==============================================================================


def _wrap_runner_call(
    wrapped: Callable,
    instance: Any,
    args: tuple,
    kwargs: dict,
) -> Any:
    """
    Wrap Runner.call (or AsyncRunner.async_call).

    Captures raw LLM metadata (provider, model, messages, usage, latency).
    """
    state = guardrails_epi_state()
    if state is None:
        return wrapped(*args, **kwargs)

    session = _find_session(state)
    if session is None:
        return wrapped(*args, **kwargs)

    start_time = time_module.monotonic()
    result = None
    error = None

    try:
        result = wrapped(*args, **kwargs)
        return result
    except Exception as e:
        error = str(e)
        raise
    finally:
        latency = time_module.monotonic() - start_time

        # Extract info from result (LLMResponse)
        provider = "unknown"
        model = "unknown"
        messages = []
        usage = None
        choices = None
        system = None

        if result is not None:
            try:
                # result is an LLMResponse
                provider = getattr(result, "provider", "unknown")
                model = getattr(result, "model_id", "unknown")
                usage_obj = getattr(result, "usage", None)
                if usage_obj:
                    try:
                        usage = {
                            "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0),
                            "completion_tokens": getattr(usage_obj, "completion_tokens", 0),
                            "total_tokens": getattr(usage_obj, "total_tokens", 0),
                        }
                    except (AttributeError, TypeError) as exc:
                        logger.warning(
                            "epi_guardrails: could not read LLM usage object: %s", exc
                        )

                output = getattr(result, "output", None)
                if output:
                    choices = [{"message": {"content": str(output)}}]
            except (AttributeError, TypeError) as exc:
                logger.warning(
                    "epi_guardrails: could not extract LLM call metadata: %s", exc
                )

        session.emit_llm_call(
            provider=provider,
            model=model,
            messages=[], # Captured via step if needed, or extracted from call args
            choices=choices,
            usage=usage,
            latency_seconds=round(latency, 4),
            error=error,
            step_id=get_current_iteration_id(),
        )


async def _wrap_async_runner_call(
    wrapped: Callable,
    instance: Any,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Async variant of Runner.call wrapper."""
    state = guardrails_epi_state()
    if state is None:
        return await wrapped(*args, **kwargs)

    session = _find_session(state)
    if session is None:
        return await wrapped(*args, **kwargs)

    start_time = time_module.monotonic()
    result = None
    error = None

    try:
        result = await wrapped(*args, **kwargs)
        return result
    except Exception as e:
        error = str(e)
        raise
    finally:
        latency = time_module.monotonic() - start_time
        # Simplified async capture similar to sync
        session.emit_llm_call(
            provider="async_provider",
            model="async_model",
            messages=[],
            latency_seconds=round(latency, 4),
            error=error,
            step_id=get_current_iteration_id(),
        )


# ==============================================================================
# AsyncStreamRunner.async_step wrapper — async streaming iteration
# ==============================================================================


async def _wrap_async_stream_runner_step(
    wrapped: Callable,
    instance: Any,
    args: tuple,
    kwargs: dict,
) -> Any:
    """
    Wrap AsyncStreamRunner.async_step (or AsyncRunner.async_step).

    Emits a guardrails.step on exhaustion or exception so async streaming
    evidence is never silently dropped. The exact method name is detected
    dynamically at instrument() time, so this wrapper survives version drift.
    """
    state = guardrails_epi_state()
    if state is None or not hasattr(state, "guard_name"):
        async for item in wrapped(*args, **kwargs):
            yield item
        return

    call_log = _safe_get(wrapped, args, kwargs, "call_log", default=None)
    step_index = _safe_get(wrapped, args, kwargs, "index", default=0)
    iteration_id = (
        f"{getattr(call_log, 'id', id(call_log) if call_log else 'async-stream')}-step-{step_index}"
    )

    step_start_time = time_module.monotonic()
    _errored = False

    try:
        push_current_iteration_id(iteration_id)
        async for item in wrapped(*args, **kwargs):
            yield item
    except Exception:
        _errored = True
        raise
    finally:
        duration = time_module.monotonic() - step_start_time
        pop_current_iteration_id()
        session = _find_session(state)
        if session:
            session.emit_guardrails_step(
                iteration_index=step_index or 0,
                iteration_id=iteration_id,
                validation_passed=not _errored,
                validators=[],
                correction_applied=False,
                duration_seconds=round(duration, 4),
                completed=not _errored,
            )


# ==============================================================================
# Guard._execute wrapper — session lifecycle
# ==============================================================================



def _wrap_guard_execute(
    wrapped: Callable,
    self: Any,
    args: tuple,
    kwargs: dict,
) -> Any:
    """
    Wrap Guard._execute to create + finalize GuardrailsRecorderSession.

    Creates session at entry (sets up contextvars state).
    Finalizes session at exit (packs + signs .epi).
    """
    # Extract EPI options from kwargs
    output_path = kwargs.pop("__epi_output_path", None)
    if output_path is None:
        import os
        from pathlib import Path

        output_path = Path(
            os.environ.get(
                "EPI_GUARDRAILS_OUTPUT", _settings.get("output_path", "guardrails_run.epi")
            )
        )

    auto_sign = kwargs.pop("__epi_auto_sign", _settings.get("auto_sign", True))
    redact = kwargs.pop("__epi_redact", _settings.get("redact", True))
    goal = kwargs.pop("__epi_goal", _settings.get("goal", None))
    notes = kwargs.pop("__epi_notes", _settings.get("notes", None))
    tags = kwargs.pop("__epi_tags", _settings.get("tags", None))

    existing_state = guardrails_epi_state()

    # Extract guard config
    guard_config = {}
    try:
        if hasattr(self, "rail") and self.rail:
            guard_config["rail_present"] = True
        if hasattr(self, "metadata"):
            guard_config["metadata"] = getattr(self, "metadata", {}) or {}
    except (AttributeError, TypeError) as exc:
        logger.warning("epi_guardrails: could not extract guard config: %s", exc)

    # If already in a session, attach to the active session and avoid
    # creating a nested output-less session
    if existing_state is not None:
        from epi_guardrails.session import _global_sessions
        active_session = _global_sessions.get(id(existing_state))
        if active_session:
            active_session.emit_guard_execution_start(
                guard_config=guard_config or None,
                prompt=str(kwargs.get("prompt", "")) if kwargs.get("prompt") else None,
            )
        try:
            return wrapped(self, *args, **kwargs)
        except Exception:
            if active_session:
                active_session.state.exception_raised = True
            raise

    guard_name = getattr(self, "name", None) or "guardrails"
    ver_str = ".".join(map(str, _guardrails_version()))

    session = GuardrailsRecorderSession(
        output_path=output_path,
        auto_sign=auto_sign,
        redact=redact,
        guard_name=guard_name,
        guardrails_version=ver_str,
        goal=goal,
        notes=notes,
        tags=tags,
        agent_identity=_settings.get("agent_identity"),
    )

    try:
        with session:
            session.emit_guard_execution_start(
                guard_config=guard_config or None,
                # Full prompt — no truncation. EU AI Act Article 12 traceability.
                prompt=str(kwargs.get("prompt", "")) if kwargs.get("prompt") else None,
            )

            # Call original Guard._execute
            result = wrapped(self, *args, **kwargs)

            return result

    except Exception as e:
        session.state.exception_raised = True
        raise


async def _wrap_guard_execute_async(
    wrapped: Callable,
    self: Any,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Async variant of Guard._execute wrapper."""
    output_path = kwargs.pop("__epi_output_path_async", None)
    if output_path is None:
        import os
        from pathlib import Path

        output_path = Path(
            os.environ.get(
                "EPI_GUARDRAILS_OUTPUT", _settings.get("output_path", "guardrails_run.epi")
            )
        )

    auto_sign = kwargs.pop("__epi_auto_sign", _settings.get("auto_sign", True))
    redact = kwargs.pop("__epi_redact", _settings.get("redact", True))
    goal = kwargs.pop("__epi_goal", _settings.get("goal", None))
    notes = kwargs.pop("__epi_notes", _settings.get("notes", None))
    tags = kwargs.pop("__epi_tags", _settings.get("tags", None))

    guard_name = getattr(self, "name", None) or "guardrails"
    ver_str = ".".join(map(str, _guardrails_version()))

    session = GuardrailsRecorderSession(
        output_path=output_path,
        guard_name=guard_name,
        guardrails_version=ver_str,
        auto_sign=auto_sign,
        redact=redact,
        goal=goal,
        notes=notes,
        tags=tags,
        agent_identity=_settings.get("agent_identity"),
    )

    try:
        with session:
            # Extract prompt from kwargs or args for full capture.
            prompt_val = kwargs.get("prompt") or (args[0] if args else None)
            session.emit_guard_execution_start(
                prompt=str(prompt_val) if prompt_val else None,
            )
            result = await wrapped(self, *args, **kwargs)
            return result

    except Exception as e:
        session.state.exception_raised = True
        raise


# ==============================================================================
# Session finding helper (no global state)
# ==============================================================================


def _find_session(state: Any) -> Optional[GuardrailsRecorderSession]:
    """
    Find the GuardrailsRecorderSession from a GuardrailsEPIState.

    Since the session is set in contextvars + thread-local, and state is the
    GuardrailsEPIState dataclass (which is stored in context), we can use the
    state's session_id to look it up... but there's no global registry.

    Instead, we store a back-reference on the state object itself.
    """
    # The GuardrailsEPIState doesn't hold a reference to the session.
    # We need to store the session somewhere accessible.
    # The cleanest way: store it as an attribute on the state object.
    return getattr(state, "_session_ref", None)


# ==============================================================================
# Public API
# ==============================================================================


def instrument(
    output_path: str | Path = "guardrails_run.epi",
    auto_sign: bool = True,
    redact: bool = True,
    goal: Optional[str] = None,
    notes: Optional[str] = None,
    tags: Optional[list] = None,
    include_raw_rail: bool = False,
    agent_identity: Optional[dict] = None,
) -> bool:
    """
    Instrument Guardrails to produce .epi artifacts on every Guard execution.

    Call ONCE at application startup, BEFORE creating any Guard instances.

    Args:
        output_path: Path for the .epi artifact.
        auto_sign: Sign artifact with Ed25519 (default: True).
        redact: Apply default redaction rules (default: True).
        goal: Human-readable goal for the recording.
        notes: Additional notes embedded in the manifest.
        tags: Tags for categorising this recording.
        include_raw_rail: Whether to include rail XML in the start event.
        agent_identity: Optional dict identifying the agent that invoked the
            Guard. Persisted in the artifact for EU AI Act traceability.
            Example::

                instrument(
                    agent_identity={
                        "id": "did:web:my-service",
                        "version": "1.4.2",
                    }
                )

    Note:
        This PR stabilises the current monkey-patch integration. A follow-up
        will migrate to a native Instrumentor/event-based implementation
        aligned with the Guardrails telemetry system.

    Returns:
        True if instrumentation succeeded, False otherwise.
    """
    global _originals, _settings

    if not _HAS_WRAPT:
        logger.error("wrapt not installed. Run: pip install wrapt")
        return False

    _settings = {
        "output_path": str(output_path),
        "auto_sign": auto_sign,
        "redact": redact,
        "goal": goal,
        "notes": notes,
        "tags": tags or [],
        "include_raw_rail": include_raw_rail,
        "agent_identity": agent_identity or {},
    }

    try:
        import guardrails as gd
    except ImportError:
        logger.error("Guardrails AI not installed. Run: pip install guardrails-ai")
        return False

    ver = _guardrails_version()
    logger.info(f"Instrumenting Guardrails {ver[0]}.{ver[1]}.{ver[2]}")

    # ---- Guard._execute ----
    try:
        guard_module = import_module(_GUARD_MODULE)
        guard_cls = getattr(guard_module, "Guard", None)
        if guard_cls and hasattr(guard_cls, "_execute"):
            if "Guard._execute" not in _originals:
                orig = getattr(guard_cls, "_execute")
                if getattr(orig, "__name__", "") == "_execute_wrapper":
                    pass
                else:
                    _originals["Guard._execute"] = orig

            def _execute_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
                kwargs = dict(kwargs)
                kwargs.setdefault("__epi_output_path", output_path)
                kwargs.setdefault("__epi_auto_sign", auto_sign)
                kwargs.setdefault("__epi_redact", redact)
                kwargs.setdefault("__epi_goal", goal)
                kwargs.setdefault("__epi_notes", notes)
                kwargs.setdefault("__epi_tags", tags)
                wrapped = _originals["Guard._execute"]
                if getattr(wrapped, "__name__", "") == "_execute_wrapper":
                    raise RuntimeError("Infinite loop detected: original is the wrapper!")
                return _wrap_guard_execute(wrapped, self, args, kwargs)

            guard_cls._execute = _execute_wrapper  # type: ignore
            logger.info("Instrumented Guard._execute")
    except Exception as e:
        logger.warning(f"Failed to instrument Guard._execute: {e}")

    # ---- Guard._execute_async ----
    try:
        guard_module = import_module(_GUARD_MODULE)
        guard_cls = getattr(guard_module, "Guard", None)
        if guard_cls and hasattr(guard_cls, "_execute_async"):
            if "Guard._execute_async" not in _originals:
                orig = getattr(guard_cls, "_execute_async")
                if getattr(orig, "__name__", "") == "_execute_async_wrapper":
                    pass
                else:
                    _originals["Guard._execute_async"] = orig

            async def _execute_async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
                kwargs = dict(kwargs)
                kwargs.setdefault("__epi_output_path_async", output_path)
                kwargs.setdefault("__epi_auto_sign", auto_sign)
                kwargs.setdefault("__epi_redact", redact)
                kwargs.setdefault("__epi_goal", goal)
                kwargs.setdefault("__epi_notes", notes)
                kwargs.setdefault("__epi_tags", tags)
                wrapped = _originals["Guard._execute_async"]
                return await _wrap_guard_execute_async(wrapped, self, args, kwargs)

            guard_cls._execute_async = _execute_async_wrapper  # type: ignore
            logger.info("Instrumented Guard._execute_async")
    except Exception as e:
        logger.warning(f"Failed to instrument Guard._execute_async: {e}")

    # ---- AsyncGuard._execute (some Guardrails versions use this class) ----
    try:
        guard_module = import_module(_GUARD_MODULE)
        async_guard_cls = getattr(guard_module, "AsyncGuard", None)
        if async_guard_cls and hasattr(async_guard_cls, "_execute") and "AsyncGuard._execute" not in _originals:
            _originals["AsyncGuard._execute"] = async_guard_cls._execute

            def _async_guard_execute_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
                kwargs = dict(kwargs)
                kwargs.setdefault("__epi_output_path", output_path)
                kwargs.setdefault("__epi_auto_sign", auto_sign)
                kwargs.setdefault("__epi_redact", redact)
                kwargs.setdefault("__epi_goal", goal)
                kwargs.setdefault("__epi_notes", notes)
                kwargs.setdefault("__epi_tags", tags)
                wrapped = _originals["AsyncGuard._execute"]
                if getattr(wrapped, "__name__", "") == "_async_guard_execute_wrapper":
                    raise RuntimeError("Infinite loop detected: original is the wrapper!")
                return _wrap_guard_execute(wrapped, self, args, kwargs)

            async_guard_cls._execute = _async_guard_execute_wrapper  # type: ignore
            logger.info("Instrumented AsyncGuard._execute")
    except Exception as e:
        logger.warning(f"Failed to instrument AsyncGuard._execute: {e}")

    # ---- Runner.step (non-streaming) ----
    try:
        runner_module = import_module(_RUNNER_MODULE)
        runner_cls = getattr(runner_module, "Runner", None)
        if runner_cls and hasattr(runner_cls, "step") and "Runner.step" not in _originals:
            _originals["Runner.step"] = runner_cls.step
            wrap_function_wrapper(_RUNNER_MODULE, "Runner.step", _wrap_runner_step)
            logger.info("Instrumented Runner.step")
    except Exception as e:
        logger.warning(f"Failed to instrument Runner.step: {e}")

    # ---- StreamRunner.step (sync streaming) ----
    try:
        stream_runner_cls = getattr(runner_module, "StreamRunner", None)
        if stream_runner_cls and hasattr(stream_runner_cls, "step") and "StreamRunner.step" not in _originals:
            _originals["StreamRunner.step"] = stream_runner_cls.step
            wrap_function_wrapper(_RUNNER_MODULE, "StreamRunner.step", _wrap_stream_runner_step)
            logger.info("Instrumented StreamRunner.step")
    except Exception as e:
        logger.warning(f"Failed to instrument StreamRunner.step: {e}")

    # ---- AsyncStreamRunner / AsyncRunner async step (streaming async) ----
    # Guardrails versions differ on the class/method name. Probe in priority order.
    _ASYNC_STEP_PROBES = [
        ("AsyncStreamRunner", "async_step"),
        ("AsyncRunner", "async_step"),
        ("AsyncStreamRunner", "step"),
    ]
    try:
        for _cls_name, _method_name in _ASYNC_STEP_PROBES:
            _async_stream_cls = getattr(runner_module, _cls_name, None)
            if _async_stream_cls and hasattr(_async_stream_cls, _method_name):
                _key = f"{_cls_name}.{_method_name}"
                if _key not in _originals:
                    _originals[_key] = getattr(_async_stream_cls, _method_name)
                    wrap_function_wrapper(_RUNNER_MODULE, f"{_cls_name}.{_method_name}", _wrap_async_stream_runner_step)
                    logger.info("Instrumented %s (async streaming)", _key)
                break  # Only hook the first available method
        else:
            logger.debug("No async streaming runner found in this Guardrails version; skipping.")
    except Exception as e:
        logger.warning(f"Failed to instrument async streaming runner: {e}")

    # ---- ValidatorServiceBase.after_run_validator ----
    try:
        validator_module = import_module(_VALIDATOR_MODULE)
        validator_svc = getattr(validator_module, "ValidatorServiceBase", None)
        if validator_svc and hasattr(validator_svc, "after_run_validator") and "ValidatorServiceBase.after_run_validator" not in _originals:
            _originals["ValidatorServiceBase.after_run_validator"] = (
                validator_svc.after_run_validator
            )
            wrap_function_wrapper(
                _VALIDATOR_MODULE,
                "ValidatorServiceBase.after_run_validator",
                _wrap_validator_after_run,
            )
            logger.info("Instrumented ValidatorServiceBase.after_run_validator")
    except Exception as e:
        logger.warning(f"Failed to instrument ValidatorServiceBase.after_run_validator: {e}")

    # ---- Runner.call / AsyncRunner.async_call ----
    try:
        runner_module = import_module(_RUNNER_MODULE)
        runner_cls = getattr(runner_module, "Runner", None)
        if runner_cls and hasattr(runner_cls, "call") and "Runner.call" not in _originals:
            _originals["Runner.call"] = runner_cls.call
            wrap_function_wrapper(_RUNNER_MODULE, "Runner.call", _wrap_runner_call)
            logger.info("Instrumented Runner.call")
        
        async_runner_cls = getattr(runner_module, "AsyncRunner", None)
        if async_runner_cls and hasattr(async_runner_cls, "async_call") and "AsyncRunner.async_call" not in _originals:
            _originals["AsyncRunner.async_call"] = async_runner_cls.async_call
            wrap_function_wrapper(_RUNNER_MODULE, "AsyncRunner.async_call", _wrap_async_runner_call)
            logger.info("Instrumented AsyncRunner.async_call")
    except Exception as e:
        logger.warning(f"Failed to instrument Runner calls: {e}")

    return True


def instrument_otel(
    output_dir: str = "./epi-recordings",
    auto_sign: bool = True,
    agent_identity: Optional[dict[str, Any]] = None,
) -> bool:
    """
    Production-grade instrumentation via OpenTelemetry (Stable Interface).

    This is the RECOMMENDED way to instrument Guardrails for compliance 
    use cases (Article 12). It leverages official framework hooks and 
    industry-standard tracing, avoiding the risks of monkey-patching.

    NOTE ON FIDELITY: 
    While stable, OTel instrumentation may have LOWER fidelity than legacy
    direct hooks. Specifically, raw corrections, 're-asks', and internal
    validator intermediate states might not be fully captured if they are
    not emitted as standard OTel span attributes by Guardrails AI.
    """
    from epi_guardrails.instrumentor_otel import otel_instrumentor

    return otel_instrumentor.instrument(
        output_dir=output_dir,
        auto_sign=auto_sign,
        agent_identity=agent_identity,
    )


def uninstrument() -> None:
    """
    Remove all Guardrails instrumentation and restore original methods.
    """
    global _originals, _settings

    _settings = {}

    restore_map = [
        ("Guard._execute", "guardrails.guard", "Guard"),
        ("Guard._execute_async", "guardrails.guard", "Guard"),
        ("AsyncGuard._execute", "guardrails.guard", "AsyncGuard"),
        ("Runner.step", "guardrails.run", "Runner"),
        ("StreamRunner.step", "guardrails.run", "StreamRunner"),
        ("AsyncStreamRunner.async_step", "guardrails.run", "AsyncStreamRunner"),
        ("AsyncRunner.async_step", "guardrails.run", "AsyncRunner"),
        ("AsyncStreamRunner.step", "guardrails.run", "AsyncStreamRunner"),
        (
            "ValidatorServiceBase.after_run_validator",
            "guardrails.validator_service",
            "ValidatorServiceBase",
        ),
        ("Runner.call", "guardrails.run", "Runner"),
        ("AsyncRunner.async_call", "guardrails.run", "AsyncRunner"),
    ]

    for name, module_name, cls_name in restore_map:
        if name in _originals:
            try:
                mod = import_module(module_name)
                cls = getattr(mod, cls_name, None)
                if cls is not None:
                    attr = name.split(".")[-1]
                    setattr(cls, attr, _originals[name])
            except (ImportError, AttributeError) as exc:
                logger.warning("epi_guardrails: uninstrument failed for %s: %s", name, exc)
            del _originals[name]

    # Shutdown OTel if active
    try:
        from epi_guardrails.instrumentor_otel import otel_instrumentor

        otel_instrumentor.uninstrument()
    except ImportError:
        pass

    logger.info("Guardrails instrumentation removed")
