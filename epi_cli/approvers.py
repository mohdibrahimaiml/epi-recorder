"""``epi approvers`` — pin human approvers and hold their own keys (step 3a).

Approver keys live in a directory separate from the agent keys dir, and the
approver registry is separate from the trusted *signer* keys. Pinning a
vendor's sealing key can never make it an approver.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from epi_core.approvers import (
    APPROVER_ROLE,
    ApproverRegistry,
    _resolve_default_approver_keys_dir,
    normalize_fingerprint,
    reserved_key_reason,
)
from epi_core.keys import KeyManager, key_fingerprint

app = typer.Typer(
    help="Human approver registry and approver-held keys.",
    no_args_is_help=True,
)
console = Console()


def _load_public_key_hex(source: str) -> str:
    """Accept a key file (PEM/.pub/.epi), a 64-hex key, or an agent key name."""
    candidate = Path(str(source))
    if candidate.exists():
        return KeyManager()._load_public_key_raw_bytes_from_any(candidate).hex()
    text = str(source).strip()
    if len(text) == 64 and all(char in "0123456789abcdefABCDEF" for char in text):
        return text.lower()
    return KeyManager().load_public_key(text).hex()


def _approval_key_for_fingerprint(source: str, fingerprint: str | None) -> str | None:
    """An approval key inside a .epi whose fingerprint matches the one read aloud.

    `approvers add <file.epi>` otherwise takes the *sealing* key from the
    manifest, which is the wrong key when what you want to pin is the human who
    approved. The fingerprint is still the check: a key is only accepted when
    its fingerprint is the one the operator supplied.
    """
    if not fingerprint:
        return None
    candidate = Path(str(source))
    if not candidate.exists() or candidate.suffix.lower() != ".epi":
        return None
    try:
        from epi_core.review import read_review_records
    except Exception:
        return None
    try:
        records = read_review_records(candidate)
    except Exception:
        return None
    wanted = normalize_fingerprint(fingerprint)
    for record in records:
        signature = str(record.review_signature or "")
        parts = signature.split(":", 2)
        if len(parts) != 3 or parts[0] != "ed25519" or len(parts[1]) != 64:
            continue
        public_hex = parts[1].lower()
        if normalize_fingerprint(key_fingerprint(public_hex)) == wanted:
            return public_hex
    return None


def _approver_keys_dir() -> Path:
    return _resolve_default_approver_keys_dir()


def _refuse_if_not_separate(keys_dir: Path) -> None:
    try:
        agent_dir = Path(KeyManager().keys_dir).resolve()
    except Exception:
        agent_dir = None
    if agent_dir is not None and Path(keys_dir).resolve() == agent_dir:
        console.print(
            "[red][FAIL] Refusing: the approver keys directory is the agent keys "
            f"directory ({agent_dir}).[/red]"
        )
        console.print(
            "[dim]Set EPI_APPROVER_KEYS_DIR (or unset EPI_KEYS_DIR) so the approver's "
            "key is not the key that seals runs.[/dim]"
        )
        raise typer.Exit(1)


@app.command("add")
def add(
    source: str = typer.Argument(
        ...,
        help="Public key file (.pub / PEM / signed .epi), a 64-hex key, or an agent key name.",
    ),
    name: str = typer.Option(..., "--name", help="Approver identity, e.g. alice@bank.com"),
    role: list[str] = typer.Option(
        [APPROVER_ROLE],
        "--role",
        help="Role(s) for this approver. Only 'approver' counts for human_signed.",
    ),
    fingerprint: str | None = typer.Option(
        None,
        "--fingerprint",
        help="The fingerprint the approver read aloud. Required; must match the key.",
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Replace an existing pin for this name."
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Pin a key that is a local agent key or a trusted signer anyway (not recommended).",
    ),
):
    """Pin a person's public key as a human approver."""
    try:
        public_hex = _load_public_key_hex(source)
    except Exception as exc:
        approval_key = _approval_key_for_fingerprint(source, fingerprint)
        if approval_key is None:
            console.print(f"[red][FAIL] Could not read a public key from {source!r}:[/red] {exc}")
            raise typer.Exit(1)
        public_hex = approval_key
    else:
        # A signed .epi carries two keys: the sealer (manifest) and, if the run
        # was approved, the approver (review signature). When the fingerprint the
        # operator read aloud belongs to the approval, pin that one instead.
        if fingerprint and normalize_fingerprint(fingerprint) != normalize_fingerprint(
            key_fingerprint(public_hex)
        ):
            approval_key = _approval_key_for_fingerprint(source, fingerprint)
            if approval_key is not None:
                public_hex = approval_key

    actual_fp = key_fingerprint(public_hex)
    if not fingerprint or normalize_fingerprint(fingerprint) != normalize_fingerprint(actual_fp):
        console.print(
            "[red][FAIL] Not pinned.[/red] Pin an approver only against the fingerprint "
            "the person read to you (by phone, not from the same machine)."
        )
        console.print(f"  Key fingerprint: [bold]{actual_fp}[/bold]")
        console.print(
            f'  If it matches what they read: epi approvers add "{source}" --name {name} '
            f'--fingerprint "{actual_fp}"'
        )
        raise typer.Exit(1)

    reason = reserved_key_reason(public_hex)
    if reason:
        if not force:
            console.print(f"[red][FAIL] Refusing: {reason}.[/red]")
            console.print(
                "[dim]An approver key must be the person's own key, not the agent's or a "
                "pinned signer's. Use --force only if you are sure.[/dim]"
            )
            raise typer.Exit(1)
        console.print(f"[bold yellow]Warning:[/bold yellow] pinning a reserved key — {reason}.")

    try:
        path = ApproverRegistry().add(name, public_hex, roles=list(role), overwrite=overwrite)
    except Exception as exc:
        console.print(f"[red][FAIL] Could not pin approver '{name}':[/red] {exc}")
        raise typer.Exit(1)

    console.print(f"\n[bold green][OK] Pinned approver:[/bold green] {name}")
    console.print(f"  [cyan]Fingerprint:[/cyan] {actual_fp}")
    console.print(f"  [cyan]Registry:[/cyan]    {path}")


@app.command("list")
def list_approvers():
    """List pinned approvers."""
    entries = ApproverRegistry().list()
    if not entries:
        console.print("[dim]No approvers pinned yet.[/dim]")
        console.print(
            "[dim]Add one: epi approvers add <key-file> --name <id> --fingerprint \"<fp>\"[/dim]"
        )
        return
    table = Table(title="Approvers (pinned)", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Fingerprint", style="green")
    table.add_column("Roles")
    table.add_column("Added", style="dim")
    for entry in entries:
        table.add_row(
            str(entry.get("name", "")),
            key_fingerprint(str(entry.get("public_key", ""))),
            ", ".join(str(r) for r in (entry.get("roles") or [])),
            str(entry.get("added_at", ""))[:19],
        )
    console.print(table)


@app.command("remove")
def remove(
    name: str = typer.Option(..., "--name", help="Approver name to unpin."),
):
    """Unpin an approver. Files they signed then report signed_unknown_key."""
    if ApproverRegistry().remove(name):
        console.print(f"[green][OK][/green] Removed approver: {name}")
    else:
        console.print(f"[yellow]No approver named '{name}'.[/yellow]")
        raise typer.Exit(1)


@app.command("keygen")
def keygen(
    name: str = typer.Option(..., "--name", help="Approver identity, e.g. alice@bank.com"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing key."),
):
    """Generate an approver's key in the approver keys dir (never the agent's)."""
    keys_dir = _approver_keys_dir()
    _refuse_if_not_separate(keys_dir)

    password = os.environ.get("EPI_KEY_PASSWORD")
    if not password:
        password = typer.prompt(
            "Password for the approver key (encrypted at rest)",
            hide_input=True,
            confirmation_prompt=True,
        )
        if not password:
            console.print("[red][FAIL] An approver key must be encrypted at rest.[/red]")
            raise typer.Exit(1)
        os.environ["EPI_KEY_PASSWORD"] = password

    try:
        manager = KeyManager(keys_dir=keys_dir)
        private_path, public_path = manager.generate_keypair(name, overwrite=overwrite)
    except Exception as exc:
        console.print(f"[red][FAIL] Could not generate approver key:[/red] {exc}")
        raise typer.Exit(1)

    public_hex = manager.load_public_key(name).hex()
    console.print(f"\n[bold green][OK] Generated approver key:[/bold green] {name}")
    console.print(f"  [cyan]Private:[/cyan] {private_path}  [dim](encrypted at rest)[/dim]")
    console.print(f"  [cyan]Public:[/cyan]  {public_path}")
    console.print(
        f"  [cyan]Fingerprint:[/cyan] {key_fingerprint(public_hex)}  "
        "[dim](read this to the verifier's admin by phone)[/dim]"
    )


@app.command("link")
def link(
    name: str = typer.Option(..., "--name", help="Approver identity, e.g. alice@bank.com"),
    uri: str = typer.Option(
        ...,
        "--uri",
        help="Key held in an HSM/KMS: pkcs11:... | awskms:... | gcpkms:...",
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Re-link an existing key."),
):
    """Link an approver's key held in an HSM or cloud KMS."""
    keys_dir = _approver_keys_dir()
    _refuse_if_not_separate(keys_dir)
    try:
        manager = KeyManager(keys_dir=keys_dir)
        signer_path, public_hex = manager.link_external_key(name, uri, overwrite=overwrite)
    except Exception as exc:
        console.print(f"[red][FAIL] Could not link approver key:[/red] {exc}")
        raise typer.Exit(1)

    console.print(f"\n[bold green][OK] Linked approver key:[/bold green] {name} -> {uri}")
    console.print(f"  [cyan]Link file:[/cyan]   {signer_path}  [dim](no secrets)[/dim]")
    console.print(f"  [cyan]Fingerprint:[/cyan] {key_fingerprint(public_hex)}")
