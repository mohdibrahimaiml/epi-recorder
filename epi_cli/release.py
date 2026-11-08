"""`epi release` — signed release records tied to decisions.

A release pins the exact policy, prompts, models, tool schemas, code commit
and config a version of the decision logic is allowed to use. `create` seals
it through the normal path (signature + seal sequence + witness), `approve`
adds a signed approval from the approver's own key, and `history` lists
versions in seal order. Verification is `epi verify --release`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Signed release records: create, approve, and list versions.")
console = Console()


def _plain(text: str) -> None:
    console.print(text, markup=False, highlight=False, soft_wrap=True)


def _key(key_name: str):
    from epi_core.keys import KeyManager, fingerprint_for_private_key

    km = KeyManager()
    if not km.has_key(key_name):
        km.generate_keypair(key_name)
    return km, km.load_private_key(key_name)


def _targets(url: str | None, secret: str | None) -> tuple[list[str], str | None]:
    from epi_cli.witness import _resolve_witness_targets

    return _resolve_witness_targets(url, secret)


@app.command(name="create")
def create(
    name: str = typer.Option(..., "--name", help="Release name, e.g. credit-policy."),
    version: str = typer.Option(..., "--version", help="Version, e.g. 3.2."),
    out: Path = typer.Option(..., "--out", help="Where to write the release .epi."),
    policy: list[str] = typer.Option(
        [], "--policy", help="policy file, optionally name=path. Repeatable."
    ),
    prompt: list[str] = typer.Option(
        [], "--prompt", help="prompt template, optionally name=path. Repeatable."
    ),
    model: list[str] = typer.Option(
        [], "--model", help="Exact provider:model identifier. Repeatable."
    ),
    tools: list[str] = typer.Option(
        [], "--tools", help="tool schema file, optionally name=path. Repeatable."
    ),
    config: list[str] = typer.Option(
        [], "--config", help="config file, optionally name=path. Repeatable."
    ),
    git_commit: str | None = typer.Option(
        None, "--git-commit", help="Commit sha, or 'auto' to read HEAD."
    ),
    require_approvals: int = typer.Option(
        1, "--require-approvals", help="Approvals needed before the release is approved."
    ),
    key: str = typer.Option("default", "--key", help="Signing key name."),
    witness_url: str | None = typer.Option(
        None, "--witness-url", envvar="EPI_WITNESS_URL", help="Customer witness URL."
    ),
    witness_secret: str | None = typer.Option(
        None, "--witness-secret", envvar="EPI_WITNESS_SECRET"
    ),
) -> None:
    """Seal a release record: the exact components one version may use."""
    from epi_core.container import EPIContainer
    from epi_core.release import (
        build_release_document,
        code_component,
        model_components,
        parse_component_specs,
    )
    from epi_core.schemas import ManifestModel, ReleaseModel
    from epi_core.trust import sign_manifest
    from epi_core.webhook import report_release
    from epi_core.workspace import create_recording_workspace

    try:
        components = (
            parse_component_specs(policy, "policy")
            + parse_component_specs(prompt, "prompt")
            + model_components(model)
            + parse_component_specs(tools, "tool_schema")
            + parse_component_specs(config, "config")
        )
        code = code_component(git_commit)
        if code:
            components.append(code)
        document = build_release_document(
            name=name,
            version=version,
            required_approvals=require_approvals,
            components=components,
        )
    except Exception as exc:  # noqa: BLE001
        _plain(f"Cannot build the release: {exc}")
        raise typer.Exit(2) from exc

    km, private_key = _key(key)
    from epi_core.keys import fingerprint_for_private_key

    workspace = create_recording_workspace("epi_release_")
    try:
        (workspace / "release.json").write_text(
            json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        manifest = ManifestModel(
            goal=f"release {name} {version}",
            record_kind="release",
            release=ReleaseModel(**document),
            tags=["release"],
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        EPIContainer.pack(
            workspace,
            manifest,
            out,
            signer_function=lambda current: sign_manifest(current, private_key, key),
            generate_analysis=False,
            embed_viewer=False,
            seal_fingerprint=fingerprint_for_private_key(private_key),
        )
    finally:
        import shutil

        shutil.rmtree(workspace, ignore_errors=True)

    sealed = EPIContainer.read_manifest(out)
    seq = getattr(getattr(sealed, "seal_chain", None), "seq", None)
    _plain(
        f"Release {document['release_id']} sealed"
        + (f" as #{seq}" if seq else "")
        + f": {name} {version}"
    )
    _plain(f"  Digest:    {document['release_digest']}")
    _plain(f"  Approvals: 0/{require_approvals} (draft)")
    _plain(f"  File:      {out}")
    _plain(f"  Next:      epi release approve {out} --as <approver>")

    urls, secret = _targets(witness_url, witness_secret)
    if urls:
        entry = report_release(
            out, urls=urls, secret=secret, key_name=key, signer=private_key
        )
        outcome = (entry or {}).get("_outcome") or {}
        if outcome.get("delivered") and not outcome.get("failed"):
            _plain("  Witness:   release report delivered")
        else:
            _plain("  Witness:   queued (epi witness flush)")


@app.command(name="approve")
def approve(
    epi_path: Path = typer.Argument(..., help="The release .epi to approve."),
    as_: str = typer.Option(
        ..., "--as", help="Approver name; also the key name in the approver keys dir."
    ),
    decision: str = typer.Option("approve", "--decision", help="approve or deny"),
    reason: str | None = typer.Option(None, "--reason", help="Why (shown to the verifier)."),
    yes: bool = typer.Option(False, "--yes", help="Skip the typed confirmation (tests)."),
    no_timestamp: bool = typer.Option(
        False, "--no-timestamp", help="Skip the RFC 3161 timestamp for this approval."
    ),
    witness_url: str | None = typer.Option(
        None, "--witness-url", envvar="EPI_WITNESS_URL"
    ),
    witness_secret: str | None = typer.Option(
        None, "--witness-secret", envvar="EPI_WITNESS_SECRET"
    ),
) -> None:
    """Sign one release version with an approver's own key.

    The signed review content includes the release digest, so the approval
    cannot be replayed onto another version. An `epi.release_approval` report
    is also staged to the witness, so its time is independently observed.
    """
    from cryptography.hazmat.primitives import serialization
    from rich.prompt import Prompt

    from epi_core.approvers import _resolve_default_approver_keys_dir
    from epi_core.keys import KeyManager, key_fingerprint
    from epi_core.release import ReleaseError, load_release
    from epi_core.review import ReviewRecord, add_review_to_artifact, make_release_approval_entry
    from epi_core.webhook import stage_release_approval

    if decision not in ("approve", "deny"):
        _plain("--decision must be approve or deny.")
        raise typer.Exit(2)
    try:
        release = load_release(epi_path)
    except ReleaseError as exc:
        _plain(f"Refusing to approve: {exc}")
        raise typer.Exit(1) from exc

    document = release["document"]
    keys_dir = _resolve_default_approver_keys_dir()
    try:
        private_key = KeyManager(keys_dir=keys_dir).load_private_key(as_)
    except Exception as exc:  # noqa: BLE001
        _plain(f"No approver key {as_!r} in {keys_dir}: {exc}")
        _plain("Create one: epi approvers keygen --name <approver>")
        raise typer.Exit(1) from exc

    approver_hex = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    sealing_key = str(getattr(release["manifest"], "public_key", "") or "").lower()
    if approver_hex == sealing_key:
        _plain("Refusing: separation of duties. That key sealed this release.")
        raise typer.Exit(1)

    _plain(f"Release:   {document['name']} {document['version']}")
    _plain(f"Digest:    {document['release_digest']}")
    _plain(f"Decision:  {decision}")
    _plain(f"Your fp:   {key_fingerprint(approver_hex)}")
    if not yes:
        typed = Prompt.ask(f'Type "{decision}" to sign')
        if typed.strip().lower() != decision:
            _plain("Cancelled — nothing was written.")
            raise typer.Exit(1)

    entry = make_release_approval_entry(
        release_id=str(document["release_id"]),
        release_digest=str(document["release_digest"]),
        decision=decision,
        approver_name=as_,
        key_fingerprint_hex=key_fingerprint(approver_hex, grouped=False),
        reason=reason,
    )
    record = ReviewRecord(
        reviewed_by=as_,
        reviews=[entry],
        reviewer_identity={
            "type": "email" if "@" in as_ else "name",
            "value": as_,
            "role": "Approver",
            "org": "Unknown",
            "verified": False,
        },
    )
    try:
        stamp = add_review_to_artifact(
            epi_path, record, private_key=private_key, timestamp=not no_timestamp
        )
    except Exception as exc:  # noqa: BLE001
        _plain(f"Could not write the approval: {exc}")
        raise typer.Exit(1) from exc

    _plain(f"Signed release approval written to {epi_path}")
    _plain(f"  Fingerprint: {key_fingerprint(approver_hex)}")
    _plain(f"  Review hash: {record.review_hash}")
    if stamp and stamp.get("status") == "stamped":
        _plain(f"  Independent time: {stamp.get('gen_time') or 'stamped'}")

    # Report the approval itself so verification can use the receiver's time,
    # not the approver's clock. Best-effort: never blocks the approval.
    urls, secret = _targets(witness_url, witness_secret)
    if urls:
        try:
            from epi_core.webhook import deliver_entry, witness_timeout

            queued = stage_release_approval(
                urls=urls,
                release_id=str(document["release_id"]),
                release_digest=str(document["release_digest"]),
                approval_hash=str(record.review_hash),
                approver=as_,
                approver_key_fingerprint=key_fingerprint(approver_hex, grouped=False),
                signed_at=str(entry["signed_at"]),
                public_key=approver_hex,
                key_name=as_,
                signer=private_key,
            )
            if queued is not None:
                deliver_entry(queued, secret=secret, timeout_seconds=witness_timeout())
                _plain("  Witness:      approval report sent through the outbox")
        except Exception:
            pass


@app.command(name="history")
def history(
    directory: Path = typer.Argument(Path("."), help="Directory to scan for release .epi files."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """List release records in seal order with their approval status."""
    from epi_core.approvers import ApproverRegistry
    from epi_core.release import ReleaseError, load_release, release_approvals

    rows: list[dict] = []
    registry = ApproverRegistry()
    for path in sorted(Path(directory).rglob("*.epi")):
        try:
            loaded = load_release(path)
        except Exception:
            continue
        document = loaded["document"]
        approvals = release_approvals(
            path, loaded["release_digest"], registry=registry
        )
        pinned = [item for item in approvals if item.get("pinned")]
        chain = loaded.get("seal_chain")
        rows.append(
            {
                "path": str(path),
                "release_id": loaded["release_id"],
                "name": document.get("name"),
                "version": document.get("version"),
                "digest": loaded["release_digest"],
                "sealed_at": loaded.get("sealed_at"),
                "seq": getattr(chain, "seq", None),
                "approvals": len(pinned),
                "required": int(document.get("required_approvals") or 1),
                "status": (
                    "approved"
                    if len(pinned) >= int(document.get("required_approvals") or 1)
                    else "draft"
                ),
            }
        )
    rows.sort(key=lambda row: (row["seq"] is None, row["seq"] or 0, row["sealed_at"] or ""))
    if as_json:
        console.print_json(json.dumps({"releases": rows}))
        return
    if not rows:
        _plain(f"No release records found under {directory}.")
        return
    table = Table(title=f"Releases ({directory})")
    table.add_column("id", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("version")
    table.add_column("sealed (UTC)")
    table.add_column("seq", justify="right")
    table.add_column("approvals", justify="right")
    table.add_column("status")
    for row in rows:
        table.add_row(
            str(row["release_id"]),
            str(row["name"]),
            str(row["version"]),
            str(row["sealed_at"] or "-")[:19].replace("T", " "),
            str(row["seq"] or "-"),
            f"{row['approvals']}/{row['required']}",
            row["status"],
        )
    console.print(table)
