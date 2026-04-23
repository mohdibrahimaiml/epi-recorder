"""
epi_guardrails.state — Thread-safe and async-safe state management.

Provides:
  - GuardrailsEPIState: immutable session snapshot for passing via contextvars
  - Iteration stack: contextvars-based tracking of current iteration_id per session
  - Thread-local fallback for non-async contexts

NO global mutable state. Every piece of state is either:
  - contextvars.ContextVar (async-safe, task-local)
  - threading.local (thread fallback)
"""

from __future__ import annotations

import contextvars
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = [
    "GuardrailsEPIState",
    "guardrails_epi_state",
    "set_guardrails_epi_state",
    "reset_guardrails_epi_state",
    "push_iteration_id",
    "pop_iteration_id",
    "current_iteration_id",
    # Unified helpers (kept for backward compat, now thin wrappers over contextvars only)
    "get_current_iteration_id",
    "push_current_iteration_id",
    "pop_current_iteration_id",
]


# ==============================================================================
# GuardrailsEPIState — session-level state snapshot
# ==============================================================================


@dataclass
class GuardrailsEPIState:
    """
    Immutable-ish snapshot of the in-progress Guardrails EPI recording.

    Passed via contextvars so async tasks and threads can access session state
    without needing a global variable.
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    guard_name: Optional[str] = None
    guardrails_version: Optional[str] = None

    # Monotonic event counter for ordering — increment per event
    event_index: int = 0

    # Per-execution counters
    iterations_count: int = 0
    llm_calls_count: int = 0

    # Integrity hashes (set during input/output validation)
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None

    # Outcome
    exception_raised: bool = False

    # Back-reference to parent session (set by GuardrailsRecorderSession.__enter__)
    # Used by instrumentor to find session from state without global state
    _session_ref: Any = field(default=None, repr=False)

    def next_event_index(self) -> int:
        """Return next monotonic event index. Thread-safe via GIL (ints are atomic)."""
        idx = self.event_index
        self.event_index += 1
        return idx


# ==============================================================================
# Iteration ID stack — contextvars (async-safe, task-local)
# ==============================================================================

# Primary: contextvars (async-safe, task-local)
_iteration_stack_var: contextvars.ContextVar[list[str]] = contextvars.ContextVar(
    "guardrails_iteration_stack",
    default=None,
)


def _get_iteration_stack() -> list[str]:
    """Get or create the iteration stack for current context."""
    stack = _iteration_stack_var.get()
    if stack is None:
        stack = []
        _iteration_stack_var.set(stack)
    return stack


def push_iteration_id(iteration_id: str) -> None:
    """Push an iteration_id onto the current context's stack."""
    stack = _get_iteration_stack()
    stack.append(iteration_id)


def pop_iteration_id() -> Optional[str]:
    """Pop the top iteration_id from the current context's stack."""
    stack = _get_iteration_stack()
    if stack:
        return stack.pop()
    return None


def current_iteration_id() -> Optional[str]:
    """Return the current iteration_id (top of stack) without popping."""
    stack = _get_iteration_stack()
    if stack:
        return stack[-1]
    return None


# ==============================================================================
# Thread-local fallback (for sync thread-pool executors)
# ==============================================================================

_thread_local_iteration_stack = threading.local()


def _get_thread_iteration_stack() -> list:
    if not hasattr(_thread_local_iteration_stack, "stack"):
        _thread_local_iteration_stack.stack = []
    return _thread_local_iteration_stack.stack


def _push_thread_iteration_id(iteration_id: str) -> None:
    _get_thread_iteration_stack().append(iteration_id)


def _pop_thread_iteration_id() -> Optional[str]:
    stack = _get_thread_iteration_stack()
    if stack:
        return stack.pop()
    return None


def _current_thread_iteration_id() -> Optional[str]:
    stack = _get_thread_iteration_stack()
    if stack:
        return stack[-1]
    return None


# ==============================================================================
# Unified helpers — contextvars ONLY (single source of truth)
#
# We deliberately do NOT maintain a thread-local iteration_id stack.
# Rationale:
#   contextvars.ContextVar is the correct primitive for both async tasks
#   and native threads (Python copies context into new threads via
#   copy_context()). A parallel thread-local stack creates two sources
#   of truth that diverge under ThreadPoolExecutor, causing validator
#   results to be attached to the wrong step.
#
# The only thread-local state we keep is the GuardrailsEPIState session
# pointer (below), which is needed for thread pools that do NOT inherit
# the parent context. iteration_id does not need this because validators
# always run in the same context as the step that pushed the id.
# ==============================================================================

def get_current_iteration_id() -> Optional[str]:
    """Get current iteration_id from contextvars (single source)."""
    return current_iteration_id()


def push_current_iteration_id(iteration_id: str) -> None:
    """Push iteration_id onto the contextvars stack."""
    push_iteration_id(iteration_id)


def pop_current_iteration_id() -> Optional[str]:
    """Pop iteration_id from the contextvars stack."""
    return pop_iteration_id()


# ==============================================================================
# Session state — contextvars + thread-local
# ==============================================================================

_guardrails_state_var: contextvars.ContextVar[Optional[GuardrailsEPIState]] = (
    contextvars.ContextVar("guardrails_epi_state", default=None)
)
_thread_local_state = threading.local()


def _get_thread_state_stack() -> list:
    """Get or create the state stack for thread-local fallback."""
    if not hasattr(_thread_local_state, "stack"):
        _thread_local_state.stack = []
    return _thread_local_state.stack


def guardrails_epi_state() -> Optional[GuardrailsEPIState]:
    """
    Get current GuardrailsEPIState — checks contextvars first, then thread-local.
    Returns None when no Guardrails EPI session is active.
    """
    ctx_state = _guardrails_state_var.get()
    if ctx_state is not None:
        return ctx_state
        
    stack = _get_thread_state_stack()
    if stack:
        return stack[-1]
    return None


def set_guardrails_epi_state(state: GuardrailsEPIState) -> contextvars.Token:
    """
    Push new GuardrailsEPIState in BOTH contextvars AND thread-local stack.
    Returns the contextvars.Token for restoring the previous state.
    """
    stack = _get_thread_state_stack()
    stack.append(state)
    
    return _guardrails_state_var.set(state)


def reset_guardrails_epi_state(token: contextvars.Token) -> None:
    """
    Restore previous state using the contextvars.Token and pop thread-local stack.
    """
    _guardrails_state_var.reset(token)
    
    stack = _get_thread_state_stack()
    if stack:
        stack.pop()
