"""
EPI Recorder Integration for Guardrails AI
===========================================

Produces tamper-evident, cryptographically signed .epi artifacts from
Guardrails validation executions. One artifact per Guard execution.
"""

from guardrails.integrations.epi_recorder.instrumentor import EPIInstrumentor

__all__ = ["EPIInstrumentor"]
__version__ = "1.0.0"
