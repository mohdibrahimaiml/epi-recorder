"""
epi_guardrails.session — GuardrailsRecorderSession.

Produces exactly ONE .epi artifact per Guard execution.
Hierarchical state: session → steps → validator results.
All state accessed via contextvars — no global mutable state.

Step emission flow:
  Runner.step → push iteration_id → emit guardrails.step → validators attach → emit validator results
  Runner.step returns → pop iteration_id
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
import time as time_module
import uuid
import weakref

_global_sessions = weakref.WeakValueDictionary()

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from epi_core.container import EPIContainer
from epi_cli.keys import KeyManager
from epi_core.redactor import get_default_redactor
from epi_core.schemas import ManifestModel, StepModel
from epi_core.time_utils import utc_now, utc_now_iso
from epi_core.workspace import create_recording_workspace

from epi_guardrails.state import (
    GuardrailsEPIState,
    guardrails_epi_state,
    get_current_iteration_id,
    pop_current_iteration_id,
    push_current_iteration_id,
    set_guardrails_epi_state,
    reset_guardrails_epi_state,
)


def _normalize_for_hash(data: Any) -> Any:
    """
    Recursively normalize data to a canonical, deterministic form.

    Rules:
      - dict  → sorted keys, values recursively normalized
      - list  → elements recursively normalized (order preserved)
      - Pydantic BaseModel → .model_dump() then normalize
      - str, int, float, bool, None → pass-through
      - Anything else → raises TypeError

    Raises TypeError for non-serializable objects so callers can decide
    whether to skip or surface the error. Never falls back to str().
    """
    if data is None or isinstance(data, (bool, int, float, str)):
        return data
    if isinstance(data, dict):
        return {k: _normalize_for_hash(v) for k, v in sorted(data.items())}
    if isinstance(data, (list, tuple)):
        return [_normalize_for_hash(v) for v in data]
    # Pydantic v2
    if hasattr(data, "model_dump"):
        return _normalize_for_hash(data.model_dump())
    # Pydantic v1
    if hasattr(data, "dict") and callable(data.dict):
        return _normalize_for_hash(data.dict())
    raise TypeError(
        f"_canonical_hash: non-serializable type {type(data).__name__!r}. "
        "Convert to a primitive before hashing."
    )


def _canonical_hash(data: Any) -> Optional[str]:
    """
    Compute a stable SHA-256 hash over canonicalized data.

    Returns None if data is None.
    Raises TypeError if data contains non-serializable objects.
    """
    if data is None:
        return None
    normalized = json.dumps(_normalize_for_hash(data), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


# Keep _hash_payload as a thin alias that swallows TypeError for call sites
# that genuinely cannot guarantee serializability (e.g. raw LLM API objects).
# Prefer _canonical_hash in all new code.
def _hash_payload(data: Any) -> str:
    """Legacy alias. Returns '' on None, None on TypeError."""
    if data is None:
        return ""
    try:
        result = _canonical_hash(data)
        return result or ""
    except TypeError:
        return ""


# ==============================================================================
# Step types for Guardrails-specific steps
# ==============================================================================


@dataclass
class ValidatorResult:
    """A single validator outcome attached to a step."""

    name: str
    status: str  # "pass" | "fail" | "error"
    corrected: bool
    rail_alias: str
    value: Any = None
    parsed: Any = None
    error: Optional[str] = None
    original_value_hash: Optional[str] = None
    corrected_value_hash: Optional[str] = None
    event_index: int = 0
    timestamp: str = ""


@dataclass
class GuardrailsStepRecord:
    """
    A single guardrails.step (iteration) step.

    Contains the iteration data AND all validator results that ran against it.
    Validator results are attached by after_run_validator hooks via step_id linkage.
    """

    step_id: str  # UUID generated at begin_iteration
    iteration_index: int
    iteration_id: str  # Guardrails Iteration.id
    step_index: int  # EPI step index
    event_index: int  # Monotonic event counter

    llm_call: Optional[Dict[str, Any]] = None
    raw_output: Optional[str] = None
    parsed_output: Optional[str] = None
    validated_output: Optional[str] = None
    guarded_output: Optional[str] = None  # After correction

    # Integrity
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None
    corrected_output_hash: Optional[str] = None

    # Validation
    validation_passed: bool = True
    correction_applied: bool = False
    validators: List[ValidatorResult] = field(default_factory=list)

    # Timing
    duration_seconds: Optional[float] = None
    timestamp: str = ""
    timestamp_ns: int = 0  # Nanosecond timestamp for ordering

    # Step linkage
    parent_step_id: Optional[str] = None  # For nested steps

    # Completion
    completed: bool = False  # False if orphan (end_iteration never called)

    def attach_validator(self, result: ValidatorResult) -> None:
        self.validators.append(result)

    def to_content(self) -> Dict[str, Any]:
        """
        Serialize to viewer-friendly step content dict.

        Structure is optimized for human readability and EPI viewer rendering:
        - LLM call embedded inside step (not separate event)
        - Validators list attached directly to step
        - Correction block explicit
        - Status derived from validation outcome
        """
        status = "pass"
        if not self.completed:
            status = "incomplete"
        elif not self.validation_passed:
            status = "fail"
        elif self.correction_applied:
            status = "corrected"

        step_content: Dict[str, Any] = {
            "type": "agent.step",
            "subtype": "guardrails",
            "step_id": self.step_id,
            "step_index": self.step_index,
            "event_index": self.event_index,
            "iteration_index": self.iteration_index,
            "timestamp_ns": self.timestamp_ns,
            "status": status,
            "completed": self.completed,
        }

        if self.llm_call:
            step_content["llm_call"] = self.llm_call

        if self.input_hash:
            step_content["input_hash"] = self.input_hash

        output_block: Dict[str, Any] = {}
        if self.raw_output:
            output_block["raw"] = self.raw_output
        if self.parsed_output:
            output_block["parsed"] = self.parsed_output
        if self.validated_output:
            output_block["validated"] = self.validated_output
        if self.guarded_output:
            output_block["guarded"] = self.guarded_output
        if self.output_hash:
            output_block["output_hash"] = self.output_hash
        if output_block:
            step_content["output"] = output_block

        if self.correction_applied or self.corrected_output_hash:
            step_content["correction"] = {
                "applied": self.correction_applied,
                "original_output_hash": self.output_hash,
                "corrected_output_hash": self.corrected_output_hash,
            }

        if self.validators:
            step_content["validators"] = [
                {
                    "type": "validation",
                    "validator_name": v.name,
                    "status": "corrected" if v.corrected else (v.status if v.status else "pass"),
                    "reason": v.error or "",
                    "config": {"rail_alias": v.rail_alias},
                    "original_value_hash": v.original_value_hash,
                    "corrected_value_hash": v.corrected_value_hash,
                    "timestamp": v.timestamp,
                }
                for v in self.validators
            ]

        if self.duration_seconds is not None:
            step_content["duration_seconds"] = self.duration_seconds

        return step_content


class GuardrailsRecorderSession:
    """
    Records ONE Guardrails execution into ONE .epi artifact.

    Lifecycle:
      __enter__  → create workspace + state, install in contextvars
      [execution]
      __exit__   → finalize: write steps.jsonl → pack .epi → sign

    All instrumentation hooks append to this session via context-accessed methods.
    Thread-safe and async-safe.
    """

    def __init__(
        self,
        output_path: Path | str,
        *,
        guard_name: Optional[str] = None,
        guardrails_version: Optional[str] = None,
        auto_sign: bool = True,
        default_key_name: str = "default",
        redact: bool = True,
        goal: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
        include_raw_rail: bool = False,
        agent_identity: Optional[Dict[str, Any]] = None,
    ):
        self.output_path = Path(output_path)
        self.guard_name = guard_name or "guardrails"
        self.guardrails_version = guardrails_version or ""
        self.auto_sign = auto_sign
        self.default_key_name = default_key_name
        self.redact = redact
        self.goal = goal
        self.notes = notes
        self.tags = tags or []
        self.include_raw_rail = include_raw_rail
        self.agent_identity = agent_identity or {}
        self.key_name: Optional[str] = None
        self.public_key: Optional[str] = None
        self.registry_url: Optional[str] = None

        # Runtime
        self._state: Optional[GuardrailsEPIState] = None
        self._temp_dir: Optional[Path] = None
        self._start_time: Optional[datetime] = None
        self._entered = False
        self._finalized = False
        self._execution_started = False
        self._execution_ended = False

        # Thread-safe step accumulator
        self._lock = threading.Lock()
        self._steps: List[Dict[str, Any]] = []

        # Explicit mapping: iteration_id → step_id (UUID)
        # Ensures validators can only attach to the correct step even if iteration_ids collide
        self._iteration_to_step: Dict[str, str] = {}

        # Active step context: step_id → GuardrailsStepRecord
        # Replaces fragile _active_step object with explicit mapping
        self._step_records: Dict[str, GuardrailsStepRecord] = {}
        
        # State restore token for nested execution
        self._token: Any = None

    # --------------------------------------------------------------------------
    # Context manager
    # --------------------------------------------------------------------------

    def __enter__(self) -> "GuardrailsRecorderSession":
        if self._entered:
            raise RuntimeError("GuardrailsRecorderSession cannot be re-entered")
        self._entered = True
        self._execution_started = True
        self._start_time = utc_now()

        self._temp_dir = create_recording_workspace("epi_guardrails_")

        self._state = GuardrailsEPIState(
            guard_name=self.guard_name,
            guardrails_version=self.guardrails_version,
        )
        self._state._session_ref = self
        self._recording = True
        global _global_sessions
        
        # Pushes this state onto the logical stack
        self._token = set_guardrails_epi_state(self.state)
        _global_sessions[id(self.state)] = self
        
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._finalized:
            return
        self._finalized = True
        self._execution_ended = True

        try:
            self._finalize(exc_type, exc_val)
        finally:
            if self._token:
                reset_guardrails_epi_state(self._token)

    # --------------------------------------------------------------------------
    # State access
    # --------------------------------------------------------------------------

    @property
    def state(self) -> GuardrailsEPIState:
        if self._state is None:
            raise RuntimeError("Session not active")
        return self._state

    @property
    def _step_index(self) -> int:
        return len(self._steps)

    # --------------------------------------------------------------------------
    # Step emission (called by instrumentation wrappers)
    # --------------------------------------------------------------------------

    def _next_event_index(self) -> int:
        """Thread-safe monotonic event index."""
        return self.state.next_event_index()

    def _emit_step(self, kind: str, content: Dict[str, Any]) -> None:
        """Low-level step emission. Thread-safe."""
        if self._finalized:
            return

        redactor = get_default_redactor() if self.redact else None

        with self._lock:
            if redactor:
                content, _ = redactor.redact(content)

            step = StepModel(
                index=self._step_index,
                timestamp=utc_now(),
                kind=kind,
                content=content,
                trace_id=self.state.trace_id,
            )

            self._steps.append(step.model_dump(mode="json"))

    # ---- Execution start/end ----

    def emit_guard_execution_start(
        self,
        guard_config: Optional[Dict[str, Any]] = None,
        rail: Optional[str] = None,
        prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit guardrails.execution.start."""
        ei = self._next_event_index()
        ts_ns = time_module.time_ns()

        try:
            self.state.input_hash = _canonical_hash(
                {
                    "rail": rail,
                    "prompt": prompt,
                    "config": guard_config,
                }
            )
        except TypeError as exc:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "epi_guardrails: could not hash execution start payload: %s", exc
            )

        content: Dict[str, Any] = {
            "event_index": ei,
            "timestamp_ns": ts_ns,
            "guardrails_version": self.guardrails_version,
            "trace_id": self.state.trace_id,
            "session_id": self.state.session_id,
        }

        guard_block: Dict[str, Any] = {"name": self.guard_name}
        if guard_config:
            guard_block["config"] = guard_config
        if rail and self.include_raw_rail:
            guard_block["rail"] = rail

        content["guard"] = guard_block

        if prompt:
            # Full prompt — no truncation. Article 12 requires complete inputs.
            content["prompt"] = prompt
        if metadata:
            content["metadata"] = metadata

        # Agent identity binding — persisted in every execution start event.
        if self.agent_identity:
            content["agent"] = self.agent_identity

        content["type"] = "agent.step"
        content["subtype"] = "guardrails"
        content["phase"] = "start"

        self._emit_step("agent.step", content)

    def emit_guard_execution_end(
        self,
        success: bool,
        duration_seconds: float,
        final_output: Optional[str] = None,
        exception_type: Optional[str] = None,
        exception_message: Optional[str] = None,
    ) -> None:
        """Emit guardrails.execution.end."""
        ei = self._next_event_index()
        ts_ns = time_module.time_ns()

        if final_output:
            self.state.output_hash = _hash_payload(final_output)

        content = {
            "event_index": ei,
            "timestamp_ns": ts_ns,
            "guard_name": self.guard_name,
            "session_id": self.state.session_id,
            "success": success,
            "duration_seconds": round(duration_seconds, 4),
            "iterations_count": self.state.iterations_count,
            "llm_calls_count": self.state.llm_calls_count,
            "final_output_hash": self.state.output_hash,
            "exception_type": exception_type,
            "exception_message": exception_message,
        }

        content["type"] = "agent.step"
        content["subtype"] = "guardrails"
        content["phase"] = "end"

        self._emit_step("agent.step", content)

    def begin_iteration(
        self,
        iteration_index: int,
        iteration_id: str,
        llm_call: Optional[Dict[str, Any]] = None,
        input_data: Optional[Any] = None,
        timestamp: Optional[str] = None,
    ) -> Optional[str]:
        """
        Begin a new iteration step.

        Called at the START of Runner.step before any validators run.
        Generates a unique step_id and stores explicit iteration_id → step_id mapping.
        Pushes step_id onto context so validators can attach to the correct step.

        Returns the step_id (UUID string) so caller can pass to end_iteration.

        Args:
            iteration_index: 0-based iteration index within this execution
            iteration_id: Guardrails' unique Iteration.id
            llm_call: LLM call info (provider, model, messages)
            input_data: The input that was validated
        """
        if self._finalized:
            return None

        step_id = str(uuid.uuid4())

        ei = self._next_event_index()
        ts = timestamp or utc_now_iso()
        ts_ns = time_module.time_ns()

        if input_data is not None:
            self.state.input_hash = _hash_payload(input_data)

        if llm_call:
            self.state.llm_calls_count += 1

        step_record = GuardrailsStepRecord(
            step_id=step_id,
            iteration_index=iteration_index,
            iteration_id=iteration_id,
            step_index=self._step_index,
            event_index=ei,
            llm_call=llm_call,
            timestamp=ts,
            timestamp_ns=ts_ns,
            input_hash=self.state.input_hash,
        )

        with self._lock:
            self._iteration_to_step[iteration_id] = step_id
            self._step_records[step_id] = step_record

        push_current_iteration_id(iteration_id)
        self.state.iterations_count += 1

        return step_id

    def end_iteration(
        self,
        iteration_index: int,
        iteration_id: str,
        iteration: Any,
        duration_seconds: Optional[float] = None,
    ) -> None:
        """
        Finalize and emit the current iteration step.

        Called at the END of Runner.step after all validators have run.
        NOTE: Caller must pop the step_id from context AFTER this returns.
        This method emits the step but does NOT pop the iteration stack.

        Looks up step_id from iteration_id → step_id mapping and retrieves
        the step record from _step_records dict.

        Args:
            iteration_index: Must match begin_iteration call
            iteration_id: Must match begin_iteration call
            iteration: The Guardrails Iteration object returned by Runner.step
            duration_seconds: Step wall-clock time
        """
        if self._finalized:
            return

        with self._lock:
            step_id = self._iteration_to_step.pop(iteration_id, None)
            step_record = self._step_records.pop(step_id, None) if step_id else None

        if step_record is None:
            return

        ei = self._next_event_index()
        ts = utc_now_iso()
        ts_ns = time_module.time_ns()

        output_hash = None
        corrected_hash = None
        raw_output = None
        parsed_output = None
        validated_output = None
        guarded_output = None
        validation_passed = True
        correction_applied = False
        original_output_hash = None

        try:
            if iteration is not None:
                outputs = getattr(iteration, "outputs", None)
                if outputs:
                    llm_response_info = getattr(outputs, "llm_response_info", None)
                    if llm_response_info:
                        try:
                            raw_output = str(getattr(llm_response_info, "output", "") or "")[:2000]
                        except Exception:
                            pass

                    parsed_out = getattr(outputs, "parsed_output", None)
                    if parsed_out is not None:
                        parsed_output = str(parsed_out)[:2000]
                        original_output_hash = _hash_payload(parsed_output)

                    val_resp = getattr(outputs, "validation_response", None)
                    if val_resp is not None:
                        passed = getattr(val_resp, "passed", None)
                        if passed is not None:
                            validation_passed = bool(passed)
                            if validation_passed:
                                validated_output = str(val_resp)[:2000] if val_resp else None
                        else:
                            from guardrails_ai.types.reask import ReAsk

                            if isinstance(val_resp, ReAsk):
                                validation_passed = False
                                validated_output = None
                            else:
                                validation_passed = True
                                validated_output = str(val_resp)[:2000] if val_resp else None

                    guarded_out = getattr(outputs, "guarded_output", None)
                    if guarded_out is not None:
                        guarded_output = str(guarded_out)[:2000]
                        if guarded_output != parsed_output:
                            correction_applied = True

                    if validated_output is not None:
                        output_hash = _hash_payload(validated_output)
                        self.state.output_hash = output_hash
                    elif guarded_output is not None:
                        output_hash = _hash_payload(guarded_output)
                        self.state.output_hash = output_hash

                    if guarded_output is not None and guarded_output != parsed_output:
                        corrected_hash = _hash_payload(guarded_output)
        except Exception:
            pass

        step_record.raw_output = raw_output
        step_record.parsed_output = parsed_output
        step_record.validated_output = validated_output
        step_record.guarded_output = guarded_output
        step_record.validation_passed = validation_passed
        step_record.correction_applied = correction_applied or (corrected_hash is not None)
        step_record.output_hash = output_hash
        step_record.corrected_output_hash = corrected_hash
        step_record.duration_seconds = duration_seconds
        step_record.timestamp_ns = ts_ns
        step_record.completed = True

        self._emit_step("agent.step", step_record.to_content())

    # ---- Validator result (called by after_run_validator hook) ----

    def emit_validator_result(
        self,
        name: str,
        status: str,
        corrected: bool,
        rail_alias: str,
        value: Any = None,
        parsed: Any = None,
        error: Optional[str] = None,
        original_value_hash: Optional[str] = None,
        corrected_value_hash: Optional[str] = None,
        iteration_id: Optional[str] = None,
    ) -> None:
        """
        Attach a validator result to the current iteration step.

        Called by the after_run_validator instrumentation hook.
        STRICT LINKAGE: resolves step_id from iteration_id → step_id mapping,
        then attaches to _step_records[step_id]. Validators can only attach
        to steps they explicitly belong to.

        Args:
            name: Validator name
            status: "pass" | "fail" | "error"
            corrected: Whether the value was corrected
            rail_alias: Guardrails on_fail descriptor
            value: Raw value that was validated
            parsed: Parsed value
            error: Error message if status="error"
            original_value_hash: Hash of value before correction
            corrected_value_hash: Hash of value after correction
            iteration_id: Guardrails iteration_id (required - resolved from context by instrumentor)
        """
        if self._finalized:
            return

        if iteration_id is None:
            iteration_id = get_current_iteration_id()

        if iteration_id is None:
            return

        ei = self._next_event_index()
        ts = utc_now_iso()

        result = ValidatorResult(
            name=name,
            status=status,
            corrected=corrected,
            rail_alias=rail_alias,
            value=value,
            parsed=parsed,
            error=error,
            original_value_hash=original_value_hash
            or (None if value is None else _hash_payload(value)),
            corrected_value_hash=corrected_value_hash,
            event_index=ei,
            timestamp=ts,
        )

        with self._lock:
            step_id = self._iteration_to_step.get(iteration_id)
            step_record = self._step_records.get(step_id) if step_id else None
            if step_record is not None:
                step_record.attach_validator(result)

    # ---- LLM call step (called by Runner.call hook) ----

    def emit_llm_call(
        self,
        provider: str,
        model: str,
        messages: List[Dict[str, Any]],
        choices: Optional[List[Dict[str, Any]]] = None,
        usage: Optional[Dict[str, int]] = None,
        latency_seconds: Optional[float] = None,
        error: Optional[str] = None,
        system: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> None:
        """Emit a guardrails.llm.call step."""
        ei = self._next_event_index()
        ts_ns = time_module.time_ns()

        self.state.llm_calls_count += 1

        content = {
            "event_index": ei,
            "timestamp_ns": ts_ns,
            "provider": provider,
            "model": model,
            "messages": messages,
        }
        if system:
            content["system"] = system
        if choices:
            content["choices"] = choices
        if usage:
            content["usage"] = usage
        if latency_seconds is not None:
            content["latency_seconds"] = round(latency_seconds, 4)
        if error:
            content["error"] = error
        if step_id:
            content["step_id"] = step_id

        self._emit_step("guardrails.llm.call", content)

    # ---- Input/output validation ----

    def emit_input_validation(
        self,
        validated_input: Any,
        validation_passed: bool,
        validators_run: List[str],
    ) -> None:
        """Emit guardrails.input.validation step."""
        ei = self._next_event_index()
        ts_ns = time_module.time_ns()
        input_hash = _hash_payload(validated_input)
        self.state.input_hash = input_hash

        self._emit_step(
            "guardrails.input.validation",
            {
                "event_index": ei,
                "timestamp_ns": ts_ns,
                "input_hash": input_hash,
                "validated_input": validated_input,
                "validation_passed": validation_passed,
                "validators_run": validators_run,
            },
        )

    def emit_output_validation(
        self,
        validated_output: Any,
        validation_passed: bool,
        validators_run: List[str],
        correction_applied: bool,
    ) -> None:
        """Emit guardrails.output.validation step."""
        ei = self._next_event_index()
        ts_ns = time_module.time_ns()
        output_hash = _hash_payload(validated_output)
        self.state.output_hash = output_hash

        self._emit_step(
            "guardrails.output.validation",
            {
                "event_index": ei,
                "timestamp_ns": ts_ns,
                "output_hash": output_hash,
                "validated_output": validated_output,
                "validation_passed": validation_passed,
                "validators_run": validators_run,
                "correction_applied": correction_applied,
            },
        )

    def emit_guardrails_step(
        self,
        iteration_index: int,
        iteration_id: str,
        validation_passed: bool,
        validators: List[Any],
        correction_applied: bool,
        duration_seconds: float,
        validated_output: Optional[str] = None,
        guarded_output: Optional[str] = None,
        completed: bool = True,
    ) -> None:
        """
        Emit a generic guardrails step (used for streaming or fallback).
        This mimics the structure of an iteration step without requiring a Guardrails object.
        """
        ei = self._next_event_index()
        ts_ns = time_module.time_ns()

        content = {
            "event_index": ei,
            "timestamp_ns": ts_ns,
            "iteration_index": iteration_index,
            "iteration_id": iteration_id,
            "validation_passed": validation_passed,
            "validators": validators,
            "correction_applied": correction_applied,
            "duration_seconds": duration_seconds,
            "completed": completed,
            "type": "agent.step",
            "subtype": "guardrails",
        }
        if validated_output:
            content["validated_output"] = validated_output
            content["output_hash"] = _hash_payload(validated_output)
        if guarded_output:
            content["guarded_output"] = guarded_output
            if guarded_output != validated_output:
                content["corrected_output_hash"] = _hash_payload(guarded_output)

        self._emit_step("agent.step", content)

    # --------------------------------------------------------------------------
    # Finalization
    # --------------------------------------------------------------------------

    def _finalize(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
    ) -> None:
        """Write viewer-friendly .epi artifact with atomic write."""
        if self._temp_dir is None:
            return

        duration = (utc_now() - self._start_time).total_seconds() if self._start_time else 0.0

        # Handle orphan steps: any step that wasn't finalized
        with self._lock:
            for step_record in self._step_records.values():
                if not step_record.completed:
                    step_record.completed = False
                    ei = self._next_event_index()
                    self._emit_step("guardrails.step", step_record.to_content())

        # Audit-level Metadata Completeness (Article 12)
        runtime_meta = self._get_runtime_metadata()
        completeness_checklist = self._verify_completeness()

        success = exc_type is None if not self.state.exception_raised else False
        exc_type_str = exc_type.__name__ if exc_type else None
        exc_msg = str(exc_val) if exc_val else None

        # Build source.json (viewer branding)
        source_info = {
            "integration": "epi_guardrails",
            "framework": "guardrails",
            "framework_version": self.guardrails_version,
            "recorder_version": "1.0.0",
            "instrumentation": {
                "hooks": [
                    "Guard._execute",
                    "Runner.step",
                    "StreamRunner.step",
                    "ValidatorServiceBase.after_run_validator",
                ]
            },
        }

        # Build summary.json (viewer dashboard)
        total_steps = 0
        total_validators = 0
        total_llm_calls = self.state.llm_calls_count
        passed_steps = 0
        failed_steps = 0
        corrected_steps = 0

        guardrails_steps = [
            s for s in self._steps
            if s["kind"] == "agent.step" and s.get("content", {}).get("subtype") == "guardrails" and "phase" not in s.get("content", {})
        ]
        for step in guardrails_steps:
            total_steps += 1
            content = step.get("content", {})
            status = content.get("status", "pass")
            if status == "pass":
                passed_steps += 1
            elif status == "fail":
                failed_steps += 1
            elif status == "corrected":
                corrected_steps += 1
            validators = content.get("validators", [])
            total_validators += len(validators)

        summary_info = {
            "total_steps": total_steps,
            "total_validators": total_validators,
            "total_llm_calls": total_llm_calls,
            "passed": passed_steps,
            "failed": failed_steps,
            "corrected": corrected_steps,
        }

        # Build execution metadata
        runtime_info = {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "process_start_time": os.environ.get("START_TIME", str(utc_now())),
        }

        # Compute steps_hash over the raw steps.jsonl bytes for verifier.
        # This hash is stored in execution.json and checked by `epi verify --strict`.
        steps_path_for_hash = self._temp_dir / "steps.jsonl"
        steps_hash: Optional[str] = None
        if steps_path_for_hash.exists():
            try:
                raw_bytes = steps_path_for_hash.read_bytes()
                steps_hash = hashlib.sha256(raw_bytes).hexdigest()
            except OSError as exc:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "epi_guardrails: could not compute steps_hash: %s", exc
                )

        execution_info: Dict[str, Any] = {
            "guard_name": self.guard_name,
            "session_id": self.state.session_id,
            "trace_id": self.state.trace_id,
            "guardrails_version": self.guardrails_version,
            "duration_seconds": round(duration, 4),
            "success": success,
            "exception_type": exc_type_str,
            "exception_message": exc_msg,
            "iterations_count": self.state.iterations_count,
            "llm_calls_count": self.state.llm_calls_count,
            "input_hash": self.state.input_hash,
            "output_hash": self.state.output_hash,
            "steps_hash": steps_hash,
        }
        if self.agent_identity:
            execution_info["agent"] = self.agent_identity

        # Write source.json
        source_path = self._temp_dir / "source.json"
        with open(source_path, "w", encoding="utf-8") as f:
            json.dump(source_info, f, default=str)

        # Write summary.json
        summary_path = self._temp_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_info, f, default=str)

        # Write runtime.json
        runtime_path = self._temp_dir / "runtime.json"
        with open(runtime_path, "w", encoding="utf-8") as f:
            json.dump(runtime_info, f, default=str)

        # Write execution.json
        execution_path = self._temp_dir / "execution.json"
        with open(execution_path, "w", encoding="utf-8") as f:
            json.dump(execution_info, f, default=str)

        # Write viewer-friendly steps.jsonl (ordered, self-contained steps)
        steps_path = self._temp_dir / "steps.jsonl"
        with open(steps_path, "w", encoding="utf-8") as f:
            for step_dict in self._steps:
                f.write(json.dumps(step_dict, default=str) + "\n")

        # Write validation.json if inconsistencies
        inconsistencies = []
        for step_dict in self._steps:
            content = step_dict.get("content", {})
            if step_dict["kind"] == "agent.step" and content.get("subtype") == "guardrails" and "phase" not in content:
                if not content.get("step_id"):
                    inconsistencies.append(f"Step at index {step_dict['index']} missing step_id")
                if not step_dict["content"].get("completed", True):
                    inconsistencies.append(f"Step at index {step_dict['index']} marked incomplete")

        if inconsistencies:
            validation_path = self._temp_dir / "validation.json"
            with open(validation_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "consistency_check": "failed",
                        "issues": inconsistencies,
                        "session_id": self.state.session_id,
                        "trace_id": self.state.trace_id,
                    },
                    f,
                    default=str,
                )

        # Build manifest
        manifest = ManifestModel(
            created_at=self._start_time or utc_now(),
            goal=self.goal or f"Guardrails execution: {self.guard_name}",
            notes=self.notes,
            tags=self.tags,
            spec_version="1.0",
            source={
                "integration": "epi_guardrails",
                "framework": "guardrails",
                "framework_version": self.guardrails_version,
                "type": "validation_pipeline",
            },
            total_steps=total_steps,
            total_validators=total_validators,
            total_llm_calls=total_llm_calls,
            passed=passed_steps,
            failed=failed_steps,
            corrected=corrected_steps,
            trust={
                "public_key_id": self.key_name,
                "registry_url": getattr(self, "registry_url", None),
                "fingerprint": hashlib.sha256(self.public_key.encode()).hexdigest() if hasattr(self, "public_key") and self.public_key else None,
                "steps_hash": steps_hash,
                "signed": bool(self.auto_sign),
                "verification_status": "pending" if self.auto_sign else "unsigned",
            },
            governance={
                "agent_identity": self.agent_identity,
                "runtime": runtime_meta,
                "completeness": completeness_checklist,
            },
        )
        signer_function = None
        if self.auto_sign:
            try:
                signer_function = self._get_signer_function()
            except Exception as sign_err:
                print(f"[epi_guardrails] Failed to initialize signer: {sign_err}")

        # Atomic write: pack to temp file, fsync, rename
        temp_output = self.output_path.with_suffix(".epi.tmp")
        try:
            EPIContainer.pack(
                source_dir=self._temp_dir,
                manifest=manifest,
                output_path=temp_output,
                signer_function=signer_function,
            )
        except Exception as pack_err:
            print(f"[epi_guardrails] Failed to pack .epi artifact: {pack_err}")
            raise

        # Atomic rename to final path
        try:
            if self.output_path.exists():
                self.output_path.unlink()
            temp_output.replace(self.output_path)
        except Exception as rename_err:
            print(f"[epi_guardrails] Failed to finalize .epi artifact: {rename_err}")
            raise

        # Memory cleanup
        with self._lock:
            self._iteration_to_step.clear()
            self._step_records.clear()

        # Cleanup temp dir
        import shutil

        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _sign_epi(self) -> bool:
        """Return signer function for EPIContainer.pack."""
        try:
            from epi_core.trust import sign_manifest

            km = KeyManager()
            key_name = self.default_key_name or "default"
            if not km.has_key(key_name):
                km.generate_keypair(key_name, overwrite=False)
            
            private_key = km.load_private_key(key_name)
            public_key = km.load_public_key(key_name)
            
            self.public_key = public_key.hex()
            self.key_name = key_name

            def signer(manifest):
                from epi_core.trust import sign_manifest
                return sign_manifest(manifest, private_key, key_name)

            self._signer_function = signer
            return True
        except Exception:
            return False

    def _get_signer_function(self):
        """Get the signer function, initializing if needed."""
        if not hasattr(self, "_signer_function") or self._signer_function is None:
            self._sign_epi()
        return getattr(self, "_signer_function", None)
    def _get_runtime_metadata(self) -> Dict[str, Any]:
        """Capture environment metadata for full traceability."""
        import sys
        import platform
        return {
            "python_version": sys.version,
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "guardrails_version": self.guardrails_version,
            "spec_version": "1.1.0",
        }

    def _verify_completeness(self) -> Dict[str, Any]:
        """
        Independent completeness guarantee (Article 12).
        Detects if expected instrumentation events were missed.
        """
        # Count event types in self._steps
        types = [s.get("kind") for s in self._steps]
        subtypes = [s.get("content", {}).get("phase") for s in self._steps if s.get("kind") == "agent.step"]
        
        has_start = "start" in subtypes
        has_end = "end" in subtypes
        
        # 1. Sequence check (Detection of telemetry gaps)
        indices = [s.get("event_index", 0) for s in self._steps]
        if indices:
            is_sequential = all(indices[i] == indices[i-1] + 1 for i in range(1, len(indices)))
            missing_count = max(indices) - min(indices) + 1 - len(indices) if indices else 0
        else:
            is_sequential = True
            missing_count = 0

        # 2. Temporal Monotonicity (Clock Integrity)
        timestamps = [s.get("timestamp_ns", 0) for s in self._steps]
        is_time_monotonic = all(timestamps[i] >= timestamps[i-1] for i in range(1, len(timestamps))) if timestamps else True

        # 3. Semantic Completeness (Detection of silent omissions)
        iteration_steps = [
            s for s in self._steps 
            if s.get("kind") == "agent.step" and s.get("content", {}).get("subtype") == "guardrails"
        ]
        
        all_iterations_complete = all(s.get("content", {}).get("completed", False) for s in iteration_steps)
        
        # Check if every iteration actually HAS validators recorded
        # This prevents 'empty iterations' that look sequential but have no evidence
        iterations_with_evidence = all(len(s.get("content", {}).get("validators", [])) > 0 for s in iteration_steps)

        return {
            "traceability_status": "complete" if (has_start and has_end and all_iterations_complete and is_sequential and is_time_monotonic and iterations_with_evidence) else "partial",
            "start_event": has_start,
            "end_event": has_end,
            "all_iterations_complete": all_iterations_complete,
            "is_sequential": is_sequential,
            "is_time_monotonic": is_time_monotonic,
            "semantic_evidence_present": iterations_with_evidence,
            "missing_events_count": missing_count,
            "steps_count": len(self._steps),
        }
