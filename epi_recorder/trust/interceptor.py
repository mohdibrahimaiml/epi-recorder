"""
TrustInterceptor — Wraps agent tools and functions with runtime policy enforcement.

Intercepts tool calls at the Python function boundary, evaluates policies,
and can block, redact, or quarantine before execution.
"""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Dict, List, Optional

from epi_recorder.trust.engine import (
    EnforcementAction,
    RuntimePolicyEngine,
    TrustEnforcementError,
    Violation,
)


class TrustInterceptor:
    """
    Wraps callable tools with policy evaluation.

    Usage:
        engine = RuntimePolicyEngine("epi_policy.json", enable_blocking=True)
        interceptor = TrustInterceptor(engine)

        # Wrap a tool function
        safe_search = interceptor.wrap_tool(search_fn, "search")
        result = safe_search(query="...")  # Blocked if policy denies "search"
    """

    def __init__(self, engine: RuntimePolicyEngine):
        self.engine = engine
        self._wrapped_tools: Dict[str, Callable] = {}

    def wrap_tool(
        self,
        fn: Callable,
        tool_name: str,
        *,
        on_violation: Callable[[Violation], Any] | None = None,
    ) -> Callable:
        """
        Wrap a tool function with policy enforcement.

        Args:
            fn: The original tool function/coroutine.
            tool_name: The registered name of the tool (used for policy lookup).
            on_violation: Optional callback invoked for every violation.

        Returns:
            A wrapped function that enforces policy before calling fn.
        """
        if inspect.iscoroutinefunction(fn):
            return self._wrap_async_tool(fn, tool_name, on_violation)
        return self._wrap_sync_tool(fn, tool_name, on_violation)

    def _wrap_sync_tool(
        self,
        fn: Callable,
        tool_name: str,
        on_violation: Callable[[Violation], Any] | None,
    ) -> Callable:
        @functools.wraps(fn)
        def guarded(*args, **kwargs):
            # Build context for policy evaluation
            context = {"tool": tool_name, "input": self._build_input_context(args, kwargs, fn)}

            # Evaluate policy BEFORE execution
            action, violations = self.engine.evaluate("tool_call", context)

            if violations and on_violation:
                for v in violations:
                    on_violation(v)

            # Handle enforcement actions
            if action == EnforcementAction.BLOCK:
                if violations:
                    raise TrustEnforcementError(violations[0])
                raise TrustEnforcementError(
                    type("V", (), {
                        "rule_id": "TRUST-BLOCK",
                        "rule_name": "Tool Blocked",
                        "severity": "critical",
                        "reason": f"Tool '{tool_name}' blocked by policy",
                    })()
                )

            if action == EnforcementAction.REQUIRE_APPROVAL:
                # Approval must be handled by caller; we raise so caller knows
                if violations:
                    raise TrustEnforcementError(violations[0])

            # Execute the tool
            result = fn(*args, **kwargs)

            # Post-execution evaluation (constraint guards on result)
            result_context = {
                "tool": tool_name,
                "input": context["input"],
                "output": result,
            }
            post_action, post_violations = self.engine.evaluate("tool_response", result_context)

            if post_violations and on_violation:
                for v in post_violations:
                    on_violation(v)

            # Record sequence actions for sequence_guard tracking
            self.engine.record_sequence_action(tool_name)

            return result

        return guarded

    def _wrap_async_tool(
        self,
        fn: Callable,
        tool_name: str,
        on_violation: Callable[[Violation], Any] | None,
    ) -> Callable:
        @functools.wraps(fn)
        async def guarded(*args, **kwargs):
            context = {"tool": tool_name, "input": self._build_input_context(args, kwargs, fn)}

            action, violations = self.engine.evaluate("tool_call", context)

            if violations and on_violation:
                for v in violations:
                    on_violation(v)

            if action == EnforcementAction.BLOCK:
                if violations:
                    raise TrustEnforcementError(violations[0])
                raise TrustEnforcementError(
                    type("V", (), {
                        "rule_id": "TRUST-BLOCK",
                        "rule_name": "Tool Blocked",
                        "severity": "critical",
                        "reason": f"Tool '{tool_name}' blocked by policy",
                    })()
                )

            if action == EnforcementAction.REQUIRE_APPROVAL:
                if violations:
                    raise TrustEnforcementError(violations[0])

            result = await fn(*args, **kwargs)

            result_context = {
                "tool": tool_name,
                "input": context["input"],
                "output": result,
            }
            post_action, post_violations = self.engine.evaluate("tool_response", result_context)

            if post_violations and on_violation:
                for v in post_violations:
                    on_violation(v)

            self.engine.record_sequence_action(tool_name)
            return result

        return guarded

    def wrap_all_tools(
        self,
        tools: Dict[str, Callable],
        *,
        on_violation: Callable[[Violation], Any] | None = None,
    ) -> Dict[str, Callable]:
        """Wrap an entire dict of tool functions."""
        return {
            name: self.wrap_tool(fn, name, on_violation=on_violation)
            for name, fn in tools.items()
        }

    def _build_input_context(
        self, args: tuple, kwargs: dict, fn: Callable
    ) -> dict:
        """Build a context dict from function arguments."""
        try:
            sig = inspect.signature(fn)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            return dict(bound.arguments)
        except Exception:
            return {"args": list(args), "kwargs": dict(kwargs)}
