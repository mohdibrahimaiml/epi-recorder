"""
epi_guardrails.step_types — TypedDict definitions for Guardrails-specific EPI steps.

These map Guardrails execution concepts onto EPI step kinds while preserving
Guardrails-specific fields for downstream policy analysis and human review.
"""

from __future__ import annotations

from typing import Any, Dict, List, NotRequired
from typing_extensions import TypedDict


class GuardExecutionStartContent(TypedDict):
    """Payload for guardrails.execution.start."""

    event_index: int
    timestamp_ns: int
    guard: Dict[str, Any]
    guardrails_version: str
    trace_id: str
    session_id: str
    prompt: NotRequired[str]
    metadata: NotRequired[Dict[str, Any]]


class GuardExecutionEndContent(TypedDict, total=False):
    """Content for a ``guardrails.execution.end`` step."""

    guard_name: str
    session_id: str
    success: bool
    duration_seconds: float
    iterations_count: int
    llm_calls_count: int
    final_output_hash: NotRequired[str]
    exception_type: NotRequired[str]
    exception_message: NotRequired[str]


class GuardrailsIterationContent(TypedDict, total=False):
    """Content for a ``guardrails.iteration`` step."""

    iteration_index: int
    trace_id: str
    prompt_hash: NotRequired[str]
    raw_output: NotRequired[str]
    validated_output: NotRequired[str]
    validation_passed: bool
    validators_run: NotRequired[List[str]]
    correction_applied: bool


class LLMCallContent(TypedDict, total=False):
    """Content for a ``guardrails.llm.call`` step — records LLM calls inside Guard."""

    provider: str
    model: str
    messages: List[Dict[str, Any]]
    system: NotRequired[str]
    temperature: NotRequired[float]
    max_tokens: NotRequired[int]
    choices: NotRequired[List[Dict[str, Any]]]
    usage: NotRequired[Dict[str, int]]
    latency_seconds: NotRequired[float]
    error: NotRequired[str]


class ValidatorResultContent(TypedDict, total=False):
    """Content for a ``guardrails.validator.result`` step."""

    validator_name: str
    rail_alias: str
    status: str  # "pass" | "fail" | "error"
    corrected: bool
    error: NotRequired[str]
    value: NotRequired[Any]
    parsed: NotRequired[Any]


class GuardrailsStepContent(TypedDict, total=False):
    """
    Content for a ``guardrails.step`` step — a single Guardrails iteration step
    with all validator results attached.

    This is the primary step type emitted by the instrumentor.
    """

    step_index: int
    iteration_index: int
    trace_id: str

    # LLM call (if any)
    llm_call: NotRequired[LLMCallContent]

    # Validation
    validators: List[Dict[str, Any]]
    validation_passed: bool
    correction_applied: bool
    final_output: NotRequired[str]

    # Timing
    duration_seconds: NotRequired[float]
    timestamp: NotRequired[str]


class InputValidationContent(TypedDict, total=False):
    """Content for a ``guardrails.input.validation`` step."""

    input_hash: str
    validated_input: NotRequired[Any]
    validation_passed: bool
    validators_run: List[str]


class OutputValidationContent(TypedDict, total=False):
    """Content for a ``guardrails.output.validation`` step."""

    output_hash: str
    validated_output: NotRequired[Any]
    validation_passed: bool
    validators_run: List[str]
    correction_applied: bool
