"""
epi_recorder.auto — Explicit one-line setup for common framework stacks.

Usage::

    from epi_recorder import auto
    auto.setup()           # registers hooks for installed frameworks

    # Or opt in to specific ones:
    auto.setup(litellm=True, langchain=True)

Note: LiteLLM and OpenTelemetry are wired globally.  LangChain uses
per-object callbacks; ``auto.setup()`` confirms availability and prints
the usage hint, but you still pass ``EPICallbackHandler()`` to each model.

This is explicit opt-in convenience, not silent magic.  EPI's architecture
requires intentional capture; auto.setup() is a shortcut for teams that want
to register all integrations at app startup without writing the individual
import lines for each one.

Set EPI_QUIET=1 to suppress the printed summary.
"""
from __future__ import annotations

import os
import sys
from typing import Optional


def setup(
    *,
    litellm: Optional[bool] = None,
    langchain: Optional[bool] = None,
    opentelemetry: Optional[bool] = None,
    quiet: Optional[bool] = None,
) -> dict[str, bool]:
    """
    Register EPI integrations for all installed (or requested) frameworks.

    Each integration is only activated when the relevant package is present.
    Pass ``True`` to force a framework (raises ImportError if not installed),
    or ``False`` to explicitly skip it.  Leave as ``None`` (default) to
    auto-detect.

    Args:
        litellm:       Hook LiteLLM's callback system (covers 100+ providers).
        langchain:     Register ``EPICallbackHandler`` globally on LangChain.
        opentelemetry: Set up ``EPISpanExporter`` as an OTel span exporter.
        quiet:         Suppress the printed summary.  Defaults to the value of
                       the ``EPI_QUIET`` environment variable.

    Returns:
        Dict mapping integration name to ``True`` (activated) / ``False``
        (skipped or unavailable).

    Example::

        from epi_recorder import auto, record
        auto.setup()

        with record("my_agent.epi"):
            litellm.completion(...)   # captured automatically
    """
    _quiet = quiet if quiet is not None else (os.getenv("EPI_QUIET", "0") == "1")
    results: dict[str, bool] = {}

    # ---- LiteLLM ----
    if litellm is not False:
        try:
            from epi_recorder.integrations.litellm import enable_epi
            enable_epi()
            results["litellm"] = True
        except ImportError:
            if litellm is True:
                raise
            results["litellm"] = False
        except Exception as exc:
            if litellm is True:
                raise
            results["litellm"] = False
            if not _quiet:
                print(f"[EPI] auto.setup: litellm hook failed: {exc}", file=sys.stderr)

    # ---- LangChain ----
    # LangChain uses per-object callbacks; there is no global hook to register.
    # auto.setup() confirms the integration module is importable and prints a
    # usage reminder — the caller must still pass EPICallbackHandler() to each
    # ChatModel instance.
    if langchain is not False:
        try:
            import langchain  # noqa: F401 — probe only
            from epi_recorder.integrations.langchain import EPICallbackHandler  # noqa: F401
            results["langchain"] = True
            if not _quiet:
                print(
                    "[EPI] auto.setup: LangChain detected — EPICallbackHandler is ready to use.\n"
                    "      Add it per model: ChatOpenAI(..., callbacks=[EPICallbackHandler()])",
                    file=sys.stderr,
                )
        except ImportError:
            if langchain is True:
                raise
            results["langchain"] = False
        except Exception as exc:
            if langchain is True:
                raise
            results["langchain"] = False
            if not _quiet:
                print(f"[EPI] auto.setup: langchain probe failed: {exc}", file=sys.stderr)

    # ---- OpenTelemetry ----
    if opentelemetry is not False:
        try:
            from epi_recorder.integrations.opentelemetry import setup_epi_tracing
            setup_epi_tracing()
            results["opentelemetry"] = True
        except ImportError:
            if opentelemetry is True:
                raise
            results["opentelemetry"] = False
        except Exception as exc:
            if opentelemetry is True:
                raise
            results["opentelemetry"] = False
            if not _quiet:
                print(f"[EPI] auto.setup: opentelemetry hook failed: {exc}", file=sys.stderr)

    if not _quiet:
        activated = [k for k, v in results.items() if v]
        skipped = [k for k, v in results.items() if not v]
        if activated:
            print(f"[EPI] auto.setup: activated {', '.join(activated)}", file=sys.stderr)
        if skipped:
            print(f"[EPI] auto.setup: skipped (not installed) {', '.join(skipped)}", file=sys.stderr)

    return results
