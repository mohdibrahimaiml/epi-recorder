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
from epi_core.container import EPI_CONTAINER_FORMAT_LEGACY, EPIContainer
from epi_core.local_scitt import LOCAL_SCITT_SERVICE_URL
from epi_core.local_scitt import register_statement as register_local_statement
from epi_core.schemas import ManifestModel
from epi_core.scitt import (
    SCITTRegistrationError,
    SCITTServiceClient,
    SCITTServiceInfo,
    SCITTVerificationError,
    create_scitt_statement,
    scitt_governance_from_info,
    verify_scitt_receipt,
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


def _register_offline(
    epi_path: Path,
    output_path: Path,
    manifest: ManifestModel,
    private_key: Any,
    key_name: str,
    issuer: str,
    service_label: str,
) -> None:
    """Register the artifact with the local SCITT service and embed the receipt."""
    statement_bytes = create_scitt_statement(manifest, private_key, issuer=issuer)
    console.print(
        f"  [green][OK][/green] Created COSE_Sign1 statement ({len(statement_bytes)} bytes)"
    )

    receipt_bytes, info = register_local_statement(statement_bytes)
    info = SCITTServiceInfo(
        service_url=service_label,
        entry_id=info.entry_id,
        registered_at=info.registered_at,
    )
    console.print("  [green][OK][/green] Registered with local SCITT transparency service")
    console.print(f"  Entry ID: {info.entry_id}")

    _build_scitt_artifact(
        epi_path, output_path, manifest, statement_bytes, receipt_bytes,
        info, private_key, key_name,
    )

    panel = Panel(
        f"[bold]Input:[/bold]  {epi_path}\n"
        f"[bold]Output:[/bold] {output_path}\n"
        f"[bold]Service:[/bold] {service_label}\n"
        f"[bold]Entry:[/bold]  {info.entry_id}\n"
        f"[bold]Issuer:[/bold] {issuer}",
        title="[OK] Local SCITT Registration Complete",
        border_style="green",
    )
    console.print(panel)


@app.command("register")
def scitt_register(
    epi_file: Path = typer.Argument(..., help="Path to the .epi file to register."),
    service: str | None = typer.Option(
        None, "--service", "-s", help="SCITT transparency service URL."
    ),
    out: Path | None = typer.Option(
        None, "--out", "-o",
        help="Output path for the new .epi file. Defaults to overwriting input.",
    ),
    key: str = typer.Option(
        "default", "--key", "-k",
        help="Name of the Ed25519 key to use for signing.",
    ),
    local: bool = typer.Option(
        False, "--local",
        help="Create a local self-signed SCITT receipt without contacting a service.",
    ),
) -> None:
    """
    Register an .epi artifact with a SCITT transparency service.

    This creates a SCITT Signed Statement (COSE_Sign1) for the manifest,
    submits it to the transparency service, and embeds the returned receipt
    into a new .epi file.

    Use --local to create an offline self-signed receipt. This is useful for
    CI, air-gapped environments, or testing without a live SCITT service.

    Note: Public endpoints such as https://epilabs.org/scitt may be protected
    by Cloudflare and can return 403 in automated/CLI contexts. For CI or
    offline testing, use --local or a local SCITT service.
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

    if local:
        service_label = service or LOCAL_SCITT_SERVICE_URL
        console.print("[bold]Local SCITT Registration[/bold]")
        console.print(f"  Artifact: {epi_path}")
        console.print(f"  Service:  {service_label}")
        console.print(f"  Issuer:   {issuer}")
        _register_offline(epi_path, output_path, manifest, private_key, key, issuer, service_label)
        raise typer.Exit(0)

    if not service:
        console.print("[red][FAIL][/red] --service is required unless --local is used.")
        raise typer.Exit(1)

    from epi_cli._shared import require_service

    require_service(service, label="SCITT service")

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


@app.command("anchor")
def scitt_anchor(
    epi_file: Path = typer.Argument(..., help="Path to the .epi file to anchor."),
    service: str = typer.Option(
        None, "--service", "-s",
        help="SCITT transparency service URL (overrides EPI_SCITT_URL env var).",
    ),
    key: str = typer.Option(
        "default", "--key", "-k",
        help="Name of the Ed25519 key to use for signing.",
    ),
    local: bool = typer.Option(
        False, "--local",
        help="Create a local self-signed SCITT receipt without contacting a service.",
    ),
) -> None:
    """
    Manually anchor a signed .epi artifact to a SCITT Transparency Service.

    This is useful when auto-anchoring was disabled or failed during recording.
    Requires EPI_SCITT_URL env var or --service flag, unless --local is used.
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

    if not manifest.signature:
        console.print(
            "[yellow][WARN][/yellow] Artifact is unsigned. Sign first with: epi sign <file.epi>"
        )
        raise typer.Exit(1)

    private_key = _load_signing_key(key)
    issuer = _derive_issuer(manifest)

    if local:
        service_label = service or "local"
        console.print("[bold]Local SCITT Anchor[/bold]")
        console.print(f"  Artifact: {epi_path}")
        console.print(f"  Service:  {service_label}")
        console.print(f"  Issuer:   {issuer}")
        _register_offline(epi_path, epi_path, manifest, private_key, key, issuer, service_label)
        raise typer.Exit(0)

    import os

    from epi_recorder.auto_scitt import AutoSCITTAnchor

    service_url = service or os.environ.get("EPI_SCITT_URL")
    if not service_url:
        console.print(
            "[red][FAIL][/red] No SCITT service URL. Set EPI_SCITT_URL or use --service."
        )
        raise typer.Exit(1)

    from epi_cli._shared import require_service

    require_service(service_url, label="SCITT service")

    anchor = AutoSCITTAnchor(service_url=service_url)
    console.print(f"[bold]Anchoring to SCITT:[/bold] {service_url}")

    success = anchor.anchor_if_configured(manifest, epi_path, private_key, key)
    if success:
        console.print("[green][OK][/green] SCITT anchor complete")
    else:
        console.print("[red][FAIL][/red] SCITT anchor failed")
        raise typer.Exit(1)


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

    # Verify receipt — first structurally, then cryptographically.
    try:
        receipt = cbor2.loads(receipt_bytes)
        if not (isinstance(receipt, cbor2.CBORTag) and receipt.tag == 18):
            raise SCITTVerificationError("Invalid receipt structure")
        console.print("  [green][OK][/green] SCITT receipt structurally valid")
    except Exception as exc:
        console.print(f"  [red][FAIL][/red] SCITT receipt invalid: {exc}")
        raise typer.Exit(1)

    # Full cryptographic verification of the receipt signature.
    service_url = scitt_gov.get("service_url") or service
    if service_url:
        try:
            from epi_cli.verify import _fetch_scitt_service_key

            service_pub_key = _fetch_scitt_service_key(service_url)
            if service_pub_key:
                verify_scitt_receipt(receipt_bytes, statement_bytes, service_pub_key)
                console.print("  [green][OK][/green] SCITT receipt signature verified (Ed25519)")
            else:
                console.print(
                    "  [yellow][WARN][/yellow] Could not fetch SCITT service public key;"
                    " skipping signature verification."
                )
        except SCITTVerificationError as exc:
            console.print(f"  [red][FAIL][/red] SCITT receipt signature invalid: {exc}")
            raise typer.Exit(1)
        except Exception as exc:
            console.print(
                f"  [yellow][WARN][/yellow] Could not verify receipt signature: {exc}"
            )
    else:
        console.print(
            "  [yellow][WARN][/yellow] No service URL known; skipping signature verification."
        )

    panel = Panel(
        f"[bold]Artifact:[/bold] {epi_path}\n"
        f"[bold]Service:[/bold]  {scitt_gov.get('service_url', 'unknown')}\n"
        f"[bold]Entry:[/bold]   {scitt_gov.get('entry_id', 'unknown')}\n"
        f"[bold]Issuer:[/bold]  {scitt_gov.get('issuer', 'unknown')}",
        title="[OK] SCITT Verification Complete",
        border_style="green",
    )
    console.print(panel)


def _rewrite_payload_with_updates(
    input_payload: Path,
    output_payload: Path,
    manifest_json: bytes,
    extra_files: dict[str, bytes],
) -> None:
    """Copy a payload ZIP, replacing manifest.json and adding/updating extra files."""
    import zipfile

    with zipfile.ZipFile(input_payload, "r") as zf_in, zipfile.ZipFile(
        output_payload, "w", zipfile.ZIP_DEFLATED
    ) as zf_out:
        for item in zf_in.infolist():
            name = item.filename
            if name == "manifest.json" or name in extra_files:
                continue
            zf_out.writestr(item, zf_in.read(name))
        zf_out.writestr("manifest.json", manifest_json)
        for name, data in extra_files.items():
            zf_out.writestr(name, data)


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

    The existing payload is rewritten in-place so that file_manifest and the
    SCITT statement hash stay consistent with the original artifact.
    """
    import shutil
    import zipfile

    scitt_gov = scitt_governance_from_info(info, issuer=_derive_issuer(manifest))

    # Build updated manifest
    manifest_dict = manifest.model_dump(mode="json")
    if not manifest_dict.get("governance"):
        manifest_dict["governance"] = {}
    manifest_dict["governance"]["scitt"] = scitt_gov

    updated_manifest = ManifestModel(**manifest_dict)

    # Re-sign the manifest
    signed_manifest = sign_manifest(updated_manifest, private_key, key_name)

    manifest_json = signed_manifest.model_dump_json(indent=2).encode("utf-8")
    extra_files = {
        "artifacts/scitt/statement.cbor": statement_bytes,
        "artifacts/scitt/receipt.cbor": receipt_bytes,
    }

    output_epi.parent.mkdir(parents=True, exist_ok=True)
    in_place = input_epi.resolve() == output_epi.resolve()
    work_output = output_epi.with_suffix(output_epi.suffix + ".tmp") if in_place else output_epi
    shutil.copyfile(input_epi, work_output)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        payload_path = tmpdir_path / "payload.zip"
        EPIContainer.extract_inner_payload(work_output, payload_path)

        updated_payload = tmpdir_path / "payload_updated.zip"
        _rewrite_payload_with_updates(payload_path, updated_payload, manifest_json, extra_files)

        fmt = EPIContainer.detect_container_format(work_output)
        if fmt == EPI_CONTAINER_FORMAT_LEGACY:
            shutil.copyfile(updated_payload, work_output)
        else:
            viewer_html = None
            try:
                with zipfile.ZipFile(updated_payload, "r") as zf:
                    viewer_html = zf.read("viewer.html").decode("utf-8")
            except Exception:
                pass
            EPIContainer._write_artifact_from_payload(
                updated_payload,
                work_output,
                container_format=fmt,
                manifest=signed_manifest,
                viewer_html=viewer_html,
            )

    if in_place:
        shutil.move(str(work_output), str(output_epi))
