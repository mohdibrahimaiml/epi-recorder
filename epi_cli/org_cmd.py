"""
Org trust bundles — customer-signed key history for offline verification.

  epi org bundle issue --bundle-id acme --root-key <name|path> --key seal-2026=<pub> --out org-bundle.json
  epi org bundle verify artifact.epi org-bundle.json [--json]

The customer root private key never leaves the caller's machine: it is loaded
from their own key manager or PEM file and used only to sign the bundle
envelope in-process. Spec: docs/design/org-trust-bundle.md (v0).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

console = Console()

app = typer.Typer(
    name="org",
    help="Org trust bundles: customer-signed key history for offline auditor verification.",
    no_args_is_help=True,
)
bundle_app = typer.Typer(
    name="bundle",
    help="Issue and verify org trust bundles.",
    no_args_is_help=True,
)
app.add_typer(bundle_app, name="bundle")


def _load_root_private_key(ref: str):
    """Load the customer root private key by key-manager name or PEM path."""
    candidate = Path(ref)
    if candidate.exists():
        from cryptography.hazmat.primitives import serialization

        try:
            return serialization.load_pem_private_key(
                candidate.read_bytes(), password=None
            )
        except Exception as exc:
            raise typer.BadParameter(
                f"Cannot load root private key from {ref}: {exc}"
            )
    from epi_core.keys import KeyManager

    try:
        return KeyManager().load_private_key(ref)
    except Exception as exc:
        raise typer.BadParameter(
            f"Cannot load root private key '{ref}': {exc}. "
            "Generate one on your own hardware: epi keys generate --name org-root"
        )


def _read_pubkey_hex(ref: str) -> str:
    """Read a 32-byte Ed25519 public key as hex from hex text, PEM, or .pub path.

    ``.epi`` sources are fail-closed: the artifact's embedded manifest
    signature must verify before its key is pinned, unless
    ``EPI_ALLOW_UNVERIFIED_ORG_KEY=1`` is set (auditable, explicit).
    """
    from epi_core.keys import KeyManager

    candidate = Path(ref)
    if candidate.exists():
        if candidate.suffix.lower() == ".epi":
            import os as _os

            from epi_core.container import EPIContainer
            from epi_core.trust import verify_signature

            manifest = EPIContainer.read_manifest(candidate)
            pub_hex = str(getattr(manifest, "public_key", None) or "").strip().lower()
            if not pub_hex:
                raise typer.BadParameter(
                    f"Key '{ref}' is an unsigned .epi (no manifest.public_key); "
                    "use a signed artifact or pass the raw public key"
                )
            try:
                valid, _msg = verify_signature(manifest, bytes.fromhex(pub_hex))
            except Exception as exc:
                raise typer.BadParameter(
                    f"Key '{ref}': cannot verify source artifact signature ({exc})"
                )
            if not valid and _os.getenv(
                "EPI_ALLOW_UNVERIFIED_ORG_KEY", "0"
            ).strip().lower() not in ("1", "true", "yes", "on"):
                raise typer.BadParameter(
                    f"Key '{ref}': source artifact signature does not verify; "
                    "verify it first (epi verify) or set "
                    "EPI_ALLOW_UNVERIFIED_ORG_KEY=1 to pin anyway"
                )
        return KeyManager()._load_public_key_raw_bytes_from_any(candidate).hex()
    text = ref.strip().lower()
    try:
        raw = bytes.fromhex(text)
    except ValueError:
        raise typer.BadParameter(
            f"Key '{ref}' is not a path, PEM, or 64-hex public key"
        )
    if len(raw) != 32:
        raise typer.BadParameter(f"Key '{ref}' must be 32-byte Ed25519")
    return raw.hex()


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@bundle_app.command("issue")
def bundle_issue(
    bundle_id: str = typer.Option(..., "--bundle-id", help="Stable org identifier, e.g. acme-corp."),
    root_key: str = typer.Option(..., "--root-key", help="Customer root private key: key-manager name or PEM path. Never leaves this machine."),
    key: list[str] = typer.Option([], "--key", help="Sealing key as KEY_ID=PUB (hex, PEM path, or .pub path). Repeatable."),
    not_before: Optional[str] = typer.Option(None, "--not-before", help="Validity start for all included keys (ISO-8601, default now)."),
    not_after: Optional[str] = typer.Option(None, "--not-after", help="Validity end for all included keys (ISO-8601, optional)."),
    version: Optional[int] = typer.Option(None, "--version", help="Bundle version (default: previous + 1, or 1)."),
    prev_bundle: Optional[Path] = typer.Option(None, "--prev-bundle", help="Previous bundle file to continue versioning from."),
    out: Path = typer.Option(Path("org-bundle.json"), "--out", "-o", help="Output bundle JSON path."),
):
    """Issue (customer-sign) a new org trust bundle version."""
    from epi_core.org_bundle import issue_bundle, save_bundle

    if not key:
        console.print("[red]No keys provided.[/red] Add at least one with --key KEY_ID=PUB.")
        raise typer.Exit(2)

    root_priv = _load_root_private_key(root_key)
    try:
        root_pub_hex = root_priv.public_key().public_bytes_raw().hex()
    except Exception:
        from cryptography.hazmat.primitives import serialization

        root_pub_hex = (
            root_priv.public_key()
            .public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            .hex()
        )

    prev_version = 0
    if prev_bundle is not None:
        try:
            prev_version = int(json.loads(prev_bundle.read_text(encoding="utf-8")).get("version", 0))
        except Exception as exc:
            console.print(f"[red]Cannot read previous bundle:[/red] {exc}")
            raise typer.Exit(2)
    new_version = version if version is not None else prev_version + 1
    if new_version <= prev_version:
        console.print(
            f"[red]Version must increase:[/red] previous is v{prev_version}, requested v{new_version}."
        )
        raise typer.Exit(2)

    start = not_before or _now_iso()
    keys = []
    for spec in key:
        if "=" not in spec:
            console.print(f"[red]Bad --key spec (want KEY_ID=PUB):[/red] {spec}")
            raise typer.Exit(2)
        key_id, pub_ref = spec.split("=", 1)
        key_id = key_id.strip()
        if not key_id:
            console.print(f"[red]Empty key id in --key spec:[/red] {spec}")
            raise typer.Exit(2)
        keys.append(
            {
                "key_id": key_id,
                "public_key": _read_pubkey_hex(pub_ref.strip()),
                "not_before": start,
                **({"not_after": not_after} if not_after else {}),
            }
        )

    try:
        bundle = issue_bundle(
            bundle_id=bundle_id,
            keys=keys,
            root_private_key=root_priv,
            root_public_hex=root_pub_hex,
            version=new_version,
        )
    except ValueError as exc:
        console.print(f"[red]Invalid bundle:[/red] {exc}")
        raise typer.Exit(2)

    save_bundle(bundle, out)
    from epi_core.org_bundle import fingerprint_pubkey

    console.print(f"[green]✓[/green] Org bundle v{new_version} for [cyan]{bundle_id}[/cyan] → {out}")
    console.print(f"[dim]Root fingerprint: {fingerprint_pubkey(root_pub_hex)}[/dim]")
    console.print(
        "[dim]Send this file plus your artifacts to the auditor. "
        "Publish the root fingerprint out-of-band (contract, letterhead, DNS TXT).[/dim]"
    )


@bundle_app.command("verify")
def bundle_verify(
    artifact: Path = typer.Argument(..., help="Artifact .epi file"),
    bundle: Path = typer.Argument(..., help="Org trust bundle JSON file"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output"),
):
    """Verify an artifact's org identity against a bundle. Fully offline."""
    from epi_core.container import EPIContainer
    from epi_core.org_bundle import load_bundle, verify_artifact_against_bundle

    if not artifact.exists():
        console.print(f"[red]Artifact not found:[/red] {artifact}")
        raise typer.Exit(2)
    try:
        manifest = EPIContainer.read_manifest(artifact)
    except Exception as exc:
        console.print(f"[red]Cannot read artifact manifest:[/red] {exc}")
        raise typer.Exit(2)
    try:
        bundle_data = load_bundle(bundle)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2)

    report = verify_artifact_against_bundle(manifest, bundle_data)
    if as_json:
        # Write directly to stdout: Rich wraps long lines, corrupting JSON.
        import sys as _sys

        _sys.stdout.write(json.dumps(report, indent=2, default=str) + "\n")
    else:
        status = report.get("status", "UNKNOWN")
        color = {"VALID": "green", "INVALID": "red"}.get(status, "yellow")
        console.print(f"[{color}]Org identity: {status}[/{color}]")
        console.print(f"  {report.get('reason', '')}")
        if report.get("key_id"):
            console.print(
                f"  [dim]key {report['key_id']} · bundle v{report.get('bundle_version')} "
                f"({report.get('bundle_id')})[/dim]"
            )
    raise typer.Exit(0 if report.get("status") == "VALID" else 1)
