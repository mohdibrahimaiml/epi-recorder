"""
Import external evidence bundles into sealed .epi artifacts.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel

from epi_cli.keys import KeyManager
from epi_core.container import (
    EPIContainer,
    EPI_CONTAINER_FORMAT_ENVELOPE,
    EPI_CONTAINER_FORMAT_LEGACY,
)
from epi_core.schemas import ManifestModel
from epi_core.trust import sign_manifest
from epi_recorder.integrations.agt import AGTInputError, export_agt_to_epi, load_agt_input
from epi_recorder.integrations.agt.loader import DEFAULT_AGT_IMPORT_MANIFEST
from epi_recorder.integrations.agt.report import AnalysisMode
from epi_recorder.integrations.agt_adapter import import_agt as import_agt_raw
from epi_recorder.integrations.agt_adapter.detect import detect_file_format, AGTArtifactType

_ALLOWED_DEDUP = {"prefer-audit", "keep-both", "fail"}
_ALLOWED_ANALYSIS = {"synthesized", "none"}

app = typer.Typer(
    help=(
        "Import external evidence into a sealed .epi case file. "
        "`epi import steps <file.jsonl|.csv> --out run.epi` for any agent log, "
        "or `epi import agt <bundle-or-dir-or-manifest> --out run.epi` for AGT bundles."
    )
)
console = Console()


def _print_agt_input_hint() -> None:
    console.print("")
    console.print("[bold]Supported AGT inputs:[/bold]")
    console.print("  [cyan]bundle.json[/cyan]                     neutral AGT bundle JSON")
    console.print("  [cyan]evidence-dir/[/cyan]                   directory with AGT files like audit_logs.json")
    console.print(
        f"  [cyan]{DEFAULT_AGT_IMPORT_MANIFEST}[/cyan]              manifest JSON for non-standard filenames"
    )
    console.print("")
    console.print("[dim]Examples:[/dim]")
    console.print("  [cyan]epi import agt examples/agt/evidence-dir --out case.epi[/cyan]")
    console.print(
        "  [cyan]epi import agt examples/agt/manifest-input/agt_import_manifest.json --out case.epi[/cyan]"
    )


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
    agt_input: Path = typer.Argument(
        ...,
        help=(
            "Path to AGT input: neutral bundle JSON, AGT evidence directory, "
            "native AGT export, or AGT import manifest JSON."
        ),
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
    dedupe: str = typer.Option(
        "prefer-audit",
        "--dedupe",
        help="How to handle overlapping audit/flight-recorder records.",
    ),
    analysis: str = typer.Option(
        "synthesized",
        "--analysis",
        help="Whether to synthesize analysis.json for imported artifacts.",
    ),
    raw: bool = typer.Option(
        False, "--raw", hidden=True,
        help="Force raw AGT import (bypass auto-detect).",
    ),
):
    """Convert AGT evidence into a normal .epi artifact.

    Auto-detects the input format: native AGT export, EPI neutral bundle,
    AGT evidence directory, or AGT import manifest.
    """
    # Auto-detect: is this a native AGT format or a bundle/directory?
    use_raw = raw
    if not use_raw and agt_input.is_file():
        try:
            atype, _ = detect_file_format(agt_input)
            use_raw = atype in (
                AGTArtifactType.EXPORT_BUNDLE,
                AGTArtifactType.FILE_AUDIT_SINK,
                AGTArtifactType.CLOUDEVENTS,
                AGTArtifactType.SINGLE_ENTRY,
            )
        except Exception:
            use_raw = False  # Not a native format, try bundle path

    if use_raw:
        # Route to native AGT raw pipeline
        try:
            epi_path, report = import_agt_raw(
                source=agt_input,
                output_dir=out.parent,
                workflow_name="agt-import",
                tags=["agt-import"],
            )
        except Exception as exc:
            console.print(f"[red][FAIL][/red] Native AGT import failed: {exc}")
            raise typer.Exit(1)

        if str(epi_path) != str(out):
            import shutil
            shutil.move(str(epi_path), str(out))
            epi_path = out

        signed = bool(EPIContainer.read_manifest(epi_path).signature)
        console.print("")
        panel = Panel(
            f"[bold]Input:[/bold] {agt_input}\n"
            f"[bold]Output:[/bold] {epi_path}\n"
            f"[bold]Signed:[/bold] {'Yes' if signed else 'No'}\n"
            f"[bold]AGT Version:[/bold] {report.agt_version_detected}\n"
            f"[bold]Fields Mapped:[/bold] {report.exact_count} exact, "
            f"{report.dropped_count} dropped, {report.preserved_count} preserved\n"
            f"[bold]Mapping Report:[/bold] mapping_report.json\n"
            f"[dim]Verify:[/dim] epi verify {epi_path}",
            title="[OK] AGT import complete",
            border_style="green",
        )
        console.print(panel)
        return

    # Bundle/directory route (original behavior)
    try:
        bundle = load_agt_input(agt_input)
    except FileNotFoundError as exc:
        console.print(f"[red][FAIL][/red] {exc}")
        _print_agt_input_hint()
        raise typer.Exit(1)
    except AGTInputError as exc:
        console.print(f"[red][FAIL][/red] {exc}")
        _print_agt_input_hint()
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Could not load AGT input: {exc}")
        _print_agt_input_hint()
        raise typer.Exit(1)

    if dedupe not in _ALLOWED_DEDUP:
        console.print(f"[red][FAIL][/red] Invalid --dedupe value: {dedupe!r}. Must be one of: prefer-audit, keep-both, fail")
        raise typer.Exit(1)

    if analysis not in _ALLOWED_ANALYSIS:
        console.print(f"[red][FAIL][/red] Invalid --analysis value: {analysis!r}. Must be one of: synthesized, none")
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
    try:
        from epi_core.telemetry import track_event
        from epi_core import telemetry as telemetry_core

        telemetry_core.record_first_use()
        track_event(
            "epi.import.completed",
            {
                "command": "import",
                "source": "agt",
                "success": True,
                "artifact_bytes": output_path.stat().st_size,
                "artifact_count": 1,
            },
        )
    except Exception:
        pass
    panel = Panel(
        f"[bold]Input:[/bold] {agt_input}\n"
        f"[bold]Output:[/bold] {output_path}\n"
        f"[bold]Signed:[/bold] {'Yes' if signed else 'No'}\n"
        f"[bold]Analysis:[/bold] {'Synthesized' if analysis == 'synthesized' else 'Omitted'}\n"
        f"[bold]Trust Audit:[/bold] artifacts/agt/mapping_report.json\n"
        f"[dim]Verify:[/dim] epi verify {output_path}\n"
        f"[dim]Extract review:[/dim] epi view --extract review {output_path}\n"
        f"[dim]Open interactively:[/dim] epi view {output_path}",
        title="[OK] AGT import complete",
        border_style="green",
    )
    console.print(panel)


@app.command("agt-raw")
def import_agt_raw_cmd(
    source: Path = typer.Argument(
        ...,
        help="Path to raw AGT artifact: .json (export bundle), .jsonl (FileAuditSink), or CloudEvents.",
    ),
    out: Path = typer.Option(..., "--out", "-o", help="Output .epi file path."),
    key_name: str = typer.Option("default", "--key", help="EPI signing key name."),
    workflow_name: str = typer.Option("", "--name", help="Override workflow name."),
    tag: list[str] = typer.Option([], "--tag", help="Additional tags for the artifact."),
):
    """[DEPRECATED] Use 'epi import agt' instead — auto-detects formats.

    Import raw AGT audit evidence into a sealed .epi artifact.
    Detects artifact format from content (JSON bundle, JSONL FileAuditSink,
    CloudEvents) and preserves raw AGT evidence verbatim inside the .epi file.
    """
    if not source.exists():
        console.print(f"[red][X] File not found:[/red] {source}")
        raise typer.Exit(1)

    try:
        epi_path, report = import_agt_raw(
            source=source,
            output_dir=out.parent,
            key_name=key_name,
            workflow_name=workflow_name or None,
            tags=list(tag) or ["agt-import"],
        )
    except Exception as exc:
        console.print(f"[red][X] Import failed:[/red] {exc}")
        raise typer.Exit(1)

    # Move to exact output path if different
    if str(epi_path) != str(out):
        import shutil
        shutil.move(str(epi_path), str(out))
        epi_path = out

    console.print("")
    panel = Panel(
        f"[bold]Input:[/bold] {source}\n"
        f"[bold]Output:[/bold] {epi_path}\n"
        f"[bold]AGT Version:[/bold] {report.agt_version_detected}\n"
        f"[bold]Fields Mapped:[/bold] {report.exact_count} exact, "
        f"{report.dropped_count} dropped, {report.preserved_count} preserved\n"
        f"[bold]Mapping Report:[/bold] mapping_report.json\n"
        f"[dim]Verify:[/dim] epi verify {epi_path}",
        title="[OK] AGT raw import complete",
        border_style="green",
    )
    console.print(panel)


# ───────────────────────── generic step-log import ─────────────────────────

# Columns that carry EPI's own structure; anything else on a CSV row is content.
_STEP_RESERVED = {
    "index", "timestamp", "time", "ts", "kind", "type", "event",
    "content", "data", "payload", "source_type", "trace_id", "span_id",
    "parent_span_id", "prev_hash", "governance", "verification_class",
}
_VALID_SOURCE_TYPES = {"user", "tool", "reasoning", "system"}


def _read_step_rows(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Read a step log into rows. Returns (rows, format-name)."""
    suffix = path.suffix.lower()

    if suffix in (".jsonl", ".ndjson"):
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8-sig") as fh:
            for n, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"line {n}: invalid JSON ({exc.msg})") from exc
                if not isinstance(obj, dict):
                    raise ValueError(f"line {n}: expected a JSON object, got {type(obj).__name__}")
                rows.append(obj)
        return rows, "jsonl"

    if suffix == ".json":
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(obj, dict):
            obj = obj.get("steps")
            if obj is None:
                raise ValueError("JSON object has no 'steps' array")
        if not isinstance(obj, list):
            raise ValueError("JSON must be an array of step objects, or {'steps': [...]}")
        if not all(isinstance(r, dict) for r in obj):
            raise ValueError("every entry must be a JSON object")
        return obj, "json"

    if suffix in (".csv", ".tsv"):
        delim = "," if suffix == ".csv" else "\t"
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            rows = [dict(r) for r in csv.DictReader(fh, delimiter=delim)]
        return rows, suffix.lstrip(".")

    raise ValueError("unsupported input: use .jsonl, .ndjson, .json, .csv or .tsv")


def _coerce_timestamp(raw: Any, fallback: datetime) -> tuple[datetime, bool]:
    """Return (timestamp, assumed). Numbers are epoch seconds or milliseconds."""
    if raw is None or str(raw).strip() == "":
        return fallback, True

    if isinstance(raw, (int, float)) or str(raw).strip().replace(".", "", 1).isdigit():
        value = float(raw)
        if value > 1e11:  # milliseconds
            value /= 1000.0
        return datetime.fromtimestamp(value, tz=UTC), False

    text = str(raw).strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"unparseable timestamp {raw!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed, False


def _build_steps(
    rows: list[dict[str, Any]], *, source_name: str, fmt: str
) -> tuple[list[Any], int]:
    """Turn external rows into hash-chained StepModels."""
    from epi_core.schemas import StepModel
    from epi_core.serialize import get_canonical_hash

    base = datetime.now(UTC)
    steps: list[Any] = []
    assumed = 0
    prev_hash = "CHAIN_START"

    for i, row in enumerate(rows):
        kind = str(row.get("kind") or row.get("type") or row.get("event") or "").strip()
        if not kind:
            raise ValueError(f"row {i + 1}: missing 'kind' (or 'type' / 'event')")

        raw_content = row.get("content", row.get("data", row.get("payload")))
        extras = {
            k: v for k, v in row.items() if k not in _STEP_RESERVED and v is not None
        }
        if raw_content is None:
            content = extras
        else:
            if isinstance(raw_content, dict):
                parsed_content = dict(raw_content)
            else:
                try:
                    parsed = json.loads(str(raw_content))
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"row {i + 1}: 'content' is not valid JSON ({exc.msg})"
                    ) from exc
                parsed_content = parsed if isinstance(parsed, dict) else {"value": parsed}
            # Extra columns are provenance too; explicit content wins on clashes.
            content = {**extras, **parsed_content}

        timestamp, was_assumed = _coerce_timestamp(
            row.get("timestamp", row.get("time", row.get("ts"))),
            base + timedelta(microseconds=i),
        )
        if was_assumed:
            assumed += 1

        meta: dict[str, Any] = {"format": fmt, "source": source_name, "source_index": i}
        if was_assumed:
            meta["timestamp_assumed"] = True
        existing = content.get("_epi_import")
        if isinstance(existing, dict):
            meta = {**existing, **meta}
        content["_epi_import"] = meta

        source_type = row.get("source_type")
        step = StepModel(
            index=i,
            timestamp=timestamp,
            kind=kind,
            content=content,
            source_type=source_type if source_type in _VALID_SOURCE_TYPES else None,
            prev_hash=prev_hash,
        )
        prev_hash = get_canonical_hash(step, format="json")
        steps.append(step)

    return steps, assumed


@app.command("steps")
def import_steps(
    input_path: Path = typer.Argument(
        ...,
        help="Step log to seal: .jsonl/.ndjson, a .json array, or .csv/.tsv.",
    ),
    out: Path | None = typer.Option(
        None, "--out", "-o",
        help="Output .epi path (default: epi-recordings/<input name>.epi).",
    ),
    goal: str | None = typer.Option(
        None, "--goal", help="One-line goal recorded in the manifest."
    ),
    key_name: str = typer.Option("default", "--key", help="Signing key name."),
    no_sign: bool = typer.Option(
        False, "--no-sign", help="Seal unsigned (verification reports unsigned)."
    ),
    with_viewer: bool = typer.Option(
        False, "--with-viewer", help="Embed the self-opening HTML viewer."
    ),
) -> None:
    """Seal a step log you already have — no SDK, no integration.

    Each record needs a ``kind``; everything else becomes content. The hash
    chain is rebuilt at import, so the artifact proves the record has not
    changed since you sealed it — not that the exporter told the truth.
    """
    import shutil
    import tempfile

    if not input_path.exists():
        console.print(f"[red][X] File not found:[/red] {input_path}")
        raise typer.Exit(1)

    try:
        rows, fmt = _read_step_rows(input_path)
    except (ValueError, OSError, UnicodeDecodeError) as exc:
        console.print(f"[red][X] Cannot read {input_path.name}:[/red] {exc}")
        raise typer.Exit(1)

    if not rows:
        console.print(f"[red][X] No steps found in {input_path.name}.[/red]")
        raise typer.Exit(1)

    try:
        steps, assumed = _build_steps(rows, source_name=input_path.name, fmt=fmt)
    except ValueError as exc:
        console.print(f"[red][X] Import failed:[/red] {exc}")
        raise typer.Exit(1)

    out_path = out or Path("epi-recordings") / f"{input_path.stem}.epi"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    notes = (
        f"Imported from {input_path.name} ({fmt}); {len(steps)} steps; "
        "hash chain rebuilt at import."
    )
    if assumed:
        notes += (
            f" {assumed} step(s) carried no timestamp: import time was assumed "
            "and is declared in each step's _epi_import block."
        )

    manifest = ManifestModel(
        cli_command=f"epi import steps {input_path.name}",
        goal=goal,
        notes=notes,
    )
    manifest.total_steps = len(steps)

    signer = None if no_sign else _build_signer(False)
    if signer is None and not no_sign:
        console.print(
            "[yellow][WARN][/yellow] No signing key available — sealing unsigned."
        )

    staging = Path(tempfile.mkdtemp(prefix="epi_import_steps_"))
    try:
        with (staging / "steps.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for step in steps:
                fh.write(step.model_dump_json() + "\n")

        EPIContainer.pack(
            staging,
            manifest,
            out_path,
            signer_function=signer,
            container_format=(
                EPI_CONTAINER_FORMAT_ENVELOPE if with_viewer else EPI_CONTAINER_FORMAT_LEGACY
            ),
            embed_viewer=with_viewer,
        )
    except Exception as exc:  # noqa: BLE001 - surface the real reason to the operator
        console.print(f"[red][X] Packing failed:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    assumed_line = (
        f"[bold]Timestamps assumed:[/bold] {assumed} (declared in each step)\n"
        if assumed
        else ""
    )
    console.print("")
    console.print(
        Panel(
            f"[bold]Input:[/bold] {input_path}  ({fmt}, {len(rows)} rows)\n"
            f"[bold]Output:[/bold] {out_path}  ({out_path.stat().st_size:,} bytes)\n"
            f"[bold]Steps:[/bold] {len(steps)}  ·  hash chain rebuilt\n"
            f"{assumed_line}"
            f"[bold]Signed:[/bold] {'no (unsigned)' if signer is None else 'yes'}\n"
            f"[dim]Verify:[/dim] epi verify {out_path} --policy strict",
            title="[OK] Step log sealed",
            border_style="green",
        )
    )
