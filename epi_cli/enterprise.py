"""Enterprise evidence kit: bootstrap org trust + auditor pack.

Designed for regulated buyers who need a file-first path:
  org keys → trust bundle → policy → CI recipe → auditor kit from a .epi
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

console = Console(legacy_windows=False)

enterprise_app = typer.Typer(
    name="enterprise",
    help="Enterprise evidence kit: org trust bootstrap and auditor packs.",
    no_args_is_help=True,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@enterprise_app.command("setup")
@enterprise_app.command("bootstrap")
def bootstrap(
    out: Path = typer.Option(
        Path("enterprise-epi"),
        "--out",
        "-o",
        help="Directory to write the enterprise kit into",
    ),
    key_name: str = typer.Option(
        "org-seal",
        "--key-name",
        "-k",
        help="Label for the org key inside the kit (display only, not a key lookup).",
    ),
    org_pubkey: Path | None = typer.Option(
        None,
        "--org-pubkey",
        help=(
            "Path to the org's PUBLIC sealing key (PEM, 64-hex .pub, or signed .epi). "
            "Generate it on your own hardware with: epi keys generate --name org-seal. "
            "EPI never accepts a private key here."
        ),
    ),
    policy_profile: str = typer.Option(
        "starter",
        "--policy-profile",
        "-p",
        help="Built-in policy profile name, or 'starter'",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing kit files"),
):
    """Scaffold org trust, policy, and CI recipe for enterprise evidence."""
    from epi_core.keys import KeyManager, export_trust_bundle
    from epi_core.policy import (
        build_policy_from_profile,
        build_starter_policy,
        list_policy_profiles,
    )
    from epi_core.trust import TrustRegistry

    out = out.resolve()
    if out.exists() and any(out.iterdir()) and not force:
        console.print(
            f"[red]Directory not empty:[/red] {out}\n"
            "[dim]Use --force to overwrite kit files, or choose another --out.[/dim]"
        )
        raise typer.Exit(1)

    out.mkdir(parents=True, exist_ok=True)
    km = KeyManager()

    # 1) Org public sealing key — customer-supplied ONLY.
    # EPI never generates or accepts a customer private key in this flow:
    # generation happens on customer hardware, and only public material
    # crosses into this command. This is structural, not advisory.
    if org_pubkey is None:
        console.print(
            "[red]Refusing:[/red] no org public key provided.\n"
            "[dim]Generate one on your own hardware, then re-run with its public half:\n"
            "  epi keys generate --name org-seal\n"
            f"  epi enterprise bootstrap --org-pubkey <path-to-org-seal.pub>\n"
            "Accepted public formats: PEM, 64-hex .pub, or a signed .epi "
            "(pins manifest.public_key). Private key material is never accepted here.[/dim]"
        )
        raise typer.Exit(2)
    org_pubkey = org_pubkey.resolve()
    if not org_pubkey.exists():
        console.print(f"[red]Org public key not found:[/red] {org_pubkey}")
        raise typer.Exit(2)

    # 2) Pin public key into local trust store
    trusted_name = f"enterprise-{key_name}"
    try:
        tr = TrustRegistry()
        trust_path = km.trust_key(
            org_pubkey,
            trusted_keys_dir=tr.trusted_keys_dir,
            trusted_name=trusted_name,
            overwrite=force,
        )
        console.print(f"[green]✓[/green] Trusted as [cyan]{trusted_name}[/cyan] → {trust_path}")
    except FileExistsError:
        console.print(f"[dim]Trusted key {trusted_name} already exists — reusing.[/dim]")
        trust_path = tr.trusted_keys_dir / f"{trusted_name}.pub"
    except Exception as exc:
        console.print(f"[red]Org public key rejected:[/red] {exc}")
        console.print(
            "  [dim]Expected PEM, 64-hex .pub, or a signed .epi artifact.[/dim]"
        )
        raise typer.Exit(2)

    # 3) Trust bundle (public keys only — exactly the pinned org key, nothing
    # swept in from the local signing namespace)
    bundle_path = out / "org-trust-bundle.zip"
    try:
        export_trust_bundle(
            km,
            bundle_path,
            pubs=[(trusted_name, trust_path.read_text(encoding="utf-8"))],
        )
        console.print(f"[green]✓[/green] Trust bundle: {bundle_path}")
    except Exception as exc:
        console.print(f"[yellow]![/yellow] Bundle export failed: {exc}")
        console.print(f"  [dim]Manual: epi keys bundle-export --out {bundle_path}[/dim]")

    # 4) Policy
    policy_path = out / "epi_policy.json"
    profiles = list_policy_profiles()
    try:
        sys_kwargs = dict(
            system_name="enterprise-agent",
            system_version="1.0",
            policy_version="1.0",
        )
        if policy_profile in profiles:
            payload = build_policy_from_profile(policy_profile, **sys_kwargs)
        elif policy_profile in ("starter", "custom") or not profiles:
            from epi_core.policy import list_starter_rule_types

            payload = build_starter_policy(
                **sys_kwargs,
                rule_types=list_starter_rule_types()[:4],
            )
        else:
            payload = build_policy_from_profile(profiles[0], **sys_kwargs)
            console.print(f"[dim]Unknown profile {policy_profile}; used {profiles[0]}[/dim]")
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json")
        _write(policy_path, json.dumps(payload, indent=2))
        console.print(f"[green]✓[/green] Policy: {policy_path}")
    except Exception as exc:
        console.print(f"[yellow]![/yellow] Policy write failed: {exc}")

    # 5) CI workflow recipe
    ci_path = out / ".github" / "workflows" / "epi-enterprise-verify.yml"
    ci_yaml = """# Enterprise evidence gate — copy into your app repo as needed.
name: EPI Enterprise Verify
on:
  pull_request:
  push:
    branches: [main, master]
jobs:
  verify-epi:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install EPI
        run: pip install epi-recorder
      - name: Import org trust bundle
        run: |
          if [ -f enterprise-epi/org-trust-bundle.zip ]; then
            epi keys bundle-import enterprise-epi/org-trust-bundle.zip
          elif [ -f org-trust-bundle.zip ]; then
            epi keys bundle-import org-trust-bundle.zip
          else
            echo "No trust bundle found — verify may WARN on identity"
          fi
      - name: Verify .epi artifacts
        uses: mohdibrahimaiml/epi-recorder/.github/actions/verify-epi@main
        with:
          path: ./epi-recordings
          fail-on-tampered: "true"
          fail-on-unsigned: "true"
          generate-summary: "true"
"""
    _write(ci_path, ci_yaml)
    console.print(f"[green]✓[/green] CI recipe: {ci_path}")

    # 6) README
    readme = f"""# Enterprise EPI kit

Generated {datetime.now(UTC).isoformat()}

## What this is

File-first evidence for AI agents: **org seal keys**, **trust bundle**, **policy**, **CI gate**.
Auditors verify **offline** from `.epi` files — not a dashboard login.

## Quick path (30 minutes)

```bash
# Seal agent runs with org key: {key_name}
# (configure your recorder / EPI_KEY as your deployment does)

# On CI / auditor machines:
epi keys bundle-import org-trust-bundle.zip
epi verify path/to/run.epi --policy strict

# Auditor pack from a sealed file:
epi enterprise kit path/to/run.epi --out auditor-pack.zip
```

## Files

| File | Purpose |
|------|---------|
| `org-trust-bundle.zip` | Public keys only — share with CI/auditors |
| `epi_policy.json` | Fault/policy rules |
| `.github/workflows/epi-enterprise-verify.yml` | CI gate template |
| `README.md` | This guide |

## Private key

Private key under `~/.epi/keys/` (name: **{key_name}**). **Never commit private keys.**

## Air-gapped seal

```bash
set EPI_NOTARIZE=0
```

## Docs

- docs/ENTERPRISE-EVIDENCE-PLAYBOOK.md
- docs/EPI_MASTER_DOCUMENTATION.md
- docs/SELF-HOSTED-RUNBOOK.md
"""
    _write(out / "README.md", readme)
    console.print(f"[green]✓[/green] README: {out / 'README.md'}")
    console.print(
        f"\n[bold green]Done. Your company kit is ready:[/bold green] {out}\n\n"
        f"[bold]Next 3 steps[/bold]\n"
        f"  1. Record an agent run into a .epi file\n"
        f"  2. [cyan]epi enterprise pack your-run.epi[/cyan]\n"
        f"  3. Send [cyan]auditor-pack.zip[/cyan] to your auditor\n\n"
        f"[dim]Key: {key_name} · Never commit private keys · "
        f"Share only org-trust-bundle.zip with CI[/dim]\n"
    )


@enterprise_app.command("pack")
@enterprise_app.command("kit")
def kit(
    artifact: Path = typer.Argument(..., exists=True, help="Path to sealed .epi file"),
    out: Path = typer.Option(
        Path("auditor-pack.zip"),
        "--out",
        "-o",
        help="Output zip path for the auditor pack",
    ),
    strict: bool = typer.Option(True, "--strict/--no-strict", help="Strict audit mode"),
):
    """Build an auditor pack (verify + audit reports + copy of .epi)."""
    from epi_cli.audit import _render_markdown, audit_artifact
    from epi_core.container import EPIContainer

    artifact = artifact.resolve()
    work = out.with_suffix("").resolve() if out.suffix == ".zip" else out.resolve()
    if work.exists() and work.is_dir():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    shutil.copy2(artifact, work / artifact.name)

    try:
        report = audit_artifact(artifact, output_format="json", strict=strict)
        _write(work / "audit.json", json.dumps(report, indent=2, default=str))
        _write(work / "audit.md", _render_markdown(report))
        console.print("[green]✓[/green] audit.json + audit.md")
    except Exception as exc:
        console.print(f"[yellow]![/yellow] Audit skipped: {exc}")

    try:
        p = subprocess.run(
            [sys.executable, "-m", "epi_cli", "verify", str(artifact)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        _write(work / "verify.txt", (p.stdout or "") + "\n" + (p.stderr or ""))
        console.print(f"[green]✓[/green] verify.txt (exit {p.returncode})")
    except Exception as exc:
        _write(work / "verify.txt", f"verify failed to run: {exc}\n")

    try:
        manifest = EPIContainer.read_manifest(artifact)
        if hasattr(manifest, "model_dump"):
            m = manifest.model_dump(mode="json")
        elif isinstance(manifest, dict):
            m = manifest
        else:
            m = {"raw": str(manifest)}
        _write(
            work / "manifest-summary.json",
            json.dumps(m, indent=2, default=str)[:500_000],
        )
        console.print("[green]✓[/green] manifest-summary.json")
    except Exception as exc:
        console.print(f"[yellow]![/yellow] manifest summary skipped: {exc}")

    _write(
        work / "README.md",
        f"""# Auditor pack

Artifact: `{artifact.name}`  
Built: {datetime.now(UTC).isoformat()}

## Independent verify

```bash
pip install epi-recorder
epi verify {artifact.name}
epi keys bundle-import org-trust-bundle.zip
epi verify {artifact.name} --policy strict
```

Integrity and signature are offline. Identity is HIGH only when the sealer key is trusted.
""",
    )

    zip_path = out if out.suffix == ".zip" else Path(str(out) + ".zip")
    zip_path = zip_path.resolve()
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in work.rglob("*"):
            if f.is_file():
                zf.write(f, arcname=f.relative_to(work).as_posix())

    console.print(f"\n[bold green]Auditor pack:[/bold green] {zip_path}\n")


@enterprise_app.command("capabilities")
def capabilities():
    """Print what EPI provides for enterprise (honest inventory)."""
    console.print(
        """
[bold]EPI Enterprise capability inventory[/bold]

[green]Shipped today[/green]
  • Portable sealed .epi (Ed25519 + hash integrity)
  • Offline verify / view (air-gap: EPI_NOTARIZE=0)
  • Org keys + trust bundles
  • Policy + fault analysis
  • Annex IV tooling + multi-sign + CLI PDF
  • GitHub Action verify-epi
  • Optional hosted verify + remote SCITT (plan-gated)
  • Self-hosted gateway / Decision Ops
  • epi enterprise bootstrap / kit

[yellow]Services / contract[/yellow]
  • Dedicated onboarding, custom limits, legal/procurement
  • SLA only if signed in writing

[dim]Not shipped as product[/dim]
  • Cloud SSO/SAML · multi-tenant SaaS seats · FDA/HIPAA adapter suite
  • Managed multi-tenant DID registry · hosted PDF API (use CLI)

Commands (simple path):
  epi enterprise setup
  epi enterprise pack <file.epi>
  epi enterprise capabilities
"""
    )
