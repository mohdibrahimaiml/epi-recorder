"""EU database notification CLI commands."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from epi_core.keys import KeyManager

console = Console()
notify_app = typer.Typer(help="EU AI Act database notification")


def _canon(data: dict) -> str:
    """Compute canonical JSON for signing."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


@notify_app.command("generate")
def generate(
    system_name: str = typer.Option(..., "--system-name", help="Name of the high-risk AI system"),
    manufacturer: str = typer.Option(..., "--manufacturer", help="Legal name of manufacturer/provider"),
    member_states: str = typer.Option("", "--member-states", help="Comma-separated ISO codes (e.g. DE,FR,NL)"),
    risk_category: str = typer.Option("high", "--risk-category", help="Risk category: limited, high, unacceptable"),
    epi_file: Path = typer.Option(..., "--epi-file", help="Path to Annex IV .epi file"),
    key_name: str = typer.Option("annex", "--key-name", "-k", help="Key to sign with"),
    representative: str = typer.Option(None, "--representative", help="Authorized representative (non-EU providers)"),
    out: Path = typer.Option(Path("notifications"), "--out", "-o", help="Output directory"),
):
    """Generate a signed EU database notification record."""
    from epi_core.eu_notification import EUDatabaseNotification

    if not epi_file.exists():
        console.print(f"[red]EPI file not found: {epi_file}[/red]")
        raise typer.Exit(1)

    # Compute SHA-256 of the .epi file
    file_hash = hashlib.sha256(epi_file.read_bytes()).hexdigest()

    # Build notification
    states = [s.strip().upper() for s in member_states.split(",") if s.strip()]
    notification = EUDatabaseNotification(
        system_name=system_name,
        manufacturer=manufacturer,
        authorized_representative=representative,
        risk_category=risk_category,
        conformity_declaration_ref=f"Section 8 — EU Declaration of Conformity (SHA-256: {file_hash[:16]}...)",
        technical_documentation_hash=file_hash,
        member_states=states,
        contact_email=None,
    )

    # Sign the notification
    km = KeyManager()
    if not km.has_key(key_name):
        km.generate_keypair(key_name)

    pk = km.load_private_key(key_name)
    payload = notification.model_dump_notification()
    canonical = _canon(payload)
    signature = pk.sign(canonical.encode("utf-8"))

    notification_data = notification.model_dump(mode="json")
    notification_data["signature"] = f"ed25519:{key_name}:{signature.hex()}"
    notification_data["signed_at"] = datetime.now(timezone.utc).isoformat()
    notification_data["status"] = "ready_to_submit"

    # Save to output directory
    out.mkdir(parents=True, exist_ok=True)
    filename = f"eu-notification-{system_name.replace(' ', '-').lower()}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    outfile = out / filename
    outfile.write_text(json.dumps(notification_data, indent=2))

    # Try SCITT anchoring
    scitt_status = "not anchored"
    try:
        from epi_core.scitt import create_scitt_statement
        from epi_core.local_scitt import register_statement
        from epi_core.schemas import ManifestModel

        mn = ManifestModel(
            cli_command="notify generate",
            goal=f"EU database notification for {system_name}",
        )
        stmt = create_scitt_statement(mn, pk, issuer=f"epi:key:{key_name}")
        rcpt, info = register_statement(stmt)
        notification_data["scitt_receipt_id"] = info.entry_id
        scitt_status = f"SCITT anchored ({info.entry_id[:16]}...)"
        outfile.write_text(json.dumps(notification_data, indent=2))
    except Exception as e:
        scitt_status = f"SCITT skipped: {e}"

    console.print(Panel(
        f"System: {system_name}\n"
        f"Risk: {risk_category}\n"
        f"Member States: {', '.join(states) or 'none specified'}\n"
        f"Hash: {file_hash[:32]}...\n"
        f"Signed: ed25519:{key_name}\n"
        f"{scitt_status}\n"
        f"Status: ready_to_submit\n"
        f"Output: {outfile}",
        title="EU Database Notification"
    ))

    console.print(f"\n[green]Notification ready.[/green] Manual submission may be required until the EU database API is available.")
    console.print(f"File: {outfile}")


@notify_app.command("status")
def status(notifications_dir: Path = typer.Option(Path("notifications"), "--dir", "-d", help="Notifications directory")):
    """List all generated notification records and their status."""
    if not notifications_dir.exists():
        console.print("No notifications directory found. Generate one with: epi notify generate")
        return

    files = sorted(notifications_dir.glob("eu-notification-*.json"))
    if not files:
        console.print("No notification records found")
        return

    from rich.table import Table
    t = Table(title="EU Database Notifications")
    t.add_column("File"); t.add_column("System"); t.add_column("Risk"); t.add_column("Status"); t.add_column("Signed")

    for f in files:
        try:
            d = json.loads(f.read_text())
            t.add_row(
                f.name,
                d.get("system_name", "?"),
                d.get("risk_category", "?"),
                d.get("status", "?"),
                "✓" if "signature" in d else "✗",
            )
        except Exception:
            t.add_row(f.name, "error", "?", "corrupt", "✗")

    console.print(t)
