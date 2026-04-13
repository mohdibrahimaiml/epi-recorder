"""High-intent telemetry and pilot CTAs for CLI flows."""

from __future__ import annotations

import os
import sys
from typing import Literal

from rich.console import Console

from epi_core import telemetry as telemetry_core

HintContext = Literal["init", "verify", "integrate"]


def _is_interactive() -> bool:
    return bool(getattr(sys.stdin, "isatty", lambda: False)())


def _hints_disabled() -> bool:
    return str(os.getenv("EPI_TELEMETRY_HINTS") or "").strip().lower() in {"0", "false", "no", "off"}


def maybe_print_telemetry_hint(console: Console, context: HintContext) -> None:
    """Show a contextual opt-in CTA without creating identifiers or local state."""

    if _hints_disabled() or telemetry_core.is_enabled() or not _is_interactive():
        return

    console.print()
    if context == "verify":
        console.print("[bold]You just verified an EPI artifact.[/bold]")
        console.print("Want a dashboard for artifact history and compliance report exports?")
    elif context == "integrate":
        console.print("[bold]You just set up an EPI integration path.[/bold]")
        console.print("Want early access to framework roadmap input, dashboard features, and priority support?")
    else:
        console.print("[bold]Your first EPI artifact is ready.[/bold]")
        console.print("Want early access to artifact dashboard, compliance reports UI, and priority support?")

    console.print("[dim]EPI is running locally. No telemetry is sent unless you opt in.[/dim]")
    console.print("  [cyan]epi telemetry enable[/cyan]                 share anonymous non-content usage")
    console.print("  [cyan]epi telemetry enable --join-pilot[/cyan]    join the pilot for dashboard/support access")
