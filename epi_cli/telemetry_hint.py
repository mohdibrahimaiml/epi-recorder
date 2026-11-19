"""High-intent telemetry and pilot CTAs for CLI flows."""

from __future__ import annotations

import os
import sys
from typing import Literal

from rich.console import Console

from epi_core import telemetry as telemetry_core

HintContext = Literal["init", "verify", "integrate", "demo", "share"]


def _is_interactive() -> bool:
    return bool(getattr(sys.stdin, "isatty", lambda: False)())


def _hints_disabled() -> bool:
    return str(os.getenv("EPI_TELEMETRY_HINTS") or "").strip().lower() in {"0", "false", "no", "off"}


def _cloud_connected() -> bool:
    """True when `epi cloud login` already connected this computer."""
    try:
        from epi_cli.cloud import load_config

        cfg = load_config()
        return bool(cfg.get("url") and (cfg.get("org_id") or cfg.get("org")))
    except Exception:
        return False


_LEADS: dict[str, str] = {
    "verify": "You just verified an EPI artifact.",
    "integrate": "You just set up an EPI integration path.",
    "demo": "Your first EPI demo is ready.",
    "share": "You just shared an EPI artifact.",
    "init": "Your first EPI artifact is ready.",
}


def maybe_print_telemetry_hint(console: Console, context: HintContext) -> None:
    """Show one short, accurate next step without creating identifiers or local state.

    The offer is EPI Cloud (hosted witnessing and customer share links); it is
    skipped once this computer is connected, and telemetry stays opt-in.
    """

    if _hints_disabled() or not _is_interactive():
        return
    cloud = not _cloud_connected()
    telemetry = not telemetry_core.is_enabled()
    if not (cloud or telemetry):
        return

    console.print()
    console.print(f"[bold]{_LEADS.get(context, _LEADS['init'])}[/bold]")
    if cloud:
        console.print(
            "Give a customer a witnessed copy they open in a browser: "
            "[cyan]epi cloud login[/cyan] (free workspace, optional)."
        )
    if telemetry:
        console.print(
            "[dim]EPI runs locally and sends no telemetry unless you opt in: "
            "epi telemetry enable[/dim]"
        )
