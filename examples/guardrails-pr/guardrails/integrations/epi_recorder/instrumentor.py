\
"""
guardrails.integrations.epi_recorder.instrumentor -- EPIInstrumentor

Hooks Guardrails AI execution and produces a signed .epi artifact
per Guard execution for offline compliance and audit.

Pattern: class-based Instrumentor (matching MLFlow / OpenInference).
"""

from __future__ import annotations

import logging
import os
import time as time_module
from importlib import import_module
from typing import Any, Callable

try:
    from wrapt import wrap_function_wrapper
    _HAS_WRAPT = True
except ImportError:
    _HAS_WRAPT = False

logger = logging.getLogger(__name__)


class EPIInstrumentor:
    """Instrument Guardrails AI to produce signed .epi artifacts.

    Call instrument() once at application startup. Every Guard
    execution from that point produces a tamper-evident, Ed25519-signed
    .epi file with the full validation timeline.

    Example::

        instrumentor = EPIInstrumentor()
        instrumentor.instrument()

        guard = Guard.from_rail("my.rail")
        result = guard(llm_api, prompt)

        instrumentor.uninstrument()
    """

    def __init__(
        self,
        output_path: str = "guardrails_run.epi",
        auto_sign: bool = True,
        redact: bool = True,
        goal: str | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
    ):
        self._output_path = os.environ.get("EPI_GUARDRAILS_OUTPUT", output_path)
        self._auto_sign = auto_sign
        self._redact = redact
        self._goal = goal
        self._notes = notes
        self._tags = tags or []
        self._originals: dict[str, Any] = {}
        self._instrumented = False

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def instrument(self) -> bool:
        if self._instrumented:
            return True
        if not _HAS_WRAPT:
            logger.error("wrapt not installed. Run: pip install wrapt")
            return False
        try:
            import guardrails  # noqa: F401
        except ImportError:
            logger.error("Guardrails AI not installed")
            return False

        self._hook("guardrails.guard", "Guard", "_execute", "Guard._execute",
                    lambda w, i, a, k: self._wrap_guard_execute(w, i, a, k))
        self._hook("guardrails.guard", "Guard", "_execute_async", "Guard._execute_async",
                    lambda w, i, a, k: self._wrap_guard_execute(w, i, a, k))
        if "Runner.step" not in self._originals:
            self._hook_wrapt("guardrails.run", "Runner.step", self._wrap_runner_step)
        if "StreamRunner.step" not in self._originals:
            self._hook_wrapt("guardrails.run", "StreamRunner.step", self._wrap_stream_runner_step)
        if "ValidatorServiceBase.after_run_validator" not in self._originals:
            self._hook_wrapt("guardrails.validator_service",
                             "ValidatorServiceBase.after_run_validator",
                             self._wrap_validator_after_run)
        if "Runner.call" not in self._originals:
            self._hook_wrapt("guardrails.run", "Runner.call", self._wrap_runner_call)

        self._instrumented = True
        logger.info("EPIInstrumentor: instrumented Guardrails")
        return True

    def uninstrument(self) -> None:
        for name, mod_name, cls_name in [
            ("Guard._execute", "guardrails.guard", "Guard"),
            ("Guard._execute_async", "guardrails.guard", "Guard"),
            ("AsyncGuard._execute", "guardrails.guard", "AsyncGuard"),
            ("Runner.step", "guardrails.run", "Runner"),
            ("StreamRunner.step", "guardrails.run", "StreamRunner"),
            ("ValidatorServiceBase.after_run_validator",
             "guardrails.validator_service", "ValidatorServiceBase"),
            ("Runner.call", "guardrails.run", "Runner"),
        ]:
            if name in self._originals:
                try:
                    cls1 = getattr(import_module(mod_name), cls_name, None)
                    if cls1:
                        setattr(cls1, name.split(".")[-1], self._originals[name])
                except Exception as exc:
                    logger.warning("uninstrument %s failed: %s", name, exc)
                del self._originals[name]
        self._instrumented = False

    # ------------------------------------------------------------------ #
    #  Wrappers
    # ------------------------------------------------------------------ #

    def _wrap_guard_execute(
        self, wrapped: Callable, instance: Any, args: tuple, kwargs: dict
    ) -> Any:
        """Wrap Guard._execute: create session -> call original -> finalize .epi."""
        from epi_recorder import record
        from epi_recorder.integrations.guardrails import GuardrailsRecorder

        guard_name = getattr(instance, "name", None) or "guardrails"

        with record(
            self._output_path,
            goal=self._goal or f"Guardrails: {guard_name}",
            tags=self._tags or [],
        ) as session:
            recorder = GuardrailsRecorder(session)
            result = wrapped(instance, *args, **kwargs)
            if hasattr(result, "validation_passed"):
                recorder.log_validation({
                    "outcome": "pass" if result.validation_passed else "fail",
                    "score": getattr(result, "score", None),
                    "errors": getattr(result, "errors", []),
                    "corrected_value": getattr(result, "corrected_output", None),
                })
            return result

    def _wrap_runner_step(
        self, wrapped: Callable, instance: Any, args: tuple, kwargs: dict
    ) -> Any:
        from epi_recorder.api import get_current_session
        session = get_current_session()
        if session is None:
            return wrapped(*args, **kwargs)
        idx = self._get_arg(wrapped, args, kwargs, "index", 0)
        session.log_tool_call(
            tool=f"Guardrails.step[{idx}]",
            input=str(kwargs.get("output", ""))[:500],
        )
        result = wrapped(*args, **kwargs)
        return result

    def _wrap_stream_runner_step(
        self, wrapped: Callable, instance: Any, args: tuple, kwargs: dict
    ) -> Any:
        from epi_recorder.api import get_current_session
        session = get_current_session()
        if session is None:
            return wrapped(*args, **kwargs)
        idx = self._get_arg(wrapped, args, kwargs, "index", 0)
        session.log(llm.call, {"provider": "guardrails", "model": "stream"})
        return wrapped(*args, **kwargs)

    def _wrap_validator_after_run(
        self, wrapped: Callable, instance: Any, args: tuple, kwargs: dict
    ) -> Any:
        result = wrapped(*args, **kwargs)
        validator = self._get_arg(wrapped, args, kwargs, "validator", None)
        name = getattr(validator, "rail_alias", "unknown") if validator else "unknown"
        from epi_recorder.api import get_current_session
        session = get_current_session()
        if session:
            session.log_validation(validator=f"guardrails.{name}", result="pass")
        return result

    def _wrap_runner_call(
        self, wrapped: Callable, instance: Any, args: tuple, kwargs: dict
    ) -> Any:
        from epi_recorder.api import get_current_session
        session = get_current_session()
        if session is None:
            return wrapped(*args, **kwargs)
        start = time_module.monotonic()
        result = wrapped(*args, **kwargs)
        latency = time_module.monotonic() - start
        if session:
            provider = getattr(result, "provider", "unknown") if result else "unknown"
            model = getattr(result, "model_id", "unknown") if result else "unknown"
            session.log_tool_call(
                tool=f"LLM:{provider}/{model}",
                input=str(kwargs.get("messages", ""))[:300],
            )
        return result

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _hook(self, mod: str, cls_name: str, attr: str, key: str, wrapper_fn):
        cls = self._get_class(mod, cls_name)
        if cls and hasattr(cls, attr) and key not in self._originals:
            self._originals[key] = getattr(cls, attr)
            setattr(cls, attr, self._make_bound_wrapper(key, wrapper_fn))

    def _hook_wrapt(self, mod: str, qualname: str, wrapper_fn):
        self._originals[qualname] = None
        wrap_function_wrapper(mod, qualname, wrapper_fn)

    @staticmethod
    def _get_class(mod: str, name: str):
        try:
            return getattr(import_module(mod), name, None)
        except Exception:
            return None

    def _make_bound_wrapper(self, key: str, fn: Callable):
        def _wrapper(inst, *a, **kw):
            return fn(self._originals.get(key), inst, a, kw)
        _wrapper.__name__ = f"{key}_epi"
        return _wrapper

    @staticmethod
    def _get_arg(wrapped, args, kwargs, name, default=None):
        if name in kwargs:
            return kwargs[name]
        try:
            import inspect
            sig = inspect.signature(wrapped)
            for i, (p, _) in enumerate(sig.parameters.items()):
                if p == name and i < len(args):
                    return args[i]
        except Exception:
            pass
        return default
