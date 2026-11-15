"""
Analytics module for EPI Recorder

Provides tools to analyze agent performance across multiple runs.

``AgentAnalytics`` is defined in ``epi_recorder.analytics`` (package ``__init__``).
This module re-exports it for backward-compatible imports:
``from epi_recorder.analytics.engine import AgentAnalytics``.
"""

from __future__ import annotations

from typing import Any

# AgentAnalytics is provided lazily by __getattr__ below, so static analysis
# cannot see it as defined here. The export is deliberate.
__all__ = ["AgentAnalytics"]  # noqa: F822


def __getattr__(name: str) -> Any:
    if name == "AgentAnalytics":
        # Import package (defines AgentAnalytics in __init__.py) without circular self-import.
        from epi_recorder.analytics import AgentAnalytics as _AgentAnalytics

        return _AgentAnalytics
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
