"""
epi_guardrails — EPI Recorder integration for Guardrails AI.

Produces tamper-evident, cryptographically signed .epi artifacts from Guardrails
validation executions. One .epi artifact per Guard execution.

Usage:
    from epi_guardrails import instrument, uninstrument

    # Instrument Guardrails (once at app startup)
    instrument(output_path="my_run.epi", goal="Validate LLM output")

    # Run Guardrails as normal
    guard = Guard.from_rail("my.rail")
    response = guard(llm_api, prompt)
    # → my_run.epi is produced automatically

    # When done (optional)
    uninstrument()

Step kinds produced:
  - guardrails.execution.start    — session metadata
  - guardrails.step               — each iteration / validation loop
  - guardrails.llm.call           — LLM calls inside Guard
  - guardrails.validator.result   — individual validator outcomes
  - guardrails.execution.end       — session close + outcome
"""

from epi_guardrails.instrumentor import instrument, uninstrument
from epi_guardrails.session import GuardrailsRecorderSession
from epi_guardrails.state import GuardrailsEPIState, guardrails_epi_state
from epi_guardrails.step_types import (
    GuardExecutionEndContent,
    GuardExecutionStartContent,
    GuardrailsIterationContent,
    GuardrailsStepContent,
    InputValidationContent,
    LLMCallContent,
    OutputValidationContent,
    ValidatorResultContent,
)

__all__ = [
    # Main API
    "instrument",
    "uninstrument",
    # Session
    "GuardrailsRecorderSession",
    # State
    "GuardrailsEPIState",
    "guardrails_epi_state",
    # Step types
    "GuardExecutionStartContent",
    "GuardExecutionEndContent",
    "GuardrailsStepContent",
    "GuardrailsIterationContent",
    "LLMCallContent",
    "ValidatorResultContent",
    "InputValidationContent",
    "OutputValidationContent",
]

__version__ = "1.0.0"
