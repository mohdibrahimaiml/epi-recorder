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
    """Wraps callable tools with policy evaluation.

    With a configured :class:`~epi_recorder.trust.approval.ApprovalGate`, a
    REQUIRE_APPROVAL rule does not just raise: the gate builds a signed
    pre-action request, waits for a pinned approver to sign that exact call,
    verifies it, and only then lets the tool run. ``approval.request``,
    ``approval.response`` and ``approval.executed`` are written to the active
    recording session (or persisted to the approvals inbox when there is none).
    """

    def __init__(
        self,
        engine: RuntimePolicyEngine,
        *,
        gate: Any | None = None,
        step_sink: Any | None = None,
        release_ref: dict[str, Any] | None = None,
        workflow_id: str | None = None,
    ):
        self.engine = engine
        self.gate = gate
        self._step_sink = step_sink
        self._release_ref = release_ref
        self._workflow_id = workflow_id
        self._wrapped_tools: Dict[str, Callable] = {}

    def _context(self, tool_name: str, args: tuple, kwargs: dict, fn: Callable) -> dict:
        return {
            "tool": tool_name,
            "input": self._build_input_context(args, kwargs, fn),
        }

    def _rule(self, violations: list[Violation]) -> dict[str, Any] | None:
        if not violations:
            return None
        return violations[0].to_dict()

    def _request_grant(self, tool_name: str, context: dict, violations: list[Violation]):
        from epi_recorder.trust.approval import PreActionApprovalBlocked

        if self.gate is None:
            if violations:
                raise TrustEnforcementError(violations[0])
            raise TrustEnforcementError(
                type("V", (), {
                    "rule_id": "TRUST-APPROVAL",
                    "rule_name": "Approval Required",
                    "severity": "critical",
                    "reason": f"Tool '{tool_name}' requires approval and no approval gate is configured",
                })()
            )
        from epi_recorder.trust.context import current_step_sink

        sink = self._step_sink or current_step_sink()
        gate = self.gate
        if sink is not None and getattr(gate, "_step_sink", None) is None:
            try:
                gate._step_sink = sink
            except Exception:
                pass
        release_ref = self._release_ref
        if release_ref is None and sink is not None:
            release_ref = getattr(sink, "release_ref", None)
        workflow_id = self._workflow_id or (
            getattr(sink, "case_id", None) if sink is not None else None
        )
        return gate, release_ref, workflow_id

    def _run_gated_sync(self, tool_name: str, context: dict, violations: list[Violation], fn: Callable, args: tuple, kwargs: dict):
        gate, release_ref, workflow_id = self._request_grant(tool_name, context, violations)
        grant = gate.request_signed(
            tool=tool_name,
            arguments=context["input"],
            reason=(violations[0].reason if violations else ""),
            rule=self._rule(violations),
            release_ref=release_ref,
            workflow_id=workflow_id,
            vendor_description=(violations[0].reason if violations else None),
        )
        grant.release(arguments=context["input"])
        return fn(*args, **kwargs)

    async def _run_gated_async(self, tool_name: str, context: dict, violations: list[Violation], fn: Callable, args: tuple, kwargs: dict):
        gate, release_ref, workflow_id = self._request_grant(tool_name, context, violations)
        grant = await gate.async_request_signed(
            tool=tool_name,
            arguments=context["input"],
            reason=(violations[0].reason if violations else ""),
            rule=self._rule(violations),
            release_ref=release_ref,
            workflow_id=workflow_id,
            vendor_description=(violations[0].reason if violations else None),
        )
        grant.release(arguments=context["input"])
        return await fn(*args, **kwargs)

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
                gate, release_ref, workflow_id = self._request_grant(
                    tool_name, context, violations
                )
                grant = gate.request_signed(
                    tool=tool_name,
                    arguments=context["input"],
                    reason=(violations[0].reason if violations else ""),
                    rule=self._rule(violations),
                    release_ref=release_ref,
                    workflow_id=workflow_id,
                    vendor_description=(violations[0].reason if violations else None),
                )
                grant.release(arguments=context["input"])

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
                gate, release_ref, workflow_id = self._request_grant(
                    tool_name, context, violations
                )
                grant = await gate.async_request_signed(
                    tool=tool_name,
                    arguments=context["input"],
                    reason=(violations[0].reason if violations else ""),
                    rule=self._rule(violations),
                    release_ref=release_ref,
                    workflow_id=workflow_id,
                    vendor_description=(violations[0].reason if violations else None),
                )
                grant.release(arguments=context["input"])

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
