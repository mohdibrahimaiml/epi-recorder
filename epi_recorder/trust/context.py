"""Step-sink context for the active recording session.

A tool may run on a worker thread; contextvars do not cross a plain
ThreadPoolExecutor boundary. Callers that hand a wrapped tool to a pool must
propagate the context explicitly::

    ctx = contextvars.copy_context()
    pool.submit(ctx.run, wrapped_tool, ...)

Without that, the gate still blocks/allows and still writes its request,
response and execution files, sends the witness reports, and warns — it never
silently drops the evidence.
"""

from __future__ import annotations

import contextvars
from typing import Any

_CURRENT_SINK: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "epi_step_sink", default=None
)


def set_step_sink(sink: Any):
    return _CURRENT_SINK.set(sink)


def reset_step_sink(token) -> None:
    try:
        _CURRENT_SINK.reset(token)
    except Exception:
        pass


def current_step_sink() -> Any:
    return _CURRENT_SINK.get()
