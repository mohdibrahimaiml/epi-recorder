"""`epi approval` — sign pre-action approval requests with the approver's key.

The vendor's gate writes a request into its approvals inbox. `export` copies it
for an approver on another machine; `sign` runs there, with the approver's own
key; `import` returns the response to the inbox the gate is waiting on. A
request can also be signed in place when the approver shares the machine (the
gate openly flags that as not independent).

The approver signs the request digest, which binds the tool, the canonical
arguments, the nonce and the expiry. `args_display` shows the exact non-secret
values; `redacted_fields` names what was approved blind.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Pre-action approvals: list requests, sign, export and import.")
console = Console()


def _plain(text: str) -> None:
    console.print(text, markup=False, highlight=False, soft_wrap=True)


def _inbox() -> Path:
    from epi_recorder.trust.approval import _inbox_dir

    return _inbox_dir()


def _load_request(value: str) -> dict:
    from epi_core.pre_action import validate_request

    path = Path(value).expanduser()
    if not path.is_file():
        path = _inbox() / f"{value}.request.json"
    if not path.is_file():
        raise FileNotFoundError(f"approval request not found: {value}")
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"request file is not valid JSON: {exc}") from exc
    ok, why = validate_request(request)
    if not ok:
        raise ValueError(why)
    return request


def _verify_producer(request: dict) -> str | None:
    signature = str(request.get("producer_signature") or "")
    public_key = str(request.get("producer_public_key") or "")
    if not signature:
        return "vendor signature absent (the request is still bound by its digest)"
    parts = signature.split(":", 2)
    if len(parts) != 3 or parts[0] != "ed25519" or parts[1].lower() != public_key.lower():
        return "vendor signature does not name the producer key"
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
            bytes.fromhex(parts[2]),
            bytes.fromhex(str(request.get("request_digest") or "")),
        )
        return None
    except Exception:
        return "vendor signature does not verify (request may have been altered)"


@app.command(name="list")
def list_requests(as_json: bool = typer.Option(False, "--json")) -> None:
    """List request files waiting in the approvals inbox."""
    rows = []
    for path in sorted(_inbox().glob("*.request.json")):
        try:
            request = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        request_id = str(request.get("request_id") or path.name.split(".")[0])
        response_path = _inbox() / f"{request_id}.response.json"
        rows.append(
            {
                "request_id": request_id,
                "tool": request.get("tool"),
                "expires_at": request.get("expires_at"),
                "vendor_description": request.get("vendor_description"),
                "answered": response_path.is_file(),
            }
        )
    if as_json:
        console.print_json(json.dumps({"requests": rows}))
        return
    if not rows:
        _plain(f"No approval requests in {_inbox()}.")
        return
    table = Table(title=f"Approval requests ({_inbox()})")
    table.add_column("request", no_wrap=True)
    table.add_column("tool", no_wrap=True)
    table.add_column("expires (UTC)")
    table.add_column("answered")
    for row in rows:
        table.add_row(
            str(row["request_id"]),
            str(row["tool"]),
            str(row["expires_at"] or "-")[:19].replace("T", " "),
            "yes" if row["answered"] else "no",
        )
    console.print(table)


@app.command(name="export")
def export(
    request_id: str = typer.Argument(..., help="Request id in the inbox, or a request file."),
    out: Path = typer.Option(..., "--out", help="Where to write the request bundle."),
) -> None:
    """Copy a request for an approver on another machine."""
    request = _load_request(request_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _plain(f"Exported {request.get('request_id')} to {out}")
    _plain(f"Approver runs: epi approval sign {out} --as <name> --out <response>.json")


@app.command(name="sign")
def sign(
    request_ref: str = typer.Argument(..., help="Request id in the inbox, or a request JSON file."),
    as_: str = typer.Option(..., "--as", help="Approver name; key name in the approver keys dir."),
    decision: str = typer.Option("approve", "--decision", help="approve or deny"),
    reason: str | None = typer.Option(None, "--reason"),
    out: Path | None = typer.Option(
        None, "--out", help="Response file (default: ./<request_id>.response.json)."
    ),
    inbox: bool = typer.Option(
        False, "--inbox", help="Write straight into the local approvals inbox."
    ),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt (tests)."),
) -> None:
    """Sign this exact pre-action request with the approver's own key."""
    from cryptography.hazmat.primitives import serialization

    from epi_core.approvers import _resolve_default_approver_keys_dir
    from epi_core.keys import KeyManager, key_fingerprint
    from epi_core.pre_action import (
        args_digest,
        sign_response,
        verify_response_signature,
    )

    if decision not in ("approve", "deny"):
        _plain("--decision must be approve or deny.")
        raise typer.Exit(2)
    try:
        request = _load_request(request_ref)
    except Exception as exc:  # noqa: BLE001
        _plain(str(exc))
        raise typer.Exit(1) from exc

    producer_problem = _verify_producer(request)
    if producer_problem and "absent" not in producer_problem:
        _plain(f"Refusing: {producer_problem}")
        raise typer.Exit(1)

    display = request.get("args_display")
    if not isinstance(display, dict):
        _plain("Refusing: request has no argument display to approve.")
        raise typer.Exit(1)
    redacted = list(request.get("redacted_fields") or [])
    if not redacted:
        actual = args_digest(str(request.get("tool") or ""), display)
        if actual != str(request.get("args_digest") or ""):
            _plain(
                "Refusing: the displayed arguments do not match the approved digest "
                "(the request is inconsistent)."
            )
            raise typer.Exit(1)

    keys_dir = _resolve_default_approver_keys_dir()
    try:
        private_key = KeyManager(keys_dir=keys_dir).load_private_key(as_)
    except Exception as exc:  # noqa: BLE001
        _plain(f"No approver key {as_!r} in {keys_dir}: {exc}")
        _plain("Create one: epi approvers keygen --name <approver>")
        raise typer.Exit(1) from exc

    public_hex = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    producer_key = str(request.get("producer_public_key") or "").lower()
    if producer_key and producer_key == public_hex.lower():
        _plain("Refusing: separation of duties. That key produced this request.")
        raise typer.Exit(1)

    _plain(f"Request:    {request.get('request_id')}")
    _plain(f"Tool:       {request.get('tool')}")
    _plain(f"Expires:    {request.get('expires_at')}")
    _plain("Arguments (the values covered by args_digest):")
    _plain(json.dumps(display, indent=2, ensure_ascii=False, sort_keys=True))
    if redacted:
        _plain(
            f"Approved blind: {', '.join(redacted)} (redacted; their exact values "
            "are not in the request)."
        )
    else:
        _plain("Approved blind: none — every displayed value is exact.")
    if request.get("vendor_description"):
        _plain(
            "Vendor description (not the approved arguments): "
            + str(request.get("vendor_description"))
        )
    if producer_problem:
        _plain(f"Note: {producer_problem}")
    _plain(f"Your fp:    {key_fingerprint(public_hex)}")

    if not yes:
        from rich.prompt import Prompt

        typed = Prompt.ask(f'Type "{decision}" to sign')
        if typed.strip().lower() != decision:
            _plain("Cancelled — nothing was written.")
            raise typer.Exit(1)

    response = sign_response(
        request,
        decision=decision,
        approver=as_,
        key_fingerprint=key_fingerprint(public_hex, grouped=False),
        public_key=public_hex,
        private_key=private_key,
        reason=reason,
    )
    ok, why = verify_response_signature(response)
    if not ok:
        _plain(f"Internal error: {why}")
        raise typer.Exit(1)

    target = out
    if target is None:
        target = (
            _inbox() / f"{request['request_id']}.response.json"
            if inbox
            else Path.cwd() / f"{request['request_id']}.response.json"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(response, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _plain(f"Signed {decision} response written to {target}")

    urls = [u for u in str(os.environ.get("EPI_WITNESS_URL") or "").split(",") if u.strip()]
    if urls:
        try:
            from epi_core.webhook import report_approval_response

            report_approval_response(
                request,
                response,
                urls=urls,
                secret=os.environ.get("EPI_WITNESS_SECRET"),
                timeout_seconds=2.0,
            )
            _plain("Approval response report sent to the witness.")
        except Exception:
            pass


@app.command(name="import")
def import_response(
    response_path: Path = typer.Argument(..., help="Response JSON produced by `epi approval sign`."),
) -> None:
    """Put a signed response into the inbox the gate is waiting on."""
    from epi_core.pre_action import verify_response_signature

    try:
        response = json.loads(response_path.read_text(encoding="utf-8"))
        if not isinstance(response, dict):
            raise ValueError("response is not a JSON object")
    except Exception as exc:  # noqa: BLE001
        _plain(f"Cannot read response: {exc}")
        raise typer.Exit(1) from exc
    ok, why = verify_response_signature(response)
    if not ok:
        _plain(f"Refusing to import an invalid response: {why}")
        raise typer.Exit(1)
    request_id = str(response.get("request_id") or "")
    if not request_id:
        _plain("Refusing: response has no request_id.")
        raise typer.Exit(1)
    target = _inbox() / f"{request_id}.response.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(response, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _plain(f"Imported approval response for {request_id} into {target}")
