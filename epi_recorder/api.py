"""
EPI Recorder Python API - User-friendly library interface.

Provides a context manager for recording EPI packages programmatically
with minimal code changes.
"""

import asyncio
import functools
import json
import os
import shutil
import sys
import threading
import warnings
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Optional, TextIO, Union
from uuid import uuid4

from epi_core.container import EPIContainer
from epi_core.policy import EPIPolicy
from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now, utc_now_iso
from epi_core.workspace import RecordingWorkspaceError, create_recording_workspace
from epi_recorder.patcher import (
    RecordingContext,
    get_recording_context,
    set_recording_context,
)
from epi_recorder.environment import capture_full_environment


# Thread-local storage for active recording sessions
_thread_local = threading.local()

_RESERVED_ARCHIVE_ROOT_NAMES = {
    "mimetype",
    "manifest.json",
    "viewer.html",
    "steps.jsonl",
    "environment.json",
    "env.json",
    "analysis.json",
    "policy.json",
    "policy_evaluation.json",
    "review.json",
    "stdout.log",
    "stderr.log",
}


def _normalize_archive_path(archive_path: str) -> str:
    candidate = (archive_path or "").strip().replace("\\", "/")
    pure = PurePosixPath(candidate)

    if not candidate or pure == PurePosixPath("."):
        raise ValueError("archive_path must not be empty")

    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise ValueError("archive_path must be a relative path inside the .epi archive")

    if pure.parts and ":" in pure.parts[0]:
        raise ValueError("archive_path must not include a drive prefix")

    if pure.parts and pure.parts[0] in _RESERVED_ARCHIVE_ROOT_NAMES:
        raise ValueError(
            f"archive_path root '{pure.parts[0]}' is reserved by the EPI container; "
            "store custom files under a non-reserved path such as artifacts/ or evidence/"
        )

    return pure.as_posix()


def _warn_if_local_policy_invalid(search_dir: Path | None = None) -> None:
    policy_path = (search_dir or Path.cwd()) / "epi_policy.json"
    if not policy_path.exists():
        return
    try:
        EPIPolicy.model_validate(json.loads(policy_path.read_text(encoding="utf-8")))
    except Exception as exc:
        warnings.warn(
            f"epi_policy.json is invalid and will be ignored: {exc}. Run `epi policy validate` to fix it.",
            stacklevel=3,
        )


class _StdStreamCapture:
    """Tee stdout/stderr to console while logging printable lines as EPI steps."""

    def __init__(self, session: "EpiRecorderSession", stream: TextIO, stream_name: str):
        self._session = session
        self._stream = stream
        self._stream_name = stream_name
        self._buffer = ""

    def write(self, data: str) -> int:
        text = data if isinstance(data, str) else str(data)
        written = self._stream.write(text)
        self._buffer += text

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emit_line(line.rstrip("\r"))
        return written

    def flush(self) -> None:
        self._stream.flush()

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return bool(getattr(self._stream, "isatty", lambda: False)())

    def fileno(self) -> int:
        return self._stream.fileno()

    @property
    def encoding(self) -> Optional[str]:
        return getattr(self._stream, "encoding", None)

    @property
    def errors(self) -> Optional[str]:
        return getattr(self._stream, "errors", None)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._stream, item)

    def emit_pending(self) -> None:
        if self._buffer:
            self._emit_line(self._buffer.rstrip("\r"))
            self._buffer = ""

    def _emit_line(self, line: str) -> None:
        if not line.strip():
            return

        payload: Dict[str, Any] = {
            "stream": self._stream_name,
            "text": line,
            "timestamp": utc_now_iso(),
        }
        try:
            parsed = json.loads(line)
            if isinstance(parsed, (dict, list)):
                payload["parsed"] = parsed
        except Exception:
            pass

        try:
            self._session.log_step("stdout.print", payload)
        except Exception as _log_err:
            # Never break user stdout writes because step logging failed.
            # But warn once so the developer knows evidence is not being captured.
            if not getattr(self, "_log_warn_sent", False):
                self._log_warn_sent = True
                self._stream.write(
                    f"\n[EPI] Warning: step logging failed ({_log_err}). "
                    "Evidence capture may be incomplete. "
                    "Check disk space and file permissions.\n"
                )


def _compact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Drop None values while preserving falsy-but-meaningful fields like False or 0."""
    return {key: value for key, value in payload.items() if value is not None}


class AgentRun:
    """
    High-level helper for recording AI-agent execution as readable EPI steps.

    This gives agent developers a stable, product-shaped surface:

        with record("agent.epi") as epi:
            with epi.agent_run("refund-agent", user_input="Refund order 123") as agent:
                agent.message("user", "Refund order 123")
                agent.tool_call("lookup_order", {"order_id": "123"})
                agent.tool_result("lookup_order", {"status": "paid"})
                agent.decision("approve_refund", confidence=0.94)

    The helper intentionally reuses EPI's existing step kinds where that helps
    downstream policy/fault analysis (`tool.call`, `tool.response`) while adding
    agent-specific context for the viewer and human review experience.
    """

    def __init__(
        self,
        step_logger: Callable[[str, Dict[str, Any]], None],
        async_step_logger: Callable[[str, Dict[str, Any]], Any],
        agent_name: str,
        *,
        agent_type: str = "agent",
        user_input: Optional[Any] = None,
        goal: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        attempt: int = 1,
        resume_from: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self._step_logger = step_logger
        self._async_step_logger = async_step_logger
        self.agent_name = agent_name
        self.agent_type = agent_type
        self.user_input = user_input
        self.goal = goal
        self.session_id = session_id or str(uuid4())
        self.task_id = task_id or str(uuid4())
        self.parent_run_id = parent_run_id
        self.attempt = attempt
        self.resume_from = resume_from
        self.metadata = metadata or {}
        self.run_id = str(uuid4())
        self.started_at: Optional[datetime] = None
        self._entered = False

    def _payload(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = dict(self.metadata)
        payload.update(
            {
                "agent_name": self.agent_name,
                "agent_type": self.agent_type,
                "session_id": self.session_id,
                "task_id": self.task_id,
                "run_id": self.run_id,
                "parent_run_id": self.parent_run_id,
                "attempt": self.attempt,
                "resume_from": self.resume_from,
                "timestamp": utc_now_iso(),
            }
        )
        if extra:
            payload.update(extra)
        return _compact_payload(payload)

    def _log(self, kind: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self._step_logger(kind, self._payload(payload))

    async def _alog(self, kind: str, payload: Optional[Dict[str, Any]] = None) -> None:
        await self._async_step_logger(kind, self._payload(payload))

    def start(self) -> "AgentRun":
        if self._entered:
            raise RuntimeError("AgentRun cannot be re-entered")

        self._entered = True
        self.started_at = utc_now()
        self._log(
            "agent.run.start",
            {
                "user_input": self.user_input,
                "goal": self.goal,
            },
        )
        return self

    async def astart(self) -> "AgentRun":
        if self._entered:
            raise RuntimeError("AgentRun cannot be re-entered")

        self._entered = True
        self.started_at = utc_now()
        await self._alog(
            "agent.run.start",
            {
                "user_input": self.user_input,
                "goal": self.goal,
            },
        )
        return self

    def plan(self, summary: str, *, steps: Optional[List[str]] = None, **metadata: Any) -> None:
        self._log("agent.plan", {"summary": summary, "steps": steps, **metadata})

    async def aplan(self, summary: str, *, steps: Optional[List[str]] = None, **metadata: Any) -> None:
        await self._alog("agent.plan", {"summary": summary, "steps": steps, **metadata})

    def finish(self, success: bool = True, **metadata: Any) -> None:
        duration = None
        if self.started_at is not None:
            duration = (utc_now() - self.started_at).total_seconds()

        self._log(
            "agent.run.end",
            {
                "success": success,
                "duration_seconds": duration,
                **metadata,
            },
        )

    async def afinish(self, success: bool = True, **metadata: Any) -> None:
        duration = None
        if self.started_at is not None:
            duration = (utc_now() - self.started_at).total_seconds()

        await self._alog(
            "agent.run.end",
            {
                "success": success,
                "duration_seconds": duration,
                **metadata,
            },
        )

    def message(self, role: str, content: Any, **metadata: Any) -> None:
        self._log("agent.message", {"role": role, "content": content, **metadata})

    async def amessage(self, role: str, content: Any, **metadata: Any) -> None:
        await self._alog("agent.message", {"role": role, "content": content, **metadata})

    def tool_call(self, tool: str, tool_input: Optional[Any] = None, **metadata: Any) -> None:
        self._log("tool.call", {"tool": tool, "input": tool_input, **metadata})

    async def atool_call(self, tool: str, tool_input: Optional[Any] = None, **metadata: Any) -> None:
        await self._alog("tool.call", {"tool": tool, "input": tool_input, **metadata})

    def tool_result(
        self,
        tool: str,
        output: Optional[Any] = None,
        *,
        status: str = "success",
        **metadata: Any,
    ) -> None:
        self._log(
            "tool.response",
            {
                "tool": tool,
                "output": output,
                "status": status,
                **metadata,
            },
        )

    async def atool_result(
        self,
        tool: str,
        output: Optional[Any] = None,
        *,
        status: str = "success",
        **metadata: Any,
    ) -> None:
        await self._alog(
            "tool.response",
            {
                "tool": tool,
                "output": output,
                "status": status,
                **metadata,
            },
        )

    def decision(
        self,
        decision: str,
        *,
        output: Optional[Any] = None,
        confidence: Optional[float] = None,
        rationale: Optional[str] = None,
        review_required: Optional[bool] = None,
        **metadata: Any,
    ) -> None:
        self._log(
            "agent.decision",
            {
                "decision": decision,
                "output": output,
                "confidence": confidence,
                "rationale": rationale,
                "review_required": review_required,
                **metadata,
            },
        )

    async def adecision(
        self,
        decision: str,
        *,
        output: Optional[Any] = None,
        confidence: Optional[float] = None,
        rationale: Optional[str] = None,
        review_required: Optional[bool] = None,
        **metadata: Any,
    ) -> None:
        await self._alog(
            "agent.decision",
            {
                "decision": decision,
                "output": output,
                "confidence": confidence,
                "rationale": rationale,
                "review_required": review_required,
                **metadata,
            },
        )

    def approval_request(
        self,
        action: str,
        *,
        reason: Optional[str] = None,
        risk_level: Optional[str] = None,
        requested_by: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        self._log(
            "agent.approval.request",
            {
                "action": action,
                "reason": reason,
                "risk_level": risk_level,
                "requested_by": requested_by or self.agent_name,
                **metadata,
            },
        )

    async def aapproval_request(
        self,
        action: str,
        *,
        reason: Optional[str] = None,
        risk_level: Optional[str] = None,
        requested_by: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        await self._alog(
            "agent.approval.request",
            {
                "action": action,
                "reason": reason,
                "risk_level": risk_level,
                "requested_by": requested_by or self.agent_name,
                **metadata,
            },
        )

    def approval_response(
        self,
        action: str,
        *,
        approved: bool,
        reviewer: Optional[str] = None,
        notes: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        self._log(
            "agent.approval.response",
            {
                "action": action,
                "approved": approved,
                "reviewer": reviewer,
                "notes": notes,
                **metadata,
            },
        )

    async def aapproval_response(
        self,
        action: str,
        *,
        approved: bool,
        reviewer: Optional[str] = None,
        notes: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        await self._alog(
            "agent.approval.response",
            {
                "action": action,
                "approved": approved,
                "reviewer": reviewer,
                "notes": notes,
                **metadata,
            },
        )

    def handoff(self, to_agent: str, *, reason: Optional[str] = None, **metadata: Any) -> None:
        self._log(
            "agent.handoff",
            {
                "from_agent": self.agent_name,
                "to_agent": to_agent,
                "reason": reason,
                **metadata,
            },
        )

    async def ahandoff(self, to_agent: str, *, reason: Optional[str] = None, **metadata: Any) -> None:
        await self._alog(
            "agent.handoff",
            {
                "from_agent": self.agent_name,
                "to_agent": to_agent,
                "reason": reason,
                **metadata,
            },
        )

    def memory_read(
        self,
        memory_key: str,
        *,
        query: Optional[str] = None,
        source: Optional[str] = None,
        result_count: Optional[int] = None,
        value: Optional[Any] = None,
        **metadata: Any,
    ) -> None:
        self._log(
            "agent.memory.read",
            {
                "memory_key": memory_key,
                "query": query,
                "source": source,
                "result_count": result_count,
                "value": value,
                **metadata,
            },
        )

    async def amemory_read(
        self,
        memory_key: str,
        *,
        query: Optional[str] = None,
        source: Optional[str] = None,
        result_count: Optional[int] = None,
        value: Optional[Any] = None,
        **metadata: Any,
    ) -> None:
        await self._alog(
            "agent.memory.read",
            {
                "memory_key": memory_key,
                "query": query,
                "source": source,
                "result_count": result_count,
                "value": value,
                **metadata,
            },
        )

    def memory_write(
        self,
        memory_key: str,
        value: Optional[Any] = None,
        *,
        operation: str = "set",
        destination: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        self._log(
            "agent.memory.write",
            {
                "memory_key": memory_key,
                "value": value,
                "operation": operation,
                "destination": destination,
                **metadata,
            },
        )

    async def amemory_write(
        self,
        memory_key: str,
        value: Optional[Any] = None,
        *,
        operation: str = "set",
        destination: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        await self._alog(
            "agent.memory.write",
            {
                "memory_key": memory_key,
                "value": value,
                "operation": operation,
                "destination": destination,
                **metadata,
            },
        )

    def state(self, state: str, **metadata: Any) -> None:
        self._log("agent.state", {"state": state, **metadata})

    async def astate(self, state: str, **metadata: Any) -> None:
        await self._alog("agent.state", {"state": state, **metadata})

    def pause(self, *, reason: Optional[str] = None, waiting_for: Optional[str] = None, **metadata: Any) -> None:
        self._log(
            "agent.run.pause",
            {
                "reason": reason,
                "waiting_for": waiting_for,
                **metadata,
            },
        )

    async def apause(self, *, reason: Optional[str] = None, waiting_for: Optional[str] = None, **metadata: Any) -> None:
        await self._alog(
            "agent.run.pause",
            {
                "reason": reason,
                "waiting_for": waiting_for,
                **metadata,
            },
        )

    def resume(self, *, reason: Optional[str] = None, resumed_from: Optional[str] = None, **metadata: Any) -> None:
        self._log(
            "agent.run.resume",
            {
                "reason": reason,
                "resumed_from": resumed_from or self.resume_from,
                **metadata,
            },
        )

    async def aresume(self, *, reason: Optional[str] = None, resumed_from: Optional[str] = None, **metadata: Any) -> None:
        await self._alog(
            "agent.run.resume",
            {
                "reason": reason,
                "resumed_from": resumed_from or self.resume_from,
                **metadata,
            },
        )

    def error(self, error: Union[str, BaseException], **metadata: Any) -> None:
        if isinstance(error, BaseException):
            payload = {
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
        else:
            payload = {
                "error_type": "AgentError",
                "error_message": str(error),
            }
        payload.update(metadata)
        self._log("agent.run.error", payload)

    async def aerror(self, error: Union[str, BaseException], **metadata: Any) -> None:
        if isinstance(error, BaseException):
            payload = {
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
        else:
            payload = {
                "error_type": "AgentError",
                "error_message": str(error),
            }
        payload.update(metadata)
        await self._alog("agent.run.error", payload)

    def __enter__(self) -> "AgentRun":
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            if exc_val is not None:
                self.error(exc_val)
            else:
                self._log(
                    "agent.run.error",
                    {
                        "error_type": getattr(exc_type, "__name__", "AgentError"),
                        "error_message": f"Exception of type {getattr(exc_type, '__name__', 'AgentError')} raised with no value",
                    },
                )
        self.finish(success=exc_type is None)
        return False

    async def __aenter__(self) -> "AgentRun":
        return await self.astart()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            if exc_val is not None:
                await self.aerror(exc_val)
            else:
                await self._alog(
                    "agent.run.error",
                    {
                        "error_type": getattr(exc_type, "__name__", "AgentError"),
                        "error_message": f"Exception of type {getattr(exc_type, '__name__', 'AgentError')} raised with no value",
                    },
                )
        await self.afinish(success=exc_type is None)
        return False


class EpiRecorderSession:
    """
    Context manager for recording EPI packages.
    
    Usage:
        with EpiRecorderSession("my_run.epi", workflow_name="Demo") as epi:
            # Your AI code here - automatically recorded
            response = openai.chat.completions.create(...)
            
            # Optional manual logging
            epi.log_step("custom.event", {"data": "value"})
            epi.log_artifact(Path("output.txt"))
    """
    
    def __init__(
        self,
        output_path: Path | str,
        workflow_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        auto_sign: bool = True,
        redact: bool = True,
        default_key_name: str = "default",
        # New metadata fields
        goal: Optional[str] = None,
        notes: Optional[str] = None,
        metrics: Optional[Dict[str, Union[float, str]]] = None,
        approved_by: Optional[str] = None,
        metadata_tags: Optional[List[str]] = None,  # Renamed to avoid conflict with tags parameter
        # Legacy mode (deprecated)
        legacy_patching: bool = False,
        capture_prints: bool = True,
        capture_stderr: bool = False,
    ):
        """
        Initialize EPI recording session.
        
        Args:
            output_path: Path for output .epi file
            workflow_name: Descriptive name for this workflow
            tags: Optional tags for categorization
            auto_sign: Whether to automatically sign on exit (default: True)
            redact: Whether to redact secrets (default: True)
            default_key_name: Name of key to use for signing (default: "default")
            goal: Goal or objective of this workflow execution
            notes: Additional notes or context about this workflow
            metrics: Key-value metrics for this workflow (accuracy, latency, etc.)
            approved_by: Person or entity who approved this workflow execution
            metadata_tags: Tags for categorizing this workflow (renamed from tags to avoid conflict)
            legacy_patching: Enable deprecated monkey patching mode (default: False)
        """
        self.output_path = Path(output_path)
        self.workflow_name = workflow_name or "untitled"
        self.tags = tags or []
        self.auto_sign = auto_sign
        self.redact = redact
        self.default_key_name = default_key_name
        
        # New metadata fields
        self.goal = goal
        self.notes = notes
        self.metrics = metrics
        self.approved_by = approved_by
        self.metadata_tags = metadata_tags
        
        # Legacy mode flag (deprecated)
        self.legacy_patching = legacy_patching
        self.capture_prints = capture_prints
        self.capture_stderr = capture_stderr
        
        # Runtime state
        self.temp_dir: Optional[Path] = None
        self.recording_context: Optional[RecordingContext] = None
        self.start_time: Optional[datetime] = None
        self._entered = False
        self._stdout_capture: Optional[_StdStreamCapture] = None
        self._stderr_capture: Optional[_StdStreamCapture] = None
        self._original_stdout: Optional[TextIO] = None
        self._original_stderr: Optional[TextIO] = None
        
    def __enter__(self) -> "EpiRecorderSession":
        """
        Enter the recording context.
        
        Sets up temporary directory, initializes recording context,
        and patches LLM libraries.
        """
        if self._entered:
            raise RuntimeError("EpiRecorderSession cannot be re-entered")
        
        self._entered = True
        self.start_time = utc_now()
        
        try:
            # Create temporary directory for recording
            self.temp_dir = create_recording_workspace("epi_recording_")

            _warn_if_local_policy_invalid()

            # Initialize recording context
            self.recording_context = RecordingContext(
                output_dir=self.temp_dir,
                enable_redaction=self.redact
            )
        except RecordingWorkspaceError:
            if self.temp_dir and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            self._entered = False
            raise
        
        # Set as active recording context
        set_recording_context(self.recording_context)
        _thread_local.active_session = self
        
        # Only patch LLM libraries if legacy mode is enabled (deprecated)
        if self.legacy_patching:
            import warnings
            warnings.warn(
                "legacy_patching is deprecated and will be removed in the next major release. "
                "Use epi.log_llm_call() or wrapper clients (wrap_openai) instead.",
                DeprecationWarning,
                stacklevel=2
            )
            from epi_recorder.patcher import patch_all
            patch_all()
        
        # Log session start
        self.log_step("session.start", {
            "workflow_name": self.workflow_name,
            "tags": self.tags,
            "timestamp": self.start_time.isoformat()
        })

        if self.capture_prints:
            self._install_stdio_capture()
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the recording context (sync version).
        
        Finalizes recording, captures environment, packs .epi file,
        and signs it if auto_sign is enabled.
        """
        try:
            # Capture environment snapshot BEFORE session.end
            self._capture_environment()
            
            # Log exception if one occurred (before session.end)
            if exc_type is not None:
                self.log_step("session.error", {
                    "error_type": exc_type.__name__,
                    "error_message": str(exc_val),
                    "timestamp": utc_now_iso()
                })
            
            # Log session end LAST to ensure it's the final step
            end_time = utc_now()
            duration = (end_time - self.start_time).total_seconds()
            
            self.log_step("session.end", {
                "timestamp": end_time.isoformat(),
                "duration_seconds": duration,
                "success": exc_type is None
            })
            
            # Finalize SQLite storage → export steps.jsonl before packing
            if self.recording_context:
                self.recording_context.finalize()

            # Create manifest with metadata
            manifest = ManifestModel(
                created_at=self.start_time,
                goal=self.goal,
                notes=self.notes,
                metrics=self.metrics,
                approved_by=self.approved_by,
                tags=self.metadata_tags
            )

            # Pack into .epi file
            EPIContainer.pack(
                source_dir=self.temp_dir,
                manifest=manifest,
                output_path=self.output_path
            )

            # Sign if requested
            signed = False
            if self.auto_sign:
                signed = self._sign_epi_file()

            self._print_session_summary(signed)

        finally:
            self._restore_stdio_capture()
            # Clean up temporary directory
            if self.temp_dir and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)

            # Clear recording context
            set_recording_context(None)
            if hasattr(_thread_local, 'active_session'):
                delattr(_thread_local, 'active_session')

    # ==================== ASYNC CONTEXT MANAGER SUPPORT ====================
    
    async def __aenter__(self) -> "EpiRecorderSession":
        """
        Enter the recording context (async version).
        
        Identical to __enter__ but async-compatible for use with
        'async with' statements in async agent frameworks.
        """
        # Reuse sync __enter__ logic (no I/O, just setup)
        return self.__enter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the recording context (async version).
        
        Async-compatible version of __exit__ for modern agent frameworks.
        Uses run_in_executor for I/O operations to avoid blocking.
        """
        try:
            loop = asyncio.get_running_loop()

            # Capture environment snapshot BEFORE session.end
            await loop.run_in_executor(None, self._capture_environment)

            # Log exception if one occurred (before session.end)
            if exc_type is not None:
                self.log_step("session.error", {
                    "error_type": exc_type.__name__,
                    "error_message": str(exc_val),
                    "timestamp": utc_now_iso()
                })

            # Log session end LAST to ensure it's the final step
            end_time = utc_now()
            duration = (end_time - self.start_time).total_seconds()

            self.log_step("session.end", {
                "timestamp": end_time.isoformat(),
                "duration_seconds": duration,
                "success": exc_type is None
            })

            # Finalize SQLite storage → export steps.jsonl before packing
            if self.recording_context:
                await loop.run_in_executor(None, self.recording_context.finalize)

            # Create manifest with metadata
            manifest = ManifestModel(
                created_at=self.start_time,
                goal=self.goal,
                notes=self.notes,
                metrics=self.metrics,
                approved_by=self.approved_by,
                tags=self.metadata_tags
            )

            # Pack into .epi file (run in executor to avoid blocking)
            await loop.run_in_executor(
                None,
                EPIContainer.pack,
                self.temp_dir,
                manifest,
                self.output_path
            )

            # Sign if requested (run in executor)
            signed = False
            if self.auto_sign:
                signed = await loop.run_in_executor(None, self._sign_epi_file)

            self._print_session_summary(signed)

        finally:
            self._restore_stdio_capture()
            # Clean up temporary directory
            if self.temp_dir and self.temp_dir.exists():
                await asyncio.get_running_loop().run_in_executor(
                    None,
                    shutil.rmtree,
                    self.temp_dir,
                    True  # ignore_errors
                )
            
            # Clear recording context
            set_recording_context(None)
            if hasattr(_thread_local, 'active_session'):
                delattr(_thread_local, 'active_session')
    
    def _install_stdio_capture(self) -> None:
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        self._stdout_capture = _StdStreamCapture(self, self._original_stdout, "stdout")
        self._stderr_capture = None
        if self.capture_stderr:
            self._stderr_capture = _StdStreamCapture(self, self._original_stderr, "stderr")
        sys.stdout = self._stdout_capture
        if self._stderr_capture is not None:
            sys.stderr = self._stderr_capture

    def _restore_stdio_capture(self) -> None:
        if self._stdout_capture:
            self._stdout_capture.emit_pending()
        if self._stderr_capture:
            self._stderr_capture.emit_pending()
        if self._original_stdout is not None:
            sys.stdout = self._original_stdout
        if self._stderr_capture is not None and self._original_stderr is not None:
            sys.stderr = self._original_stderr
        self._stdout_capture = None
        self._stderr_capture = None
        self._original_stdout = None
        self._original_stderr = None
    
    def log_step(self, kind: str, content: Dict[str, Any]) -> None:
        """
        Manually log a custom step.
        
        Args:
            kind: Step type (e.g., "custom.calculation", "user.action")
            content: Step data as dictionary
            
        Example:
            epi.log_step("data.processed", {
                "rows": 1000,
                "columns": 5,
                "output": "results.csv"
            })
        """
        if not self._entered:
            raise RuntimeError("Cannot log step outside of context manager")
        
        self.recording_context.add_step(kind, content)
    
    async def alog_step(self, kind: str, content: Dict[str, Any]) -> None:
        """
        Async version of log_step for async agent frameworks.
        
        Args:
            kind: Step type
            content: Step data as dictionary
        """
        # Logging is CPU-bound, not I/O-bound, so just call sync version
        self.log_step(kind, content)

    def agent_run(
        self,
        agent_name: str,
        *,
        agent_type: str = "agent",
        user_input: Optional[Any] = None,
        goal: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        attempt: int = 1,
        resume_from: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentRun:
        """
        Create a high-level agent-run helper for AI systems and agent frameworks.

        Example:
            with record("refund.epi") as epi:
                with epi.agent_run("refund-agent", user_input="Refund order 123") as agent:
                    agent.message("user", "Refund order 123")
                    agent.tool_call("lookup_order", {"order_id": "123"})
                    agent.tool_result("lookup_order", {"status": "paid"})
                    agent.decision("approve_refund", confidence=0.93)
        """
        if not self._entered:
            raise RuntimeError("Cannot create agent run outside of context manager")

        return AgentRun(
            self.log_step,
            self.alog_step,
            agent_name,
            agent_type=agent_type,
            user_input=user_input,
            goal=goal,
            session_id=session_id,
            task_id=task_id,
            parent_run_id=parent_run_id,
            attempt=attempt,
            resume_from=resume_from,
            metadata=metadata,
        )

    def agent(
        self,
        agent_name: str,
        *,
        agent_type: str = "agent",
        user_input: Optional[Any] = None,
        goal: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        attempt: int = 1,
        resume_from: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentRun:
        """Alias for agent_run() to keep agent code concise."""
        return self.agent_run(
            agent_name,
            agent_type=agent_type,
            user_input=user_input,
            goal=goal,
            session_id=session_id,
            task_id=task_id,
            parent_run_id=parent_run_id,
            attempt=attempt,
            resume_from=resume_from,
            metadata=metadata,
        )
    
    def log_llm_request(self, model: str, payload: Dict[str, Any]) -> None:
        """
        Log an LLM API request.
        
        Args:
            model: Model name (e.g., "gpt-4")
            payload: Request payload
            
        Note:
            This is typically called automatically by patchers.
            Manual use is for custom integrations.
        """
        self.log_step("llm.request", {
            "provider": "custom",
            "model": model,
            "timestamp": utc_now_iso(),
            **payload
        })
    
    def log_llm_response(self, response_payload: Dict[str, Any]) -> None:
        """
        Log an LLM API response.
        
        Args:
            response_payload: Response data
            
        Note:
            This is typically called automatically by patchers.
            Manual use is for custom integrations.
        """
        self.log_step("llm.response", {
            "timestamp": utc_now_iso(),
            **response_payload
        })
    
    def log_llm_call(
        self, 
        response: Any, 
        messages: Optional[List[Dict[str, str]]] = None,
        provider: str = "auto"
    ) -> None:
        """
        Log a complete LLM call (request + response) from any provider.
        
        Auto-detects OpenAI, Anthropic, and Gemini response objects.
        This is the RECOMMENDED way to log LLM calls without monkey patching.
        
        Args:
            response: The LLM response object (OpenAI, Anthropic, Gemini, etc.)
            messages: Optional original messages (for request logging)
            provider: Provider name ("auto" to detect, or "openai", "anthropic", etc.)
            
        Example:
            with record("my_agent.epi") as epi:
                response = client.chat.completions.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": "Hello"}]
                )
                epi.log_llm_call(response, messages=[{"role": "user", "content": "Hello"}])
        """
        if not self._entered:
            raise RuntimeError("Cannot log LLM call outside of context manager")
        
        # Auto-detect provider and extract data
        model = "unknown"
        content = ""
        usage = None
        choices = []
        
        # Try OpenAI format
        if hasattr(response, "choices") and hasattr(response, "model"):
            provider = "openai" if provider == "auto" else provider
            model = getattr(response, "model", "unknown")
            
            for choice in response.choices:
                msg = choice.message
                choices.append({
                    "message": {
                        "role": getattr(msg, "role", "assistant"),
                        "content": getattr(msg, "content", ""),
                    },
                    "finish_reason": getattr(choice, "finish_reason", None),
                })
                if not content:
                    content = getattr(msg, "content", "")
            
            if hasattr(response, "usage") and response.usage:
                usage = {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                    "total_tokens": getattr(response.usage, "total_tokens", 0),
                }
        
        # Try Anthropic format
        elif hasattr(response, "content") and hasattr(response, "model"):
            provider = "anthropic" if provider == "auto" else provider
            model = getattr(response, "model", "unknown")
            
            # Anthropic returns content as a list of content blocks
            content_blocks = getattr(response, "content", [])
            if content_blocks and hasattr(content_blocks[0], "text"):
                content = content_blocks[0].text
            choices = [{"message": {"role": "assistant", "content": content}}]
            
            if hasattr(response, "usage"):
                usage = {
                    "input_tokens": getattr(response.usage, "input_tokens", 0),
                    "output_tokens": getattr(response.usage, "output_tokens", 0),
                }
        
        # Try Gemini format
        elif hasattr(response, "text") and hasattr(response, "candidates"):
            provider = "gemini" if provider == "auto" else provider
            model = "gemini"
            content = getattr(response, "text", "")
            choices = [{"message": {"role": "assistant", "content": content}}]
        
        # Fallback: try to extract as dict or string
        else:
            provider = provider if provider != "auto" else "unknown"
            if isinstance(response, dict):
                content = str(response.get("content", response))
            else:
                content = str(response)
            choices = [{"message": {"role": "assistant", "content": content}}]
        
        # Log request if messages provided
        if messages:
            self.log_step("llm.request", {
                "provider": provider,
                "model": model,
                "messages": messages,
                "timestamp": utc_now_iso(),
            })
        
        # Log response
        response_data = {
            "provider": provider,
            "model": model,
            "choices": choices,
            "timestamp": utc_now_iso(),
        }
        if usage:
            response_data["usage"] = usage
        
        self.log_step("llm.response", response_data)
    
    def log_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        response_content: str,
        provider: str = "custom",
        usage: Optional[Dict[str, int]] = None,
        **metadata
    ) -> None:
        """
        Simplified logging for chat completions.
        
        Use this when you have the raw data instead of response objects.
        
        Args:
            model: Model name (e.g., "gpt-4", "claude-3")
            messages: The messages sent to the model
            response_content: The assistant's response text
            provider: Provider name (default: "custom")
            usage: Optional token usage dict
            **metadata: Additional metadata to include
            
        Example:
            epi.log_chat(
                model="gpt-4",
                messages=[{"role": "user", "content": "Hello"}],
                response_content="Hi there!",
                tokens=150
            )
        """
        if not self._entered:
            raise RuntimeError("Cannot log chat outside of context manager")
        
        # Log request
        self.log_step("llm.request", {
            "provider": provider,
            "model": model,
            "messages": messages,
            "timestamp": utc_now_iso(),
            **metadata
        })
        
        # Log response
        response_data = {
            "provider": provider,
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": response_content}}],
            "timestamp": utc_now_iso(),
        }
        if usage:
            response_data["usage"] = usage
        
        self.log_step("llm.response", response_data)
    
    def log_artifact(
        self,
        file_path: Path,
        archive_path: Optional[str] = None
    ) -> None:
        """
        Log a file artifact.
        
        Copies the file into the recording's artifacts directory.
        
        Args:
            file_path: Path to file to capture
            archive_path: Optional path within .epi archive (default: artifacts/<filename>)
            
        Example:
            # Capture output file
            with open("results.json", "w") as f:
                json.dump(data, f)
            
            epi.log_artifact(Path("results.json"))
        """
        if not self._entered:
            raise RuntimeError("Cannot log artifact outside of context manager")
        
        if not file_path.exists():
            raise FileNotFoundError(f"Artifact file not found: {file_path}")
        
        # Determine archive path
        if archive_path is None:
            archive_path = f"artifacts/{file_path.name}"
        archive_path = _normalize_archive_path(archive_path)

        # Copy file to the path inside the workspace that matches archive_path
        dest_path = self.temp_dir.joinpath(*PurePosixPath(archive_path).parts)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest_path)
        
        # Log artifact step
        self.log_step("artifact.captured", {
            "source_path": str(file_path),
            "archive_path": archive_path,
            "size_bytes": file_path.stat().st_size,
            "timestamp": utc_now_iso()
        })
    
    # ---- Internal step kinds that are not meaningful to show in the summary ----
    _INTERNAL_STEP_KINDS = frozenset({
        "session.start", "session.end", "session.error",
        "environment.captured", "environment.capture_failed",
        "security.redaction",
    })

    def _print_session_summary(self, signed: bool) -> None:
        """Print a concise post-run summary to stderr."""
        if os.getenv("EPI_QUIET", "0") == "1":
            return

        counts = {}
        if self.recording_context:
            counts = dict(self.recording_context._step_counts)

        # Filter out infrastructure-only kinds for the count
        user_counts = {k: v for k, v in counts.items() if k not in self._INTERNAL_STEP_KINDS}
        total_user_steps = sum(user_counts.values())

        # Build a short breakdown of the most meaningful kinds
        DISPLAY_GROUPS = [
            ("llm", ["llm.response", "llm.request", "llm.error"]),
            ("tool", ["tool.call", "tool.response"]),
            ("decision", ["agent.decision"]),
            ("message", ["agent.message"]),
            ("approval", ["agent.approval.request", "agent.approval.response"]),
            ("print", ["stdout.print", "stderr.print"]),
        ]
        parts = []
        shown_kinds: set = set()
        for label, kinds in DISPLAY_GROUPS:
            group_count = sum(user_counts.get(k, 0) for k in kinds)
            shown_kinds.update(kinds)
            if group_count:
                parts.append(f"{group_count}x {label}")

        # Any remaining user-defined kinds
        remaining = {k: v for k, v in user_counts.items() if k not in shown_kinds}
        if remaining:
            other_total = sum(remaining.values())
            parts.append(f"{other_total}x custom")

        trust = "Signed \u2713" if signed else "Unsigned"
        path_str = str(self.output_path)

        # Print to the real stderr (may have been swapped during capture)
        target = self._original_stderr if self._original_stderr is not None else sys.stderr
        print(f"\n[EPI] {total_user_steps} steps \u2192 {path_str}  {trust}", file=target)
        if parts:
            breakdown = " \u00b7 ".join(parts)
            print(f"      {breakdown}", file=target)
        print(f"      epi view {self.output_path.name}\n", file=target)

    def _capture_environment(self) -> None:
        """Capture environment snapshot and save to temp directory."""
        try:
            env_data = capture_full_environment()
            env_file = self.temp_dir / "environment.json"
            env_file.write_text(json.dumps(env_data, indent=2), encoding="utf-8")
            
            # Log environment capture
            self.log_step("environment.captured", {
                "platform": env_data.get("os", {}).get("platform"),
                "python_version": env_data.get("python", {}).get("version"),
                "timestamp": utc_now_iso()
            })
        except Exception as e:
            # Non-fatal: log but continue
            self.log_step("environment.capture_failed", {
                "error": str(e),
                "timestamp": utc_now_iso()
            })
    
    def _sign_epi_file(self) -> bool:
        """Sign the .epi file with default key. Returns True if signed successfully."""
        try:
            from epi_cli.keys import KeyManager
            from epi_core.trust import sign_manifest
            
            # Load key manager
            km = KeyManager()
            
            # Check if default key exists
            if not km.has_key(self.default_key_name):
                # Try to generate default key
                try:
                    km.generate_keypair(self.default_key_name)
                except Exception:
                    # If generation fails, skip signing
                    return False
            
            # Load private key
            private_key = km.load_private_key(self.default_key_name)
            
            # Extract, sign, and repack while preserving the current outer container format
            current_format = EPIContainer.detect_container_format(self.output_path)
            manifest = EPIContainer.read_manifest(self.output_path)
            tmp_path = create_recording_workspace("epi_signing_")
            try:
                EPIContainer.unpack(self.output_path, tmp_path)

                # Re-pack from the extracted workspace so file manifests, viewer content,
                # and the outer envelope stay coherent after signing.
                temp_output = self.output_path.with_suffix('.epi.tmp')
                EPIContainer.pack(
                    tmp_path,
                    manifest,
                    temp_output,
                    signer_function=lambda current: sign_manifest(
                        current, private_key, self.default_key_name
                    ),
                    preserve_generated=True,
                    container_format=current_format,
                    generate_analysis=False,
                )
                
                # Successfully created signed file, now safely replace original
                self.output_path.unlink()
                temp_output.rename(self.output_path)
            finally:
                shutil.rmtree(tmp_path, ignore_errors=True)

            return True

        except Exception as e:
            import sys
            print(f"Warning: Failed to sign .epi file: {e}", file=sys.stderr)
            return False


def _auto_generate_output_path(name_hint: Optional[str] = None) -> Path:
    """
    Auto-generate output path in ./epi-recordings/ directory.
    
    Args:
        name_hint: Optional base name hint (script name, function name, etc.)
        
    Returns:
        Path object for the .epi file
    """
    # Get recordings directory from env or default
    recordings_dir = Path(os.getenv("EPI_RECORDINGS_DIR", "epi-recordings"))
    recordings_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate base name
    if name_hint:
        base = Path(name_hint).stem if "." in name_hint else name_hint
    else:
        base = "recording"
    
    # Generate timestamp
    timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
    
    # Ensure .epi extension
    filename = f"{base}_{timestamp}.epi"
    
    return recordings_dir / filename


def _resolve_output_path(output_path: Optional[Path | str]) -> Path:
    """
    Resolve output path, adding .epi extension and default directory if needed.
    
    Args:
        output_path: User-provided path or None for auto-generation
        
    Returns:
        Resolved Path object
    """
    if output_path is None:
        return _auto_generate_output_path()
    
    path = Path(output_path)
    
    # Add .epi extension if missing
    if path.suffix != ".epi":
        path = path.with_suffix(".epi")
        
    # If path is absolute, return it
    if path.is_absolute():
        return path
        
    # If path is relative, prepend recordings directory UNLESS it already starts with it
    recordings_dir = Path(os.getenv("EPI_RECORDINGS_DIR", "epi-recordings"))
    recordings_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if path already starts with the recordings directory
    # This prevents double-prepending (e.g., epi-recordings/epi-recordings/file.epi)
    path_parts = path.parts
    if path_parts and path_parts[0] == recordings_dir.name:
        # Path already includes recordings directory, use as-is
        return path
    
    # Path doesn't include recordings directory, prepend it
    return recordings_dir / path


# Convenience function for users (supports zero-config)
def record(
    output_path: Optional[Path | str] = None,
    workflow_name: Optional[str] = None,
    tags: Optional[List[str]] = None,
    auto_sign: bool = True,
    redact: bool = True,
    default_key_name: str = "default",
    # New metadata fields
    goal: Optional[str] = None,
    notes: Optional[str] = None,
    metrics: Optional[Dict[str, Union[float, str]]] = None,
    approved_by: Optional[str] = None,
    metadata_tags: Optional[List[str]] = None,  # Renamed to avoid conflict
    legacy_patching: bool = False,
    capture_prints: bool = True,
    capture_stderr: bool = False,
) -> Union[EpiRecorderSession, Callable]:
    """
    Create an EPI recording session (context manager).
    
    Args:
        output_path: Path for output .epi file (optional - auto-generates if None)
        workflow_name: Descriptive name for workflow
        tags: Tags for categorization
        auto_sign: Whether to automatically sign on exit (default: True)
        redact: Whether to redact secrets (default: True)
        default_key_name: Name of key to use for signing (default: "default")
        goal: Goal or objective of this workflow execution
        notes: Additional notes or context about this workflow
        metrics: Key-value metrics for this workflow (accuracy, latency, etc.)
        approved_by: Person or entity who approved this workflow execution
        metadata_tags: Tags for categorizing this workflow (renamed from tags to avoid conflict)
        **kwargs: Additional arguments (backward compatibility)
        
    Returns:
        EpiRecorderSession context manager or decorated function
        
    Example:
        from epi_recorder import record
        
        # Zero-config (auto-generates filename in ./epi-recordings/)
        with record():
            # Your code here
            pass
        
        # With custom name
        with record("my_workflow"):
            # Your code here
            pass
        
        # With metadata
        with record(
            goal="reduce hallucinations",
            notes="switched to GPT-4",
            metrics={"accuracy": 0.89},
            approved_by="alice@company.com",
            metadata_tags=["prod-candidate"]
        ):
            # Your code here
            pass
        
        # Decorator usage
        @record
        def main():
            # Your code here
            pass
            
        # Decorator with metadata
        @record(goal="decorator test", metrics={"test_score": 0.95})
        def main():
            # Your code here
            pass
    """
    def _make_session(name_hint: str) -> EpiRecorderSession:
        auto_path = _auto_generate_output_path(name_hint)
        return EpiRecorderSession(
            auto_path,
            workflow_name or name_hint,
            tags=tags,
            auto_sign=auto_sign,
            redact=redact,
            default_key_name=default_key_name,
            goal=goal,
            notes=notes,
            metrics=metrics,
            approved_by=approved_by,
            metadata_tags=metadata_tags,
            legacy_patching=legacy_patching,
            capture_prints=capture_prints,
            capture_stderr=capture_stderr,
        )

    def _wrap(func: Callable) -> Callable:
        """Wrap sync or async function for EPI recording."""
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                async with _make_session(func.__name__):
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                with _make_session(func.__name__):
                    return func(*args, **kwargs)
            return sync_wrapper

    # Check if this is being used as a decorator with arguments
    # If the first argument is not a path but keyword arguments are provided,
    # we need to return a decorator function
    if output_path is None and (workflow_name is not None or goal is not None or notes is not None or
                               metrics is not None or approved_by is not None or metadata_tags is not None):
        return _wrap

    # Handle decorator usage: record is called without parentheses
    if callable(output_path):
        func = output_path
        return _wrap(func)
    
    # Normal context manager usage
    resolved_path = _resolve_output_path(output_path)
    return EpiRecorderSession(
        resolved_path,
        workflow_name,
        tags=tags,
        auto_sign=auto_sign,
        redact=redact,
        default_key_name=default_key_name,
        goal=goal,
        notes=notes,
        metrics=metrics,
        approved_by=approved_by,
        metadata_tags=metadata_tags,
        legacy_patching=legacy_patching,
        capture_prints=capture_prints,
        capture_stderr=capture_stderr,
    )


class _BootstrapSessionProxy:
    """Minimal session proxy exposed when recording is active via bootstrap."""

    def __init__(self, recording_context: RecordingContext):
        self._recording_context = recording_context

    def log_step(self, kind: str, content: Dict[str, Any]) -> None:
        self._recording_context.add_step(kind, content)

    async def alog_step(self, kind: str, content: Dict[str, Any]) -> None:
        self.log_step(kind, content)

    def agent_run(
        self,
        agent_name: str,
        *,
        agent_type: str = "agent",
        user_input: Optional[Any] = None,
        goal: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        attempt: int = 1,
        resume_from: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentRun:
        return AgentRun(
            self.log_step,
            self.alog_step,
            agent_name,
            agent_type=agent_type,
            user_input=user_input,
            goal=goal,
            session_id=session_id,
            task_id=task_id,
            parent_run_id=parent_run_id,
            attempt=attempt,
            resume_from=resume_from,
            metadata=metadata,
        )

    def agent(
        self,
        agent_name: str,
        *,
        agent_type: str = "agent",
        user_input: Optional[Any] = None,
        goal: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        attempt: int = 1,
        resume_from: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentRun:
        return self.agent_run(
            agent_name,
            agent_type=agent_type,
            user_input=user_input,
            goal=goal,
            session_id=session_id,
            task_id=task_id,
            parent_run_id=parent_run_id,
            attempt=attempt,
            resume_from=resume_from,
            metadata=metadata,
        )


# Make it easy to get current session
def get_current_session() -> Optional[Any]:
    """
    Get the currently active recording session (if any).
    
    Returns:
        EpiRecorderSession or None
    """
    active = getattr(_thread_local, 'active_session', None)
    if active is not None:
        return active

    # epi run/bootstrap mode: expose a minimal manual logging surface.
    context = get_recording_context()
    if context is None:
        return None
    return _BootstrapSessionProxy(context)



 
