"""
LangChain auto-instrumentation adapter for epi-recorder.

Provides ``EpiCallbackHandler`` — a LangChain ``BaseCallbackHandler`` that
logs LLM / tool / top-level chain events into an active epi-recorder session.

Optional dependency: ``langchain-core`` (``pip install epi-recorder[langchain]``).
This module must not be imported from ``epi_recorder.__init__``.

Usage::

    from epi_recorder import record
    from epi_recorder.adapters.langchain import EpiCallbackHandler

    with record("run.epi", goal="loan decision") as session:
        handler = EpiCallbackHandler(session)
        agent_executor.invoke({"input": "..."}, config={"callbacks": [handler]})
"""

from __future__ import annotations

import logging
import threading
import warnings
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

_logger = logging.getLogger(__name__)

# Optional: langchain-core (or legacy langchain). Never hard-require at package import.
try:
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError:  # pragma: no cover - exercised when langchain-core missing
    try:
        from langchain.callbacks.base import BaseCallbackHandler  # type: ignore
    except ImportError:
        class BaseCallbackHandler:  # type: ignore[no-redef]
            """Stub when LangChain is not installed."""

            raise_error: bool = False

        BaseCallbackHandler = BaseCallbackHandler  # noqa: F811


SessionLike = Any  # EpiRecorderSession or anything with .log / .log_step


def _run_id_str(run_id: Union[UUID, str, None]) -> str:
    if run_id is None:
        return ""
    return str(run_id)


def _component_name(serialized: Any, default: str = "unknown") -> str:
    if not isinstance(serialized, dict):
        return default
    kwargs = serialized.get("kwargs") or {}
    if not isinstance(kwargs, dict):
        kwargs = {}
    return (
        serialized.get("name")
        or kwargs.get("model_name")
        or kwargs.get("model")
        or (serialized.get("id") or [default])[-1]
        or default
    )


def _safe_str(value: Any, limit: int = 4000) -> str:
    try:
        text = value if isinstance(value, str) else str(value)
    except Exception:
        text = f"<unserializable:{type(value).__name__}>"
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _safe_mapping(data: Any, *, value_limit: int = 500) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"value": _safe_str(data, value_limit)}
    out: Dict[str, Any] = {}
    for key, val in data.items():
        k = str(key)
        try:
            if hasattr(val, "model_dump"):
                out[k] = val.model_dump()
            elif isinstance(val, (str, int, float, bool)) or val is None:
                out[k] = val if not isinstance(val, str) else _safe_str(val, value_limit)
            else:
                out[k] = _safe_str(val, value_limit)
        except Exception:
            out[k] = f"<unserializable:{type(val).__name__}>"
    return out


class EpiCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that writes forensic steps into an epi session.

    Parameters
    ----------
    session:
        Active ``EpiRecorderSession`` (from ``with record(...) as session``).
        Must expose ``log`` or ``log_step``.

    Notes
    -----
    - Prompt/response payloads go through the session's normal log path, which
      applies ``epi_core.redactor`` when the session was opened with redact=True.
    - Tool start always emits ``tool.call``; tool end *and* tool error both emit
      ``tool.response`` so AUD-CO-01 completeness stays PASS on failure paths.
    - Only top-level chains (``parent_run_id is None``) emit chain.start / chain.end.
    - LLM steps use kind ``llm.call`` (not ``llm.request``). AUD-CO-01 currently
      pairs ``llm.request`` only; tool completeness is fully covered via ``call_id``.
    """

    raise_error: bool = False  # never break the LangChain run

    def __init__(self, session: SessionLike) -> None:
        if session is None:
            raise ValueError("EpiCallbackHandler requires a non-None session")
        # Detect missing langchain after construction only when methods are used;
        # still allow instantiation so tests can monkeypatch without the dep.
        try:
            super().__init__()
        except TypeError:
            # Stub BaseCallbackHandler may not accept super()
            pass
        self._session = session
        self._lock = threading.Lock()
        self._log_error_warned = False
        # Internal maps keyed by run_id string (callbacks may fire on worker threads)
        self._tool_names: Dict[str, str] = {}
        self._llm_models: Dict[str, str] = {}

    # ------------------------------------------------------------------ logging

    def _log(self, kind: str, content: Dict[str, Any]) -> None:
        """Write a step via the session public API (redaction happens in core path)."""
        session = self._session
        if session is None:
            return
        # Prefer public ``log`` alias; fall back to ``log_step``.
        log_fn = getattr(session, "log", None) or getattr(session, "log_step", None)
        if log_fn is None:
            return
        try:
            log_fn(kind, content)
        except Exception as exc:
            # Never break the instrumented chain (default).
            if self.raise_error:
                raise
            _logger.debug("EpiCallbackHandler failed to log %s: %s", kind, exc, exc_info=True)
            import os as _os
            if _os.getenv("EPI_DEADLETTER", "0") == "1":
                try:
                    import json as _json
                    from pathlib import Path as _Path
                    p = _Path.cwd() / ".epi-deadletter.jsonl"
                    with open(p, "a", encoding="utf-8") as _f:
                        _f.write(_json.dumps({"kind": kind, "deadletter": True, "error": str(exc), "error_type": type(exc).__name__}) + "\n")
                except Exception:
                    pass
            if not self._log_error_warned:
                self._log_error_warned = True
                warnings.warn(
                    f"EpiCallbackHandler could not log step {kind!r} "
                    f"({type(exc).__name__}: {exc}). Further failures are debug-logged + deadletter. "
                    "Ensure the handler is used inside `with record(...) as session:`.",
                    RuntimeWarning,
                    stacklevel=2,
                )

    # ------------------------------------------------------------------ LLM

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        model = _component_name(serialized)
        rid = _run_id_str(run_id)
        with self._lock:
            self._llm_models[rid] = model
        # Cap prompts; redaction applied by session.log → RecordingContext
        prompt_list = list(prompts or [])[:8]
        self._log(
            "llm.call",
            {
                "model": model,
                "prompts": prompt_list,
                "run_id": rid,
                "provider": "langchain",
            },
        )

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Chat models fire this instead of on_llm_start; map to llm.call."""
        model = _component_name(serialized)
        rid = _run_id_str(run_id)
        with self._lock:
            self._llm_models[rid] = model
        # Flatten message batches into prompt-like strings for the llm.call schema
        prompts: List[str] = []
        for batch in messages or []:
            for msg in batch:
                if hasattr(msg, "content"):
                    prompts.append(_safe_str(getattr(msg, "content", ""), 2000))
                else:
                    prompts.append(_safe_str(msg, 2000))
        self._log(
            "llm.call",
            {
                "model": model,
                "prompts": prompts[:8],
                "run_id": rid,
                "provider": "langchain",
            },
        )

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        rid = _run_id_str(run_id)
        with self._lock:
            model = self._llm_models.pop(rid, None)

        generations_summary: List[str] = []
        token_usage: Optional[Dict[str, Any]] = None

        if hasattr(response, "generations"):
            try:
                for gen_list in response.generations or []:
                    for gen in gen_list:
                        text = getattr(gen, "text", None)
                        if text is None and hasattr(gen, "message"):
                            text = getattr(gen.message, "content", "")
                        generations_summary.append(_safe_str(text, 2000))
            except Exception:
                generations_summary.append(_safe_str(response, 2000))

        if hasattr(response, "llm_output") and isinstance(response.llm_output, dict):
            raw_usage = response.llm_output.get("token_usage") or response.llm_output.get(
                "usage"
            )
            if isinstance(raw_usage, dict):
                token_usage = {
                    k: raw_usage.get(k)
                    for k in (
                        "prompt_tokens",
                        "completion_tokens",
                        "total_tokens",
                        "input_tokens",
                        "output_tokens",
                    )
                    if raw_usage.get(k) is not None
                }

        payload: Dict[str, Any] = {
            "ok": True,
            "text": generations_summary[0] if len(generations_summary) == 1 else None,
            "generations": generations_summary,
            "run_id": rid,
            "provider": "langchain",
        }
        if model:
            payload["model"] = model
        if token_usage:
            payload["token_usage"] = token_usage
        # Drop None text when multi-gen
        if payload["text"] is None:
            payload.pop("text", None)

        self._log("llm.response", payload)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        rid = _run_id_str(run_id)
        with self._lock:
            model = self._llm_models.pop(rid, None)
        payload: Dict[str, Any] = {
            "ok": False,
            "error": str(error),
            "error_type": type(error).__name__,
            "run_id": rid,
            "provider": "langchain",
        }
        if model:
            payload["model"] = model
        self._log("llm.response", payload)

    # ------------------------------------------------------------------ tools

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        inputs: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        rid = _run_id_str(run_id)
        tool_name = _component_name(serialized, default="tool")
        with self._lock:
            self._tool_names[rid] = tool_name
        tool_input: Any = input_str
        if inputs is not None:
            tool_input = inputs
        self._log(
            "tool.call",
            {
                "tool": tool_name,
                "input": tool_input,
                "call_id": rid,  # AUD-CO-01 pairing key
                "run_id": rid,
            },
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        rid = _run_id_str(run_id)
        with self._lock:
            tool_name = self._tool_names.pop(rid, None)
        self._log(
            "tool.response",
            {
                "tool": tool_name,
                "output": output if not isinstance(output, (bytes, bytearray)) else _safe_str(output),
                "ok": True,
                "call_id": rid,
                "run_id": rid,
            },
        )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        rid = _run_id_str(run_id)
        with self._lock:
            tool_name = self._tool_names.pop(rid, None)
        self._log(
            "tool.response",
            {
                "tool": tool_name,
                "ok": False,
                "error": str(error),  # string only — no traceback objects
                "call_id": rid,
                "run_id": rid,
            },
        )

    # ------------------------------------------------------------------ chains (top-level only)

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        # Captured nested chains too (was early return) — include parent_run_id for trace
        name = _component_name(serialized, default="chain")
        self._log(
            "chain.start",
            {
                "chain": name,
                "name": name,
                "inputs": _safe_mapping(inputs),
                "run_id": _run_id_str(run_id),
                "parent_run_id": _run_id_str(parent_run_id) if parent_run_id else None,
                "is_nested": parent_run_id is not None,
            },
        )

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self._log(
            "chain.end",
            {
                "outputs": _safe_mapping(outputs),
                "run_id": _run_id_str(run_id),
                "parent_run_id": _run_id_str(parent_run_id) if parent_run_id else None,
                "is_nested": parent_run_id is not None,
            },
        )


__all__ = ["EpiCallbackHandler"]
