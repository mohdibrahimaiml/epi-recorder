"""
Guardrails Integration for EPI Recorder

Provides a hook/callback to automatically log Guardrails validation
outcomes to the active EPI recording session.

Usage:
    from epi_recorder import record
    from epi_recorder.integrations.guardrails import GuardrailsRecorder

    with record("agent.epi") as epi:
        recorder = GuardrailsRecorder(epi)

        # Run Guardrails validation
        result = guard.validate(output)

        # Log the outcome
        recorder.log_validation(result)
"""

from typing import Any, Dict, Optional

from epi_recorder.api import EpiRecorderSession, get_current_session


class GuardrailsRecorder:
    """
    Hook for Guardrails validation outcomes.

    Receives validation results and logs them as EPI validation steps.
    """

    def __init__(self, session: Optional[EpiRecorderSession] = None):
        """
        Initialize Guardrails recorder.

        Args:
            session: EpiRecorderSession. If None, uses get_current_session().
        """
        self.session = session

    def log_validation(self, result: Dict[str, Any]) -> None:
        """
        Log a Guardrails validation result.

        Args:
            result: Dictionary with Guardrails validation result structure:
                {
                    "outcome": "pass"|"fail"|"corrected",
                    "guards": [...],
                    "score": 0.95,
                    "errors": [...],
                    "corrected_value": ...
                }

        Example:
            result = guard.validate("Hello world")
            recorder.log_validation(result)
        """
        session = self.session or get_current_session()
        if not session:
            return  # Not recording; silently skip

        # Map Guardrails outcome to EPI result type
        gr_outcome = result.get("outcome", "unknown")
        epi_result = {
            "pass": "pass",
            "fail": "fail",
            "corrected": "corrected",
        }.get(gr_outcome, "warning")

        # Extract score if available
        score = result.get("score")
        if score is None and "errors" in result:
            # Rough heuristic: presence of errors → lower score
            score = 0.0 if result["errors"] else 1.0

        # Collect details
        details = {}
        if "errors" in result and result["errors"]:
            details["errors"] = result["errors"]
        if "guards" in result and result["guards"]:
            details["guards_triggered"] = result["guards"]
        if "corrected_value" in result:
            details["corrected_value"] = str(result["corrected_value"])[:200]  # Truncate for safety

        # Log via session API
        session.log_validation(
            validator="guardrails",
            result=epi_result,
            score=score,
            details=details if details else None
        )
