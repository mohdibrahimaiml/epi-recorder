"""
Import external evidence bundles into sealed .epi artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from epi_cli.keys import KeyManager
from epi_core.container import EPIContainer
from epi_core.trust import sign_manifest
from epi_recorder.integrations.agt import coerce_agt_bundle, export_agt_to_epi
from epi_recorder.integrations.agt.report import AnalysisMode, DedupStrategy

app = typer.Typer(
    help=(
        "Import external evidence into a sealed .epi case file. "
        "Start with `epi import agt <bundle.json> --out run.epi`."
    )
)
console = Console()


def _build_signer(no_sign: bool):
    if no_sign:
        return None

    try:
        key_manager = KeyManager()
        private_key = key_manager.load_private_key("default")

        def signer(manifest):
            return sign_manifest(manifest, private_key, "default")

        return signer
    except Exception as exc:
        console.print(f"[yellow][WARN][/yellow] Signing setup failed: {exc}")
        return None


@app.command("agt")
def import_agt(
    bundle_json: Path = typer.Argument(
        ..., help="Path to an exported AGT evidence bundle (.json)."
    ),
    out: Path = typer.Option(..., "--out", "-o", help="Output .epi file path."),
    no_sign: bool = typer.Option(False, "--no-sign", help="Do not sign the imported artifact."),
    no_attach_raw: bool = typer.Option(
        False, "--no-attach-raw", help="Skip attaching raw AGT payloads under artifacts/agt/."
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Fail on unknown AGT event mappings, unclassified fields, and dedupe conflicts.",
    ),
    dedupe: DedupStrategy = typer.Option(
        "prefer-audit",
        "--dedupe",
        help="How to handle overlapping audit/flight-recorder records.",
    ),
    analysis: AnalysisMode = typer.Option(
        "synthesized",
        "--analysis",
        help="Whether to synthesize analysis.json for imported artifacts.",
    ),
):
    """Convert an AGT evidence bundle into a normal .epi artifact."""

    if not bundle_json.exists():
        console.print(f"[red][FAIL][/red] File not found: {bundle_json}")
        raise typer.Exit(1)

    try:
        payload = json.loads(bundle_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        console.print(f"[red][FAIL][/red] Invalid JSON: {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Could not read bundle: {exc}")
        raise typer.Exit(1)

    try:
        bundle = coerce_agt_bundle(payload)
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Invalid AGT bundle: {exc}")
        raise typer.Exit(1)

    if strict and dedupe != "fail":
        console.print("[red][FAIL][/red] Strict import requires --dedupe fail")
        raise typer.Exit(1)

    if analysis == "none":
        console.print(
            "[yellow][WARN][/yellow] analysis.json will be omitted, so `epi review` "
            "will not have synthesized findings for this artifact."
        )

    signer = _build_signer(no_sign)

    try:
        output_path = export_agt_to_epi(
            bundle,
            out,
            signer_function=signer,
            attach_raw=not no_attach_raw,
            strict=strict,
            dedupe_strategy=dedupe,
            analysis_mode=analysis,
        )
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Import failed: {exc}")
        raise typer.Exit(1)

    signed = bool(EPIContainer.read_manifest(output_path).signature)
    panel = Panel(
        f"[bold]Input:[/bold] {bundle_json}\n"
        f"[bold]Output:[/bold] {output_path}\n"
        f"[bold]Signed:[/bold] {'Yes' if signed else 'No'}\n"
        f"[bold]Analysis:[/bold] {'Synthesized' if analysis == 'synthesized' else 'Omitted'}\n"
        f"[bold]Trust Audit:[/bold] artifacts/agt/mapping_report.json\n"
        f"[dim]Verify:[/dim] epi verify {output_path}\n"
        f"[dim]Open:[/dim] epi view {output_path}",
        title="[OK] AGT import complete",
        border_style="green",
    )
    console.print(panel)
