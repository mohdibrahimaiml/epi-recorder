"""
epi_recorder.step_types — TypedDict definitions for EPI step content.

These types give IDE auto-complete and static analysis support when calling
``session.log_step(kind, content)``.  They are optional — plain dicts work
fine — but using them surfaces typos and missing fields at development time.

Example::

    from epi_recorder.step_types import LLMRequestContent, ToolCallContent

    session.log_step("llm.request", LLMRequestContent(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
    ))
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import NotRequired, TypedDict


# ---------------------------------------------------------------------------
# LLM steps
# ---------------------------------------------------------------------------

class LLMRequestContent(TypedDict, total=False):
    """Content for a ``llm.request`` step."""
    provider: str           # "openai" | "anthropic" | "gemini" | …
    model: str              # "gpt-4o" | "claude-3-5-sonnet-20241022" | …
    messages: List[Dict[str, Any]]  # OpenAI-style message list
    system: NotRequired[str]        # Anthropic-style system prompt
    temperature: NotRequired[float]
    max_tokens: NotRequired[int]
    top_p: NotRequired[float]
    stream: NotRequired[bool]
    timestamp: NotRequired[str]


class LLMResponseContent(TypedDict, total=False):
    """Content for a ``llm.response`` step."""
    provider: str
    model: str
    choices: List[Dict[str, Any]]   # [{"message": {"role": …, "content": …}, "finish_reason": …}]
    usage: NotRequired[Dict[str, int]]   # {"prompt_tokens": …, "completion_tokens": …, "total_tokens": …}
    latency_seconds: NotRequired[float]
    cost_usd: NotRequired[float]
    stream: NotRequired[bool]
    timestamp: NotRequired[str]


class LLMErrorContent(TypedDict, total=False):
    """Content for a ``llm.error`` step."""
    provider: str
    model: str
    error: str
    error_type: str
    latency_seconds: NotRequired[float]
    timestamp: NotRequired[str]


# ---------------------------------------------------------------------------
# Tool steps
# ---------------------------------------------------------------------------

class ToolCallContent(TypedDict, total=False):
    """Content for a ``tool.call`` step."""
    tool: str               # Tool / function name
    input: NotRequired[Any] # Arguments passed to the tool
    call_id: NotRequired[str]
    timestamp: NotRequired[str]


class ToolResponseContent(TypedDict, total=False):
    """Content for a ``tool.response`` step."""
    tool: str
    output: NotRequired[Any]    # Return value / result
    status: str                 # "success" | "error"
    call_id: NotRequired[str]
    timestamp: NotRequired[str]


# ---------------------------------------------------------------------------
# Agent steps
# ---------------------------------------------------------------------------

class AgentRunStartContent(TypedDict, total=False):
    """Content for an ``agent.run.start`` step."""
    agent_name: str
    agent_type: NotRequired[str]
    user_input: NotRequired[Any]
    goal: NotRequired[str]
    session_id: NotRequired[str]
    task_id: NotRequired[str]
    run_id: NotRequired[str]
    attempt: NotRequired[int]
    timestamp: NotRequired[str]


class AgentRunEndContent(TypedDict, total=False):
    """Content for an ``agent.run.end`` step."""
    agent_name: str
    success: bool
    duration_seconds: NotRequired[float]
    timestamp: NotRequired[str]


class AgentDecisionContent(TypedDict, total=False):
    """Content for an ``agent.decision`` step."""
    decision: str
    output: NotRequired[Any]
    confidence: NotRequired[float]  # 0.0 – 1.0
    rationale: NotRequired[str]
    review_required: NotRequired[bool]
    timestamp: NotRequired[str]


class AgentMessageContent(TypedDict, total=False):
    """Content for an ``agent.message`` step."""
    role: str           # "user" | "assistant" | "system"
    content: Any
    timestamp: NotRequired[str]


class AgentApprovalRequestContent(TypedDict, total=False):
    """Content for an ``agent.approval.request`` step."""
    action: str
    reason: NotRequired[str]
    risk_level: NotRequired[str]    # "low" | "medium" | "high"
    requested_by: NotRequired[str]
    timestamp: NotRequired[str]


class AgentApprovalResponseContent(TypedDict, total=False):
    """Content for an ``agent.approval.response`` step."""
    action: str
    approved: bool
    reviewer: NotRequired[str]
    notes: NotRequired[str]
    timestamp: NotRequired[str]


class AgentHandoffContent(TypedDict, total=False):
    """Content for an ``agent.handoff`` step."""
    from_agent: str
    to_agent: str
    reason: NotRequired[str]
    timestamp: NotRequired[str]


class AgentMemoryReadContent(TypedDict, total=False):
    """Content for an ``agent.memory.read`` step."""
    memory_key: str
    query: NotRequired[str]
    result_count: NotRequired[int]
    timestamp: NotRequired[str]


class AgentMemoryWriteContent(TypedDict, total=False):
    """Content for an ``agent.memory.write`` step."""
    memory_key: str
    value: NotRequired[Any]
    operation: NotRequired[str]     # "set" | "append" | "delete"
    destination: NotRequired[str]
    timestamp: NotRequired[str]


# ---------------------------------------------------------------------------
# Convenience re-export
# ---------------------------------------------------------------------------

__all__ = [
    "LLMRequestContent",
    "LLMResponseContent",
    "LLMErrorContent",
    "ToolCallContent",
    "ToolResponseContent",
    "AgentRunStartContent",
    "AgentRunEndContent",
    "AgentDecisionContent",
    "AgentMessageContent",
    "AgentApprovalRequestContent",
    "AgentApprovalResponseContent",
    "AgentHandoffContent",
    "AgentMemoryReadContent",
    "AgentMemoryWriteContent",
]
