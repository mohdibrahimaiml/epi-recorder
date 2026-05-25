"""
EPI CLI Verify - Verify .epi file integrity and authenticity.

Performs comprehensive verification including:
- Structural validation (ZIP format, mimetype, manifest schema)
- Integrity checks (file hashes match manifest)
- Authenticity checks (Ed25519 signature verification)
"""

import json
import sys
from datetime import UTC
from pathlib import Path
from typing import Annotated

import cbor2
import typer
from rich.console import Console
from rich.panel import Panel

from epi_cli.view import _resolve_epi_file
from epi_core._version import get_version
from epi_core.aiuc1_mapping import map_verification_to_aiuc1, aiuc1_summary
from epi_core.container import EPIContainer
from epi_core.review import verify_review_trust
from epi_core.trust import (
    TrustRegistry,
    VerificationPolicy,
    apply_policy,
    create_verification_report,
    verify_embedded_manifest_signature,
)

console = Console()


def _fetch_scitt_service_key(service_url: str | None) -> bytes | None:
    """
    Fetch and cache the SCITT transparency service's Ed25519 public key.

    Args:
        service_url: URL of the SCITT service (e.g., https://scitt.epilabs.org)

    Returns:
        32-byte raw Ed25519 public key, or None if unavailable.
    """
    if not service_url:
        return None

    import hashlib
    from pathlib import Path

    cache_dir = Path.home() / ".epi" / "scitt_service_keys"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(service_url.encode()).hexdigest()[:16]
    cache_file = cache_dir / f"{cache_key}.pub"

    # Return cached key if present and not expired (24h TTL)
    CACHE_TTL_SECONDS = 86400
    if cache_file.exists():
        try:
            import time
            if time.time() - cache_file.stat().st_mtime < CACHE_TTL_SECONDS:
                return bytes.fromhex(cache_file.read_text().strip())
            # Expired: delete and fall through to re-fetch
            cache_file.unlink(missing_ok=True)
        except Exception:
            pass

    # Fetch from service
    try:
        from epi_core.scitt import SCITTServiceClient
        client = SCITTServiceClient(service_url)
        key_bytes = client.get_public_key()
        cache_file.write_text(key_bytes.hex())
        return key_bytes
    except Exception:
        return None


def _verify_step_chain(steps: list[dict]) -> tuple[bool, list[str]]:
    """
    Verify the prev_hash cryptographic chain in a list of steps.

    Each step's ``prev_hash`` must equal the JSON canonical hash of the
    previous step.  Steps with ``prev_hash == "CHAIN_START"`` or ``None``
    are skipped (genesis steps).

    Returns:
        tuple: (chain_ok: bool, chain_breaks: list of human-readable messages)

    Old artifacts that used CBOR-style hashing may fail schema validation;
    those specific errors are handled gracefully.  Unexpected runtime errors
    are reported as a chain break rather than silently passing.
    """
    if len(steps) < 2:
        return True, []

    try:
        from epi_core.schemas import StepModel
        from epi_core.serialize import get_canonical_hash

        chain_breaks: list[str] = []
        step_models = [StepModel(**s) for s in steps]
        for i in range(1, len(step_models)):
            claimed_prev = step_models[i].prev_hash
            if claimed_prev is None or claimed_prev == "CHAIN_START":
                continue
            expected_hash = get_canonical_hash(step_models[i - 1], format="json")
            if claimed_prev != expected_hash:
                # Fallback: check CBOR canonical hash for legacy artifacts
                expected_cbor_hash = get_canonical_hash(step_models[i - 1], format="cbor")
                if claimed_prev != expected_cbor_hash:
                    chain_breaks.append(f"step {i}: prev_hash mismatch")
        return len(chain_breaks) == 0, chain_breaks
    except (ValueError, TypeError):
        # Old artifacts (CBOR-hashed chains) or steps with unexpected field
        # types: default to True so legacy artifacts do not falsely fail.
        return True, []
    except Exception as exc:  # noqa: BLE001
        # Unexpected error: do not silently pass — report it as a chain break
        # so operators are aware something went wrong during chain validation.
        return False, [f"chain verification error: {exc}"]


def _audit_step_sequence_completeness(steps: list[dict]) -> tuple[bool, list[str]]:
    """
    AUD-CO-01: Step Sequence Completeness Audit.
    Ensures:
      - Every tool.call has a corresponding tool.response
      - Every llm.request has a corresponding llm.response or llm.error
      - Every agent.approval.request has a corresponding agent.approval.response
    """
    gaps: list[str] = []
    
    pending_tool_calls: list[tuple[int, str | None]] = []
    pending_llm_requests: list[tuple[int, str | None]] = []
    pending_approvals: list[tuple[int, str | None]] = []
    
    for s in steps:
        kind = s.get("kind", "")
        content = s.get("content", {}) or {}
        idx = s.get("index", 0)
        span_id = s.get("span_id")
        
        if kind == "tool.call":
            call_id = content.get("call_id")
            pending_tool_calls.append((idx, call_id))
        elif kind == "tool.response":
            call_id = content.get("call_id")
            matched = False
            if call_id is not None:
                for item in reversed(pending_tool_calls):
                    if item[1] == call_id:
                        pending_tool_calls.remove(item)
                        matched = True
                        break
            if not matched and pending_tool_calls:
                pending_tool_calls.pop(0)
                
        elif kind == "llm.request":
            pending_llm_requests.append((idx, span_id))
        elif kind in ("llm.response", "llm.error"):
            matched = False
            if span_id is not None:
                for item in reversed(pending_llm_requests):
                    if item[1] == span_id:
                        pending_llm_requests.remove(item)
                        matched = True
                        break
            if not matched and pending_llm_requests:
                pending_llm_requests.pop(0)
                
        elif kind == "agent.approval.request":
            action = content.get("action")
            pending_approvals.append((idx, action))
        elif kind == "agent.approval.response":
            action = content.get("action")
            matched = False
            if action is not None:
                for item in reversed(pending_approvals):
                    if item[1] == action:
                        pending_approvals.remove(item)
                        matched = True
                        break
            if not matched and pending_approvals:
                pending_approvals.pop(0)
                
    for idx, call_id in pending_tool_calls:
        gaps.append(f"tool.call at step {idx} is missing a corresponding tool.response")
    for idx, span_id in pending_llm_requests:
        gaps.append(f"llm.request at step {idx} is missing a corresponding response or error")
    for idx, action in pending_approvals:
        gaps.append(f"agent.approval.request for '{action}' at step {idx} is missing a response")
        
    return len(gaps) == 0, gaps


def _print_share_hint() -> None:
    """Show the lowest-friction next steps after a successful verification."""
    console.print("")
    console.print("[bold]Share / review this case file:[/bold]")
    console.print("  [cyan]epi share <file.epi>[/cyan]       hosted link that opens in any browser")
    console.print(
        "  [cyan]https://epilabs.org/verify[/cyan]  browser trust check, no install required"
    )
    console.print("  [cyan]epi connect open[/cyan]           local team review workspace")


def _print_qr_code(url: str) -> None:
    """Print a QR code in the terminal. Falls back to URL box if qrcode not installed."""
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make()
        # Print compact ASCII QR
        for row in qr.modules:
            line = ""
            for cell in row:
                line += "██" if cell else "  "
            console.print(f"[bold]{line}[/bold]")
    except Exception:
        # Fallback: draw a nice box with the URL
        console.print("┌" + "─" * 50 + "┐")
        console.print("│" + " " * 50 + "│")
        console.print("│" + url.center(50) + "│")
        console.print("│" + " " * 50 + "│")
        console.print("└" + "─" * 50 + "┘")


def _emit_json_report(report: dict) -> None:
    """Write a machine-readable verification report directly to stdout."""
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    sys.stdout.flush()


def _build_failure_report(
    message: str,
    *,
    error_type: str,
    signature_valid: bool | None = None,
    signer_name: str | None = None,
    has_signature: bool = False,
    mismatches: dict[str, str] | None = None,
) -> dict:
    """Return a consistent JSON failure payload for pre-manifest verification errors."""
    mismatch_map = mismatches or {}
    return {
        "facts": {
            "integrity_ok": False,
            "signature_valid": signature_valid,
            "has_signature": has_signature,
            "sequence_ok": False,
            "completeness_ok": False,
            "mismatches": mismatch_map,
        },
        "identity": {
            "status": "UNKNOWN",
            "name": signer_name,
            "detail": message,
        },
        "summary": {
            "integrity": "FAILED",
            "trust": "NONE",
        },
        "decision": {"status": "FAIL", "policy": "none", "reason": message},
        # Legacy flat fields for backward compatibility
        "integrity_ok": False,
        "signature_valid": signature_valid,
        "trust_level": "NONE",
        "has_signature": has_signature,
        "mismatches_count": len(mismatch_map),
        "signer": signer_name,
        "files_checked": 0,
        "workflow_id": None,
        "created_at": None,
        "spec_version": None,
        "error": message,
        "error_type": error_type,
    }


def _handle_verification_error(
    *,
    message: str,
    json_output: bool,
    console_message: str | None = None,
    error_type: str = "verification_failed",
    signature_valid: bool | None = None,
    signer_name: str | None = None,
    has_signature: bool = False,
    mismatches: dict[str, str] | None = None,
) -> None:
    """Emit a user-facing or JSON verification failure and exit 1."""
    if json_output:
        _emit_json_report(
            _build_failure_report(
                message,
                error_type=error_type,
                signature_valid=signature_valid,
                signer_name=signer_name,
                has_signature=has_signature,
                mismatches=mismatches,
            )
        )
    else:
        console.print(console_message or message)
    raise typer.Exit(1)


def _write_verification_report(report: dict, epi_file: Path, report_out: Path) -> None:
    """Serialise a verification report dict to a plain-text file."""
    from datetime import datetime

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    result_line = (
        "VERIFIED ✓"
        if report["trust_level"] == "HIGH"
        else (
            "VERIFIED (unsigned) ✓"
            if report["trust_level"] == "MEDIUM"
            else (
                "VALID SIGNATURE (unknown identity) ⚠"
                if report["trust_level"] == "LOW"
                else (
                    "IDENTITY MISMATCH — IMPERSONATION DETECTED ✗"
                    if report["trust_level"] == "FAIL"
                    else "FAILED ✗"
                )
            )
        )
    )
    integrity_line = (
        f"PASSED — {report['files_checked']} files verified (SHA-256)"
        if report["integrity_ok"]
        else f"FAILED — {report['mismatches_count']} file(s) modified"
    )
    if report["signature_valid"]:
        sig_line = f"VALID — Ed25519, signed by key '{report['signer']}'"
    elif report["signature_valid"] is None:
        sig_line = "NOT SIGNED — no signature present"
    else:
        sig_line = "INVALID — signature does not match"

    if report["trust_level"] == "HIGH":
        suitable = (
            "\nThis artifact has not been modified since it was signed.\n"
            "It is suitable for submission as evidence to regulators,\n"
            "auditors, or legal proceedings."
        )
    elif report["trust_level"] == "MEDIUM":
        suitable = (
            "\nIntegrity intact but artifact is unsigned.\nConsider signing with: epi keys generate"
        )
    elif report["trust_level"] == "LOW":
        suitable = (
            "\nSignature is valid but signer identity is UNKNOWN.\n"
            "This may be a key substitution attack. Do not trust without\n"
            "independent identity verification (e.g. DID:WEB or trust registry)."
        )
    elif report["trust_level"] == "FAIL":
        suitable = (
            "\nIDENTITY MISMATCH DETECTED. The signer claims an identity\n"
            "that does not match their cryptographic key. This is an\n"
            "active impersonation attempt. Do not trust this artifact."
        )
    else:
        suitable = "\nThis artifact FAILED verification and should not be trusted."

    lines = [
        "EPI VERIFICATION REPORT",
        f"Generated: {generated}",
        f"File: {epi_file.name}",
        "",
        f"RESULT: {result_line}",
        f"Trust Level: {report['trust_level']}",
        "",
        f"Integrity Check:  {integrity_line}",
        f"Signature Check:  {sig_line}",
        "",
        "ARTIFACT DETAILS",
        f"Workflow:     {report['workflow_id']}",
        f"Created:      {report['created_at']}",
        f"Spec Version: {report['spec_version']}",
        suitable,
        "",
        "---",
        "Verified by EPI (Evidence Packaged Infrastructure)",
        f"epi verify {epi_file.name}",
    ]
    report_out.write_text("\n".join(lines), encoding="utf-8")


def verify_command(
    ctx: typer.Context,
    epi_file: Path,
    json_output: bool = False,
    verbose: bool = False,
    report_out: Path | None = None,
    review: bool = False,
    strict: bool = False,
    aiuc1: bool = typer.Option(
        False,
        "--aiuc1",
        help="Include AIUC-1 trust domain mapping in the verification report",
    ),
    policy: Annotated[
        VerificationPolicy,
        typer.Option("--policy", help="Governance policy to apply (permissive, standard, strict)"),
    ] = VerificationPolicy.STANDARD,
    web: bool = typer.Option(
        False,
        "--web",
        help="Open verification results in browser at verify.epilabs.org after CLI check",
    ),
    qr: bool = typer.Option(
        False,
        "--qr",
        help="Print a QR code that opens the artifact on verify.epilabs.org",
    ),
) -> None:
    """
    Verify .epi file integrity and authenticity.

    Performs three levels of verification:
    1. Structural: ZIP format, mimetype, manifest schema
    2. Integrity: File hashes match manifest
    3. Authenticity: Ed25519 signature validation
    """
    try:
        epi_file = _resolve_epi_file(str(epi_file))
    except FileNotFoundError:
        _handle_verification_error(
            message=f"File not found: {epi_file}",
            json_output=json_output,
            console_message=f"[red][FAIL] Error:[/red] File not found: {epi_file}",
            error_type="file_not_found",
        )

    # Initialize verification state
    manifest = None
    integrity_ok = False
    signature_valid = None
    signer_name = None
    mismatches = {}
    review_report = None
    registry = TrustRegistry()

    try:
        # ========== STEP 1: STRUCTURAL VALIDATION ==========
        if verbose:
            console.print("\n[bold]Step 1: Structural Validation[/bold]")

        # Read manifest (validates ZIP format and mimetype)
        try:
            manifest = EPIContainer.read_manifest(epi_file)
            if verbose:
                console.print("  [green][OK][/green] Valid ZIP format")
                console.print("  [green][OK][/green] Valid mimetype")
                console.print("  [green][OK][/green] Valid manifest schema")

            # Version compatibility check
            supported_versions = [get_version()]
            if manifest.spec_version not in supported_versions:
                if verbose:
                    console.print(
                        f"  [yellow]![/yellow] Unsupported spec_version "
                        f"'{manifest.spec_version}' (supported: {supported_versions})"
                    )
                # We still continue but this can be checked by policy later
        except Exception as e:
            _handle_verification_error(
                message=f"Structural validation failed: {e}",
                json_output=json_output,
                console_message=f"[red][FAIL] Structural validation failed:[/red] {e}",
                error_type="structural_validation_failed",
            )

        # ========== STEP 2: INTEGRITY CHECKS (Facts) ==========
        if verbose:
            console.print("\n[bold]Step 2: Integrity Checks (Facts)[/bold]")

        integrity_ok, mismatches = EPIContainer.verify_integrity(epi_file)

        # ========== STEP 3: FORENSIC AUDIT (Facts) ==========
        # Moved forward as these are objective 'facts'
        sequence_ok = True
        completeness_ok = True
        steps_hash_ok = True
        chain_ok = True
        chain_breaks = []
        seq_comp_gaps = []
        step_count_ok = True  # AUD-CO-02: safe default for old artifacts
        steps: list[dict] = []

        try:
            import hashlib as _hashlib
            import json
            import zipfile

            with zipfile.ZipFile(epi_file, "r") as zf:
                members = zf.namelist()
                steps_member = next((m for m in members if m.endswith("steps.jsonl")), None)
                if steps_member:
                    raw_steps = zf.read(steps_member).decode("utf-8").splitlines()
                    steps = [json.loads(line) for line in raw_steps]

                    # 1. Index Sequence Audit (Monotonicity)
                    indices = [s.get("index", 0) for s in steps]
                    sequence_ok = (
                        all(indices[i] == indices[i - 1] + 1 for i in range(1, len(indices)))
                        if indices
                        else True
                    )

                    # 2. Timestamp Monotonicity Audit
                    # Check both OTel-style ns and standard ISO timestamps
                    times = []
                    for s in steps:
                        t_ns = s.get("content", {}).get("timestamp_ns")
                        if t_ns is not None:
                            times.append(t_ns)
                        else:
                            # Fallback to ISO timestamp string comparison (safe for monotonicity)
                            times.append(s.get("timestamp", ""))

                    is_time_monotonic = (
                        all(times[i] >= times[i - 1] for i in range(1, len(times)))
                        if times
                        else True
                    )
                    sequence_ok = sequence_ok and is_time_monotonic

                    # 3. Semantic Completeness Audit
                    # Only applies to guardrails-style recordings; passes when none present.
                    iteration_steps = [
                        s for s in steps if s.get("content", {}).get("subtype") == "guardrails"
                    ]
                    completeness_ok = len(iteration_steps) == 0 or all(
                        len(s.get("content", {}).get("validators", [])) > 0 for s in iteration_steps
                    )

                    # AUD-CO-01: Step Sequence Completeness Audit
                    seq_comp_ok, seq_comp_gaps = _audit_step_sequence_completeness(steps)
                    completeness_ok = completeness_ok and seq_comp_ok

                    # 4. Steps Hash Verification
                    execution_data = {}
                    try:
                        execution_data = EPIContainer.read_member_json(epi_file, "execution.json")
                    except Exception:
                        pass

                    claimed_hash = execution_data.get("steps_hash") or (manifest.trust or {}).get(
                        "steps_hash"
                    )
                    if claimed_hash:
                        actual_hash = _hashlib.sha256(zf.read(steps_member)).hexdigest()
                        steps_hash_ok = actual_hash == claimed_hash

                    # 5. prev_hash Chain Verification
                    chain_ok, chain_breaks = _verify_step_chain(steps)

                    # 6. AUD-CO-02: Step Count Attestation
                    # Compare actual step count against the signed manifest.total_steps.
                    # Only checked when the manifest has total_steps set (new artifacts).
                    # Old artifacts without total_steps are silently skipped.
                    claimed_step_count = manifest.total_steps
                    actual_step_count = len(steps)
                    if claimed_step_count is not None:
                        step_count_ok = actual_step_count == claimed_step_count

        except Exception as _e:
            if verbose:
                console.print(f"  [yellow]![/yellow] Forensic audit warning: {_e}")

        integrity_ok = integrity_ok and steps_hash_ok and chain_ok and step_count_ok

        if verbose:
            if chain_ok and not chain_breaks:
                console.print("  [green][OK][/green] prev_hash chain verified")
            elif chain_breaks:
                for cb in chain_breaks:
                    console.print(f"  [red][FAIL][/red] Chain broken: {cb}")
            else:
                console.print(
                    "  [yellow]![/yellow] Chain check skipped (old artifact or malformed)"
                )

            # Report sequence completeness
            if completeness_ok and not seq_comp_gaps:
                console.print("  [green][OK][/green] Step sequence completeness verified")
            elif seq_comp_gaps:
                for gap in seq_comp_gaps:
                    console.print(f"  [red][FAIL][/red] Sequence incomplete: {gap}")

            # Report step count check
            if manifest.total_steps is not None:
                if step_count_ok:
                    console.print(
                        f"  [green][OK][/green] Step count verified: "
                        f"{actual_step_count} of {claimed_step_count} steps present"
                    )
                else:
                    console.print(
                        f"  [red][FAIL][/red] Step count mismatch: "
                        f"manifest says {claimed_step_count}, found {actual_step_count}"
                    )

        # ========== STEP 4: AUTHENTICITY CHECKS (Trust) ==========
        if verbose:
            console.print("\n[bold]Step 4: Authenticity Checks (Trust)[/bold]")

        signature_valid, signer_name, sig_message = verify_embedded_manifest_signature(manifest)

        # ========== STEP 4.5: TRANSPARENCY CHECKS (SCITT) ==========
        transparency_ok: bool | None = None
        scitt_info = (manifest.governance or {}).get("scitt") if manifest.governance else None
        if scitt_info:
            if verbose:
                console.print("\n[bold]Step 4.5: Transparency Checks (SCITT)[/bold]")
            try:
                from epi_core.scitt import verify_scitt_statement

                stmt_path = scitt_info.get("statement_path", "artifacts/scitt/statement.cbor")
                rcpt_path = scitt_info.get("receipt_path", "artifacts/scitt/receipt.cbor")

                statement_bytes: bytes | None = None
                receipt_bytes: bytes | None = None
                with zipfile.ZipFile(epi_file, "r") as zf:
                    try:
                        statement_bytes = zf.read(stmt_path)
                    except KeyError:
                        pass
                    try:
                        receipt_bytes = zf.read(rcpt_path)
                    except KeyError:
                        pass

                if statement_bytes is None:
                    raise Exception(f"SCITT statement not found in archive: {stmt_path}")
                if receipt_bytes is None:
                    raise Exception(f"SCITT receipt not found in archive: {rcpt_path}")

                # Verify statement against manifest (structure + payload hash)
                verify_scitt_statement(statement_bytes, manifest, public_key_bytes=None)

                # Verify receipt signature against statement
                # Fetch service public key from the transparency service or cache
                service_pub_key = _fetch_scitt_service_key(scitt_info.get("service_url"))
                if service_pub_key:
                    try:
                        from epi_core.scitt import verify_scitt_receipt
                        verify_scitt_receipt(receipt_bytes, statement_bytes, service_pub_key)
                        transparency_ok = True
                        if verbose:
                            console.print("  [green][OK][/green] SCITT receipt cryptographically verified")
                    except Exception as exc:
                        transparency_ok = False
                        if verbose:
                            console.print(f"  [red][FAIL][/red] SCITT receipt signature invalid: {exc}")
                else:
                    # Fallback: structural check only if service key unavailable
                    receipt = cbor2.loads(receipt_bytes)
                    if isinstance(receipt, cbor2.CBORTag) and receipt.tag == 18:
                        transparency_ok = True
                        if verbose:
                            console.print("  [yellow][WARN][/yellow] SCITT receipt structurally valid (service key unavailable for crypto verification)")
                    else:
                        transparency_ok = False

                if verbose:
                    if transparency_ok:
                        console.print("  [green][OK][/green] SCITT receipt structurally valid")
                    else:
                        console.print("  [red][FAIL][/red] SCITT receipt invalid")
            except Exception as exc:
                transparency_ok = False
                if verbose:
                    console.print(f"  [yellow][WARN][/yellow] SCITT verification failed: {exc}")

        # ========== STEP 5: CREATE REPORT & APPLY POLICY ==========
        report = create_verification_report(
            integrity_ok=integrity_ok,
            signature_valid=signature_valid,
            signer_name=signer_name,
            mismatches=mismatches,
            manifest=manifest,
            trusted_registry=registry,
            sequence_ok=sequence_ok,
            completeness_ok=completeness_ok,
            chain_ok=chain_ok,
            transparency_ok=transparency_ok,
        )

        # Apply the selected governance policy
        active_policy = VerificationPolicy.STRICT if strict else policy
        apply_policy(report, active_policy)

        # ========== AIUC-1 DOMAIN MAPPING ==========
        if aiuc1:
            aiuc1_statuses = map_verification_to_aiuc1(report, manifest=manifest, steps=steps)
            report["aiuc1"] = aiuc1_summary(aiuc1_statuses)
            if verbose:
                console.print("\n[bold]AIUC-1 Trust Domain Mapping[/bold]")
                for domain_id, status in aiuc1_statuses.items():
                    color = "green" if status.status == "PASS" else ("yellow" if status.status == "PARTIAL" else "red")
                    console.print(f"  [{color}]{domain_id}. {status.label}: {status.status}[/{color}]")

        # ========== STEP 5: REVIEW TRUST CHECKS ==========
        if review:
            if verbose:
                console.print("\n[bold]Step 5: Review Trust Checks[/bold]")
            review_report = verify_review_trust(epi_file, strict=strict)
            report["review_trust"] = review_report
            if verbose:
                if review_report["status"] == "verified":
                    console.print(
                        "  [green][OK][/green] Review ledger, binding, and signatures verified"
                    )
                elif review_report["status"] == "warnings":
                    console.print("  [yellow][WARN][/yellow] Review trust warnings present")
                else:
                    console.print("  [red][FAIL][/red] Review trust verification failed")

        # ========== OUTPUT REPORT ==========
        if json_output:
            # JSON output (write directly to stdout to avoid Rich line-wrapping
            # inserted newlines that would corrupt machine-readable JSON).
            _emit_json_report(report)
        else:
            # Rich formatted output
            print_trust_report(report, epi_file, verbose)
            if review_report is not None:
                print_review_trust_report(review_report)

        # ========== WRITE REPORT FILE ==========
        if report_out is not None:
            dest = report_out
            _write_verification_report(report, epi_file, dest)
            if not json_output:
                console.print(f"[green][OK][/green] Verification report written: {dest}")

        if not json_output and integrity_ok and signature_valid is not False:
            _print_share_hint()
            try:
                from epi_cli.telemetry_hint import maybe_print_telemetry_hint

                maybe_print_telemetry_hint(console, "verify")
            except Exception:
                pass

        # ========== WEB / QR BRIDGE ==========
        if web and not json_output:
            portal_url = "https://epilabs.org/verify"
            console.print(f"\n[bold cyan]Opening {portal_url}...[/bold cyan]")
            console.print(f"[dim]Upload this file to verify in your browser:[/dim]")
            console.print(f"[green]{epi_file.resolve()}[/green]\n")
            try:
                import webbrowser
                webbrowser.open(portal_url)
            except Exception:
                console.print("[yellow]Could not open browser automatically.[/yellow]")
                console.print(f"[cyan]Please visit: {portal_url}[/cyan]")

        if qr and not json_output:
            portal_url = "https://epilabs.org/verify"
            console.print(f"\n[bold cyan]Scan this QR code to verify on your phone:[/bold cyan]")
            _print_qr_code(portal_url)
            console.print(f"[dim]Or visit: {portal_url}[/dim]\n")

        try:
            from epi_core.telemetry import track_event

            review_failed = bool(review_report and review_report.get("status") == "failed")
            track_event(
                "epi.verify.completed",
                {
                    "command": "verify",
                    "success": bool(
                        integrity_ok and signature_valid is not False and not review_failed
                    ),
                    "artifact_bytes": epi_file.stat().st_size,
                    "artifact_count": 1,
                },
            )
        except Exception:
            pass

        # Exit code based on policy decision
        if report["decision"]["status"] == "FAIL" or (
            review_report is not None and review_report.get("status") == "failed"
        ):
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except KeyboardInterrupt:
        if json_output:
            _emit_json_report(
                _build_failure_report(
                    "Verification interrupted",
                    error_type="interrupted",
                )
            )
        else:
            console.print("\n[yellow]Verification interrupted[/yellow]")
        raise typer.Exit(130)
    except Exception as e:
        if json_output:
            _emit_json_report(
                _build_failure_report(
                    f"Verification failed: {e}",
                    error_type="verification_failed",
                    signature_valid=signature_valid,
                    signer_name=signer_name,
                    has_signature=bool(getattr(manifest, "signature", None)),
                    mismatches=mismatches,
                )
            )
        elif verbose:
            console.print_exception()
        else:
            console.print(f"[red][FAIL] Verification failed:[/red] {e}")
        raise typer.Exit(1)


def print_trust_report(report: dict, epi_file: Path, verbose: bool = False):
    """Print the human-readable verification results with Facts/Identity/Decision separation.

    Supports both the new nested report format (facts/identity/decision) and
    the legacy flat format for backward compatibility.
    """
    # Normalise: detect new nested vs old flat format
    if "facts" in report:
        facts = report["facts"]
        identity = report.get("identity", {})
        decision = report.get("decision", {})
        integrity_ok = facts["integrity_ok"]
        signature_valid = facts["signature_valid"]
        sequence_ok = facts.get("sequence_ok", True)
        completeness_ok = facts.get("completeness_ok", True)
        chain_ok = facts.get("chain_ok", True)
        identity_status = identity.get("status", "UNKNOWN")
        identity_name = identity.get("name")
        identity_detail = identity.get("detail", "")
        public_key_id = identity.get("public_key_id")
        decision_status = decision.get("status", "FAIL")
        decision_policy = decision.get("policy", "none")
        decision_reason = decision.get("reason", "")
    else:
        # Legacy flat format
        integrity_ok = report.get("integrity_ok", False)
        signature_valid = report.get("signature_valid", None)
        sequence_ok = True
        completeness_ok = True
        chain_ok = True
        identity_status = "KNOWN" if report.get("identity_trusted") else "UNKNOWN"
        identity_name = report.get("signer")
        identity_detail = report.get("trust_message", "")
        public_key_id = None
        identity = {}
        facts = {}
        decision_status = "PASS" if (integrity_ok and signature_valid is not False) else "FAIL"
        decision_policy = "none"
        decision_reason = report.get("trust_message", "")

    # Header and Result
    status_symbol = (
        "[bold green]✔[/bold green]" if decision_status == "PASS" else "[bold red]✘[/bold red]"
    )
    panel_style = "green" if decision_status == "PASS" else "red"

    content_lines = []

    # Decision Layer
    content_lines.append(f"[bold]DECISION: {decision_status}[/bold]")
    content_lines.append(f"Policy: {decision_policy}")
    content_lines.append(f"Reason: {decision_reason}")
    content_lines.append("")

    # Fact Layer
    content_lines.append("[bold underline]FACTS (Objective Proofs)[/bold underline]")
    i_color = "green" if integrity_ok else "red"
    content_lines.append(
        f"  [{i_color}]- Integrity:    {'Verified' if integrity_ok else 'FAILED'}[/{i_color}]"
    )

    s_color = "green" if signature_valid else ("yellow" if signature_valid is None else "red")
    s_text = "Valid" if signature_valid else ("Unsigned" if signature_valid is None else "INVALID")
    content_lines.append(f"  [{s_color}]- Signature:    {s_text}[/{s_color}]")

    f_color = "green" if (sequence_ok and completeness_ok and chain_ok) else "red"
    f_text = "PASS" if (sequence_ok and completeness_ok and chain_ok) else "FAIL"
    content_lines.append(f"  [{f_color}]- Forensic:     {f_text}[/{f_color}]")
    if not chain_ok:
        content_lines.append("  [red]- Chain:        BROKEN (prev_hash mismatch)[/red]")

    # Transparency (SCITT)
    transparency_ok = facts.get("transparency_ok")
    if transparency_ok is not None:
        t_color = "green" if transparency_ok else "red"
        t_text = "VERIFIED" if transparency_ok else "FAILED"
        content_lines.append(f"  [{t_color}]- Transparency: {t_text} (SCITT)[/{t_color}]")

    content_lines.append("")

    # Identity Layer
    content_lines.append("[bold underline]IDENTITY (Trust Context)[/bold underline]")
    if identity_status == "KNOWN":
        id_color = "green"
    elif identity_status in ("REVOKED", "MISMATCH"):
        id_color = "red"
    else:
        id_color = "yellow"
    content_lines.append(f"  [{id_color}]- Status:       {identity_status}[/{id_color}]")
    content_lines.append(f"  - Name:         {identity_name or 'Unknown'}")
    if public_key_id:
        content_lines.append(f"  - Key ID:       {public_key_id}...")
    did_identity = identity.get("did") if isinstance(identity, dict) else None
    if did_identity:
        content_lines.append(f"  - DID:          {did_identity}")
    content_lines.append(f"  - Source:       {identity_detail}")

    # AIUC-1 Domain Layer
    aiuc1_data = report.get("aiuc1")
    if aiuc1_data:
        content_lines.append("")
        content_lines.append("[bold underline]AIUC-1 TRUST DOMAINS[/bold underline]")
        domains = aiuc1_data.get("domains", {})
        for domain_id in ["A", "B", "C", "D", "E", "F"]:
            domain = domains.get(domain_id)
            if not domain:
                continue
            d_status = domain.get("status", "UNKNOWN")
            d_label = domain.get("label", domain_id)
            if d_status == "PASS":
                d_color = "green"
            elif d_status == "PARTIAL":
                d_color = "yellow"
            else:
                d_color = "red"
            content_lines.append(f"  [{d_color}]{domain_id}. {d_label}: {d_status}[/{d_color}]")
        overall = aiuc1_data.get("overall", "UNKNOWN")
        o_color = "green" if overall == "PASS" else ("yellow" if overall == "PARTIAL" else "red")
        content_lines.append(f"  [{o_color}]Overall: {overall}[/{o_color}]")

    if "warnings" in report and report["warnings"]:
        content_lines.append("")
        content_lines.append("[bold yellow]Warnings:[/bold yellow]")
        for w in report["warnings"]:
            content_lines.append(f"  [yellow]![/yellow] {w}")

    content = "\n".join(content_lines)

    # Print panel
    panel = Panel(
        content,
        title=f"{status_symbol} EPI Verification Report",
        border_style=panel_style,
        expand=False,
    )
    console.print("\n")
    console.print(panel)
    console.print("")


def print_review_trust_report(review_report: dict):
    """Print the optional review trust verification result."""
    status = review_report.get("status")
    if status == "verified":
        style = "green"
        title = "[OK] Review Trust"
    elif status == "warnings":
        style = "yellow"
        title = "[WARN] Review Trust"
    else:
        style = "red"
        title = "[FAIL] Review Trust"

    lines = [
        f"[bold]Status:[/bold] {status}",
        f"[bold]Reviews:[/bold] {review_report.get('review_count', 0)}",
        f"[bold]Latest review:[/bold] {review_report.get('latest_review_id') or 'none'}",
        f"[bold]Binding:[/bold] {review_report.get('binding_valid')}",
        f"[bold]Signature:[/bold] {review_report.get('signature_valid')}",
        f"[bold]Chain:[/bold] {review_report.get('chain_valid')}",
    ]

    failures = list(review_report.get("failures") or [])
    warnings = list(review_report.get("warnings") or [])
    if failures:
        lines.append("")
        lines.append("[bold red]Failures:[/bold red]")
        lines.extend(f"  [red]-[/red] {item}" for item in failures[:5])
    if warnings:
        lines.append("")
        lines.append("[bold yellow]Warnings:[/bold yellow]")
        lines.extend(f"  [yellow]-[/yellow] {item}" for item in warnings[:5])

    console.print(Panel("\n".join(lines), title=title, border_style=style, expand=False))
    console.print("")
