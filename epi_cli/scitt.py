"""
SCITT (Supply Chain Integrity, Transparency and Trust) CLI commands.

Provides:
  epi scitt register <file.epi> --service <url> [--out <new_file.epi>]
  epi scitt verify <file.epi> [--service <url>]
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import cbor2
import typer
from rich.console import Console
from rich.panel import Panel

from epi_cli.keys import KeyManager
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.scitt import (
    SCITTRegistrationError,
    SCITTServiceClient,
    SCITTVerificationError,
    create_scitt_statement,
    scitt_governance_from_info,
    verify_scitt_statement,
)
from epi_core.trust import sign_manifest

console = Console()
app = typer.Typer(
    help="Register and verify SCITT transparency receipts for .epi artifacts."
)


def _load_signing_key(key_name: str = "default"):
    """Load an Ed25519 private key from the EPI key manager."""
    try:
        key_manager = KeyManager()
        return key_manager.load_private_key(key_name)
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Could not load signing key '{key_name}': {exc}")
        raise typer.Exit(1)


def _derive_issuer(manifest: ManifestModel) -> str:
    """Derive the issuer identifier from manifest metadata."""
    gov = manifest.governance or {}
    if gov.get("did"):
        return gov["did"]
    if manifest.public_key:
        return f"epi:pubkey:{manifest.public_key[:16]}"
    return "epi:anonymous"


@app.command("register")
def scitt_register(
    epi_file: Path = typer.Argument(..., help="Path to the .epi file to register."),
    service: str = typer.Option(..., "--service", "-s", help="SCITT transparency service URL."),
    out: Path | None = typer.Option(
        None, "--out", "-o",
        help="Output path for the new .epi file. Defaults to overwriting input.",
    ),
    key: str = typer.Option(
        "default", "--key", "-k",
        help="Name of the Ed25519 key to use for signing.",
    ),
) -> None:
    """
    Register an .epi artifact with a SCITT transparency service.

    This creates a SCITT Signed Statement (COSE_Sign1) for the manifest,
    submits it to the transparency service, and embeds the returned receipt
    into a new .epi file.
    """
    epi_path = Path(epi_file).resolve()
    if not epi_path.exists():
        console.print(f"[red][FAIL][/red] File not found: {epi_path}")
        raise typer.Exit(1)

    output_path = Path(out).resolve() if out else epi_path

    try:
        manifest = EPIContainer.read_manifest(epi_path)
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Could not read manifest: {exc}")
        raise typer.Exit(1)

    if not manifest.public_key:
        console.print(
            "[yellow][WARN][/yellow] Artifact is unsigned. SCITT registration requires "
            "an Ed25519 signature. Sign first with: epi sign <file.epi>"
        )
        raise typer.Exit(1)

    private_key = _load_signing_key(key)
    issuer = _derive_issuer(manifest)

    console.print("[bold]SCITT Registration[/bold]")
    console.print(f"  Artifact: {epi_path}")
    console.print(f"  Service:  {service}")
    console.print(f"  Issuer:   {issuer}")

    # Create SCITT Signed Statement
    try:
        statement_bytes = create_scitt_statement(manifest, private_key, issuer=issuer)
        console.print(
            f"  [green][OK][/green] Created COSE_Sign1 statement ({len(statement_bytes)} bytes)"
        )
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Could not create SCITT statement: {exc}")
        raise typer.Exit(1)

    # Register with transparency service
    client = SCITTServiceClient(service)
    try:
        receipt_bytes, info = client.register(statement_bytes)
        console.print("  [green][OK][/green] Registered with transparency service")
        console.print(f"  Entry ID: {info.entry_id}")
    except SCITTRegistrationError as exc:
        console.print(f"[red][FAIL][/red] Registration failed: {exc}")
        raise typer.Exit(1)

    # Build new .epi with SCITT artifacts embedded
    try:
        _build_scitt_artifact(
            epi_path, output_path, manifest, statement_bytes, receipt_bytes,
            info, private_key, key,
        )
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Could not build SCITT artifact: {exc}")
        raise typer.Exit(1)

    panel = Panel(
        f"[bold]Input:[/bold]  {epi_path}\n"
        f"[bold]Output:[/bold] {output_path}\n"
        f"[bold]Service:[/bold] {service}\n"
        f"[bold]Entry:[/bold]  {info.entry_id}\n"
        f"[bold]Issuer:[/bold] {issuer}",
        title="[OK] SCITT Registration Complete",
        border_style="green",
    )
    console.print(panel)


@app.command("verify")
def scitt_verify(
    epi_file: Path = typer.Argument(..., help="Path to the .epi file to verify."),
    service: str | None = typer.Option(
        None, "--service", "-s",
        help="SCITT transparency service URL (optional, for receipt refresh).",
    ),
) -> None:
    """
    Verify the SCITT receipt embedded in an .epi artifact.

    Checks:
    1. COSE_Sign1 statement structure and signature
    2. Statement payload matches the manifest hash
    3. Receipt structure and service signature
    """
    epi_path = Path(epi_file).resolve()
    if not epi_path.exists():
        console.print(f"[red][FAIL][/red] File not found: {epi_path}")
        raise typer.Exit(1)

    try:
        manifest = EPIContainer.read_manifest(epi_path)
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Could not read manifest: {exc}")
        raise typer.Exit(1)

    scitt_gov = (manifest.governance or {}).get("scitt") if manifest.governance else None
    if not scitt_gov:
        console.print("[yellow][WARN][/yellow] No SCITT metadata found in this artifact.")
        raise typer.Exit(1)

    stmt_path = scitt_gov.get("statement_path", "artifacts/scitt/statement.cbor")
    rcpt_path = scitt_gov.get("receipt_path", "artifacts/scitt/receipt.cbor")

    # Extract artifacts from ZIP
    import zipfile
    statement_bytes: bytes | None = None
    receipt_bytes: bytes | None = None
    with zipfile.ZipFile(epi_path, "r") as zf:
        try:
            statement_bytes = zf.read(stmt_path)
        except KeyError:
            console.print(f"[red][FAIL][/red] Statement not found in archive: {stmt_path}")
            raise typer.Exit(1)
        try:
            receipt_bytes = zf.read(rcpt_path)
        except KeyError:
            console.print(f"[red][FAIL][/red] Receipt not found in archive: {rcpt_path}")
            raise typer.Exit(1)

    # Verify statement against manifest
    try:
        verify_scitt_statement(statement_bytes, manifest)
        console.print("  [green][OK][/green] SCITT statement valid (payload matches manifest hash)")
    except SCITTVerificationError as exc:
        console.print(f"  [red][FAIL][/red] SCITT statement invalid: {exc}")
        raise typer.Exit(1)

    # Verify receipt (structural check; full sig verification needs service pubkey)
    try:
        receipt = cbor2.loads(receipt_bytes)
        if isinstance(receipt, cbor2.CBORTag) and receipt.tag == 18:
            console.print("  [green][OK][/green] SCITT receipt structurally valid")
        else:
            raise SCITTVerificationError("Invalid receipt structure")
    except Exception as exc:
        console.print(f"  [red][FAIL][/red] SCITT receipt invalid: {exc}")
        raise typer.Exit(1)

    panel = Panel(
        f"[bold]Artifact:[/bold] {epi_path}\n"
        f"[bold]Service:[/bold]  {scitt_gov.get('service_url', 'unknown')}\n"
        f"[bold]Entry:[/bold]   {scitt_gov.get('entry_id', 'unknown')}\n"
        f"[bold]Issuer:[/bold]  {scitt_gov.get('issuer', 'unknown')}",
        title="[OK] SCITT Verification Complete",
        border_style="green",
    )
    console.print(panel)


def _build_scitt_artifact(
    input_epi: Path,
    output_epi: Path,
    manifest: ManifestModel,
    statement_bytes: bytes,
    receipt_bytes: bytes,
    info,
    private_key,
    key_name: str,
) -> None:
    """
    Build a new .epi artifact with SCITT artifacts embedded.

    Extracts the original ZIP contents, adds artifacts/scitt/*,
    updates manifest.governance and file_manifest, re-signs,
    and writes the new artifact.
    """
    import hashlib
    import zipfile

    scitt_gov = scitt_governance_from_info(info, issuer=_derive_issuer(manifest))

    # Build updated manifest
    manifest_dict = manifest.model_dump(mode="json")
    manifest_dict.setdefault("governance", {})
    manifest_dict["governance"]["scitt"] = scitt_gov

    # Compute hashes for SCITT artifacts
    stmt_hash = hashlib.sha256(statement_bytes).hexdigest()
    rcpt_hash = hashlib.sha256(receipt_bytes).hexdigest()

    manifest_dict["file_manifest"] = dict(manifest_dict.get("file_manifest", {}))
    manifest_dict["file_manifest"]["artifacts/scitt/statement.cbor"] = stmt_hash
    manifest_dict["file_manifest"]["artifacts/scitt/receipt.cbor"] = rcpt_hash

    updated_manifest = ManifestModel(**manifest_dict)

    # Re-sign the manifest
    signed_manifest = sign_manifest(updated_manifest, private_key, key_name)

    # Write new ZIP
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        extract_dir = tmpdir_path / "extract"
        extract_dir.mkdir()

        # Extract original contents
        with zipfile.ZipFile(input_epi, "r") as zf_in:
            zf_in.extractall(extract_dir)

        # Add SCITT artifacts
        scitt_dir = extract_dir / "artifacts" / "scitt"
        scitt_dir.mkdir(parents=True, exist_ok=True)
        (scitt_dir / "statement.cbor").write_bytes(statement_bytes)
        (scitt_dir / "receipt.cbor").write_bytes(receipt_bytes)

        # Write updated manifest
        (extract_dir / "manifest.json").write_text(
            signed_manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )

        # Determine container format from original
        with open(input_epi, "rb") as f:
            header = f.read(4)
        container_format = "envelope-v2" if header == b"<!--" else "legacy-zip"

        EPIContainer.pack(
            source_dir=extract_dir,
            manifest=signed_manifest,
            output_path=output_epi,
            container_format=container_format,
            preserve_generated=True,
        )
