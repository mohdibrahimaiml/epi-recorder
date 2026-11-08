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
from epi_recorder.trust.approval import (
    ApprovalGate,
    ApprovalRequiredError,
    ApprovalTicket,
    PreActionApprovalBlocked,
    PreActionGrant,
)
from epi_recorder.trust.context import (
    current_step_sink,
    reset_step_sink,
    set_step_sink,
)

__all__ = [
    "EnforcementAction",
    "RuntimePolicyEngine",
    "TrustInterceptor",
    "ApprovalGate",
    "ApprovalRequiredError",
    "ApprovalTicket",
    "PreActionApprovalBlocked",
    "PreActionGrant",
    "current_step_sink",
    "set_step_sink",
    "reset_step_sink",
]
