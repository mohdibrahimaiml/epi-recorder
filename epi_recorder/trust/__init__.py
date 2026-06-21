"""
EPI Trust Layer — Runtime policy enforcement for AI agents.

Transforms EPI from a post-hoc evidence system into an active trust layer
that intercepts, evaluates, and enforces policies at runtime.

Usage:
    with record("agent.epi", enforce_trust=True) as epi:
        with epi.agent_run("my-agent") as agent:
            # tool calls are automatically permission-checked
            agent.tool_call("search", {"query": "..."})
"""

from __future__ import annotations

from epi_recorder.trust.engine import EnforcementAction, RuntimePolicyEngine
from epi_recorder.trust.interceptor import TrustInterceptor

__all__ = [
    "EnforcementAction",
    "RuntimePolicyEngine",
    "TrustInterceptor",
]
