"""
EPI CLI Verify - Verify .epi file integrity and authenticity.

Performs comprehensive verification including:
- Structural validation (ZIP format, mimetype, manifest schema)
- Integrity checks (file hashes match manifest)
- Authenticity checks (Ed25519 signature verification)
"""

import os
import json
import sys
import warnings
from datetime import UTC
from pathlib import Path
from typing import Annotated

import cbor2
import typer
from rich.console import Console
from rich.panel import Panel

from epi_cli.view import _resolve_epi_file
from epi_core._version import JCS_INTRODUCED_VERSION, get_version
from epi_core.aiuc1_mapping import aiuc1_summary, map_verification_to_aiuc1
from epi_core.container import EPIContainer
from epi_core.review import verify_review_trust
from epi_core.trust import (
    TrustRegistry,
    VerificationPolicy,
    apply_policy,
    create_verification_report,
    sealed_payload_gate,
    verify_embedded_manifest_signature,
)

console = Console()


_TIMESTAMP_TAMPER_STATUSES = ("imprint_mismatch", "bad_signature", "cert_invalid")


def _tsa_trust_roots(tsa_root_paths: list[Path] | None = None) -> list:
    """Build the TSA trust list once: pinned + --tsa-root + env roots.

    Shared by the seal path (_build_timestamps_block) and both checkpoint
    verifiers so a custom TSA trusted via --tsa-root is trusted everywhere.
    Never raises; every load failure yields fewer roots, not a crash.
    """
    from epi_core.tsa_verify import (
        load_pem_roots,
        load_pinned_tsa_roots,
        load_user_tsa_roots,
    )

    try:
        pinned = load_pinned_tsa_roots()
    except Exception:
        pinned = []
    try:
        extra_pems = load_pem_roots([str(p) for p in (tsa_root_paths or [])])
    except Exception:
        extra_pems = []
    try:
        env_pems = load_user_tsa_roots()
    except Exception:
        env_pems = []
    trust_roots: list = list(pinned)
    for cert in list(extra_pems) + list(env_pems):
        try:
            trust_roots.append((cert.subject.rfc4514_string(), cert))
        except Exception:
            continue
    return trust_roots


def _build_timestamps_block(
    epi_file: Path,
    manifest,
    cp_records: list[dict],
    tsa_root_paths: list[Path] | None = None,
) -> dict:
    """Validate seal-time and checkpoint RFC 3161 tokens (offline).

    Returns report["timestamps"]: {seal, checkpoints, earliest_verified,
    statement, clock_warning}. Never raises; every failure mode becomes data.
    """
    from epi_core.notarize import (
        IMPRINT_SCHEME,
        _parse_tsr_gen_time,
        compute_seal_imprint,
        normalize_imprint_time,
    )
    from epi_core.tsa_verify import validate_tsr

    trust_roots = _tsa_trust_roots(tsa_root_paths)

    block: dict = {
        "seal": [],
        "checkpoints": [],
        "earliest_verified": None,
        "key_binding": "none",
        "statement": "no timestamps collected",
        "clock_warning": None,
    }

    try:
        notar = EPIContainer.read_member_json(
            epi_file, "artifacts/notarization/notarization.json"
        )
    except Exception:
        notar = None
    if isinstance(notar, dict):
        scheme = notar.get("imprint_scheme")
        entries = list(notar.get("tsa_tokens") or [])
        if not entries and notar.get("tsa_token_available"):
            entries = [
                {
                    "url": ((notar.get("notarized_at") or {}).get("url") or ""),
                    "member": "artifacts/notarization/tsa_reply.tsr",
                }
            ]
        new_scheme = scheme == IMPRINT_SCHEME and notar.get("imprinted_digest")
        from epi_core.keys import key_fingerprint

        imprinted_key = notar.get("imprinted_public_key")
        manifest_key = getattr(manifest, "public_key", None)
        imprinted_key_fp = (
            key_fingerprint(str(imprinted_key), grouped=False) if imprinted_key else None
        )
        # "Key-bound" means the timestamp was taken over an imprint that named
        # a sealing key. Old seals (imprinted_public_key null) are contents-only.
        key_bound = bool(imprinted_key)
        expected: bytes | None = None
        recomputed: str | None = None
        if new_scheme:
            try:
                recomputed = compute_seal_imprint(
                    str(manifest.workflow_id),
                    normalize_imprint_time(manifest.created_at),
                    notar.get("imprinted_public_key"),
                    dict(manifest.file_manifest or {}),
                )
                expected = bytes.fromhex(str(notar["imprinted_digest"]))
            except Exception:
                expected = None
        for entry in entries:
            url = (entry.get("url") if isinstance(entry, dict) else "") or ""
            member = (
                (entry.get("member") if isinstance(entry, dict) else "")
                or "artifacts/notarization/tsa_reply.tsr"
            )
            if not new_scheme:
                try:
                    present = EPIContainer.read_member_bytes(epi_file, member)
                except Exception:
                    present = None
                block["seal"].append(
                    {
                        "url": url,
                        "status": "legacy" if present else "absent",
                        "gen_time": _parse_tsr_gen_time(present),
                        "tsa_subject": None,
                        "tsa_root": None,
                        "imprint_scheme": None,
                        "key_bound": False,
                        "imprinted_key_fingerprint": None,
                        "detail": (
                            "legacy token: imprint not recomputable "
                            "(sealed before 4.6); presence only"
                        ),
                    }
                )
                continue
            if expected is None:
                block["seal"].append(
                    {
                        "url": url,
                        "status": "malformed",
                        "gen_time": None,
                        "tsa_subject": None,
                        "tsa_root": None,
                        "imprint_scheme": IMPRINT_SCHEME,
                        "key_bound": key_bound,
                        "imprinted_key_fingerprint": imprinted_key_fp,
                        "detail": "seal imprint cannot be recomputed from this manifest",
                    }
                )
                continue
            try:
                token = EPIContainer.read_member_bytes(epi_file, member)
            except Exception:
                token = None
            if not token:
                block["seal"].append(
                    {
                        "url": url,
                        "status": "absent",
                        "gen_time": None,
                        "tsa_subject": None,
                        "tsa_root": None,
                        "imprint_scheme": IMPRINT_SCHEME,
                        "key_bound": key_bound,
                        "imprinted_key_fingerprint": imprinted_key_fp,
                        "detail": "notarization record lists a token that is not in the file",
                    }
                )
                continue
            try:
                validation = validate_tsr(token, expected, trust_roots=trust_roots)
            except Exception as exc:
                block["seal"].append(
                    {
                        "url": url,
                        "status": "malformed",
                        "gen_time": None,
                        "tsa_subject": None,
                        "tsa_root": None,
                        "imprint_scheme": IMPRINT_SCHEME,
                        "key_bound": key_bound,
                        "imprinted_key_fingerprint": imprinted_key_fp,
                        "detail": f"timestamp validation crashed ({exc})",
                    }
                )
                continue
            status = validation.status
            detail = validation.detail
            entry_key_bound = key_bound
            # The imprint was recomputed with the key RECORDED at seal time,
            # so a swapped signing key would still reproduce it. Bind the
            # timestamp to the key this file actually carries.
            key_changed = False
            if imprinted_key:
                if not manifest_key:
                    key_changed = True
                    detail = (
                        "the timestamp binds signing key "
                        f"{imprinted_key_fp} but this file carries no signing key"
                    )
                elif (
                    str(imprinted_key).strip().lower()
                    != str(manifest_key).strip().lower()
                ):
                    key_changed = True
                    detail = (
                        "signing key changed after the timestamp was taken: "
                        f"the timestamp binds key {imprinted_key_fp}, the file "
                        "is signed by key "
                        f"{key_fingerprint(str(manifest_key), grouped=False)}"
                    )
            if key_changed and status not in ("absent", "malformed"):
                status = "imprint_mismatch"
                entry_key_bound = False
            elif recomputed != notar.get("imprinted_digest") and status == "valid":
                # Payload drifted after stamping and was re-signed with the
                # key: the old token no longer covers these bytes.
                status = "imprint_mismatch"
                detail = (
                    "sealed bytes no longer match the timestamped imprint "
                    "(modified and re-signed after sealing)"
                )
            block["seal"].append(
                {
                    "url": url,
                    "status": status,
                    "gen_time": validation.gen_time,
                    "tsa_subject": validation.tsa_subject,
                    "tsa_root": validation.tsa_root,
                    "imprint_scheme": IMPRINT_SCHEME,
                    "key_bound": entry_key_bound,
                    "imprinted_key_fingerprint": imprinted_key_fp,
                    "detail": detail,
                }
            )

    for rec in cp_records or []:
        try:
            idx = int((rec or {}).get("index", 0))
        except Exception:
            idx = 0
        try:
            count = int((rec or {}).get("event_count", 0))
        except Exception:
            count = 0
        if not (rec or {}).get("tsa_available"):
            block["checkpoints"].append(
                {"index": idx, "event_count": count, "status": "absent", "gen_time": None}
            )
            continue
        validation = (rec or {}).get("tsa_validation") or {}
        block["checkpoints"].append(
            {
                "index": idx,
                "event_count": count,
                "status": validation.get("status") or "absent",
                "gen_time": validation.get("gen_time"),
            }
        )

    valid_seal = [e for e in block["seal"] if e["status"] == "valid"]
    valid_cp = sorted(
        (c for c in block["checkpoints"] if c["status"] == "valid"),
        key=lambda c: (c["index"], c["event_count"]),
    )
    keyed_seal = [e for e in valid_seal if e.get("key_bound")]
    block["key_binding"] = (
        "key-bound" if keyed_seal else ("contents-only" if valid_seal else "none")
    )
    earliest: str | None = None
    for entry in valid_seal + valid_cp:
        gen = entry.get("gen_time")
        if gen and (earliest is None or gen < earliest):
            earliest = gen
    block["earliest_verified"] = earliest

    clauses: list[str] = []
    if valid_cp:
        last = valid_cp[-1]
        if last.get("gen_time"):
            clauses.append(
                f"steps 1-{last['event_count']} existed no later than "
                f"{last['gen_time']} (checkpoint {last['index']})"
            )
    if valid_seal:
        seal_times = [e["gen_time"] for e in valid_seal if e.get("gen_time")]
        if seal_times:
            earliest_seal = min(seal_times)
            if keyed_seal:
                clauses.append(
                    "sealed by key "
                    f"{keyed_seal[0].get('imprinted_key_fingerprint')} "
                    f"no later than {earliest_seal}"
                )
            else:
                clauses.append(
                    f"the sealed contents existed no later than {earliest_seal} "
                    "(contents-only timestamp; signing key not bound)"
                )
    if any(e["status"] == "legacy" for e in block["seal"]):
        clauses.append("legacy seal token present (imprint not recomputable); presence only")
    if any(e["status"] in _TIMESTAMP_TAMPER_STATUSES for e in block["seal"]):
        clauses.append("a seal-time token is INVALID (see detail)")
    block["statement"] = (
        "; ".join(clauses) + "." if clauses else "no verified timestamps."
    )

    # Sanity check: a creation time later than the TSA's attested time is
    # impossible for honest data — the sealer's clock and the TSA disagree.
    try:
        if earliest and manifest.created_at is not None:
            from datetime import datetime, timezone

            created = manifest.created_at
            if isinstance(created, str):
                created = datetime.fromisoformat(created)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            earliest_dt = datetime.fromisoformat(str(earliest).replace("Z", "+00:00"))
            if (created - earliest_dt).total_seconds() > 600:
                block["clock_warning"] = (
                    f"sealer clock ({created.strftime('%Y-%m-%dT%H:%M:%SZ')}) is more "
                    f"than 10 minutes after the earliest verified timestamp "
                    f"({earliest}); the sealer's clock and the TSA disagree"
                )
    except Exception:
        pass
    return block


# Neutral colours: missing evidence is information for the reader, not a failed check.
_AIUC1_COLORS = {"FOUND": "green", "PARTIAL": "yellow", "NOT_FOUND": "dim"}
_AIUC1_WORDS = {
    "FOUND": "evidence found",
    "PARTIAL": "some evidence found",
    "NOT_FOUND": "no evidence found",
}


def _fetch_scitt_service_key(service_url: str | None, *, offline: bool = False) -> bytes | None:
    """
    Fetch and cache the SCITT transparency service's Ed25519 public key.

    Args:
        service_url: URL of the SCITT service (e.g., https://scitt.epilabs.org)
        offline: when True, never fetch — cache/local only.

    Returns:
        32-byte raw Ed25519 public key, or None if unavailable.
    """
    if not service_url:
        return None

    # Local/offline SCITT service: read the service public key from disk.
    if service_url.lower() == "local":
        from epi_core.local_scitt import _service_public_key_path, service_public_key

        # Only the machine that issued a local receipt has its key. Never
        # create one here as a side effect of verifying.
        if not _service_public_key_path().exists():
            return None
        return service_public_key()

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

    # Offline: cache/local only, never fetch.
    if offline:
        return None

    # Fetch from service
    try:
        from epi_core.scitt import SCITTServiceClient
        client = SCITTServiceClient(service_url)
        key_bytes = client.get_public_key()
        cache_file.write_text(key_bytes.hex())
        tmp = cache_file.with_suffix(".tmp")
        tmp.write_text(key_bytes.hex())
        tmp.replace(cache_file)
        return key_bytes
    except Exception:
        return None


def _is_cbor_spec(sv: str | None) -> bool:
    from epi_core.serialize import canonical_format_for

    return canonical_format_for(sv) == "cbor"


def _is_legacy_spec(sv: str | None) -> bool:
    from epi_core.serialize import canonical_format_for

    return canonical_format_for(sv) == "legacy"


def _warn_legacy_canonicalizer_dispatch(spec_version: str | None) -> None:
    """Emit at dispatch, not inside the chain loop — short artifacts still announce."""
    if not spec_version or _is_cbor_spec(spec_version) or not _is_legacy_spec(spec_version):
        return
    warnings.warn(
        f"Verified via legacy canonicalization (spec_version={spec_version} <{JCS_INTRODUCED_VERSION})",
        UserWarning,
        stacklevel=3,
    )


def _verify_step_chain(steps: list[dict], spec_version: str | None = None) -> tuple[bool, list[str]]:
    """
    Verify the prev_hash cryptographic chain in a list of steps.

    Dispatch by manifest spec_version via serialize.canonical_format_for —
    the same function the sign path uses. No trial, one path per artifact.
    Emits a visible warning when legacy path is used, even if the chain loop does not run.

    Genesis contract (strict): index 0 must carry None or "CHAIN_START" —
    there is no previous step to link to. A genesis marker at index > 0
    means the chain was restarted (possible truncation) and is reported as
    a break. Steps without any hash are skipped ONLY for pre-chain
    artifacts where no step carries a verifiable link at all.
    """
    from epi_core.serialize import canonical_format_for

    fmt = canonical_format_for(spec_version)
    _warn_legacy_canonicalizer_dispatch(spec_version)

    if not steps:
        return True, []

    if len(steps) == 1:
        # A single step has no link to check. Read the raw dict (no model
        # parse: minimal producers like the browser pack script omit fields
        # such as kind) and enforce only the genesis contract.
        first = steps[0] if isinstance(steps[0], dict) else {}
        if first.get("prev_hash") not in (None, "CHAIN_START"):
            return False, ["step 0: invalid genesis marker (expected CHAIN_START)"]
        return True, []

    try:
        from epi_core.schemas import StepModel
        from epi_core.serialize import hash_normalized_dict, model_dict_for_hash

        chain_breaks: list[str] = []
        step_models = [StepModel(**s) for s in steps]

        if step_models[0].prev_hash not in (None, "CHAIN_START"):
            chain_breaks.append("step 0: invalid genesis marker (expected CHAIN_START)")

        markers_present = any(m.prev_hash == "CHAIN_START" for m in step_models)
        hashes_present = any(m.prev_hash not in (None, "CHAIN_START") for m in step_models)
        if not markers_present and not hashes_present:
            # Pre-chain artifact: no step carries any link at all. Nothing
            # to check — pass loudly rather than silently.
            warnings.warn(
                "steps carry no prev_hash links (pre-chain artifact); chain check passes vacuously",
                UserWarning,
                stacklevel=3,
            )
            return len(chain_breaks) == 0, chain_breaks

        for i in range(1, len(step_models)):
            claimed_prev = step_models[i].prev_hash
            if claimed_prev in (None, "CHAIN_START"):
                chain_breaks.append(
                    f"step {i}: chain restarted with genesis marker (possible truncation)"
                )
                continue
            expected = hash_normalized_dict(model_dict_for_hash(step_models[i - 1]), fmt)
            if claimed_prev != expected:
                chain_breaks.append(f"step {i}: prev_hash mismatch")
        return len(chain_breaks) == 0, chain_breaks
    except (ValueError, TypeError) as exc:
        # Malformed steps must fail loudly — a silent True here would let a
        # corrupted steps.jsonl verify clean. (Old CBOR-hash mismatches surface
        # as normal "prev_hash mismatch" breaks above, not as exceptions.)
        return False, [f"chain verification error: malformed step ({exc})"]
    except Exception as exc:  # noqa: BLE001
        # Unexpected error: do not silently pass — report it as a chain break
        # so operators are aware something went wrong during chain validation.
        return False, [f"chain verification error: {exc}"]


def _chain_links_present(steps: list[dict]) -> bool:
    """True when the steps carry at least one prev_hash link.

    A file with no links at all is a *pre-chain* artifact: the chain check
    passes vacuously, so nothing in it proves the recorded order. Fewer than
    two steps cannot be reordered, so there is nothing to prove either way.
    """
    if len(steps) < 2:
        return True
    for s in steps:
        if not isinstance(s, dict):
            continue
        prev = s.get("prev_hash")
        if prev not in (None, "CHAIN_START"):
            return True
    return False


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
    pending_pre_commits: list[tuple[int, str | None]] = []
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

        elif kind == "llm.pre_commit":
            pending_pre_commits.append((idx, span_id))
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
            # Clear the oldest pending pre-commit when any LLM response arrives
            if pending_pre_commits:
                pending_pre_commits.pop(0)

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

    # Step references are 1-based throughout every surface (viewer §3/§4/§6,
    # analyzer step_number): a gap at list index i is reported as step i+1.
    for idx, call_id in pending_tool_calls:
        gaps.append(f"tool.call at step {idx + 1} is missing a corresponding tool.response")
    for idx, call_id in pending_pre_commits:
        gaps.append(f"llm.pre_commit at step {idx + 1} was committed but never executed — response never arrived (crash, timeout, or cancellation)")
    for idx, span_id in pending_llm_requests:
        gaps.append(f"llm.request at step {idx + 1} is missing a corresponding response or error")
    for idx, action in pending_approvals:
        gaps.append(f"agent.approval.request for '{action}' at step {idx + 1} is missing a response")

    return len(gaps) == 0, gaps


def _print_share_hint() -> None:
    """One neutral pointer after a verification (the reader may be a third party).

    No vendor-side steps here (sharing, team workspace): whoever runs
    `epi verify` is often the customer or an auditor, not the sender.
    """
    console.print("")
    console.print(
        "[dim]Anyone can re-check this file in a browser, no install: "
        "[cyan]https://epilabs.org/verify[/cyan][/dim]"
    )


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


def _clean_witness_pubkey(value) -> str | None:
    """Normalise a witness pubkey hex string; None when absent."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in ("null", "none"):
        return None
    if text.lower().startswith("0x"):
        text = text[2:]
    text = text.strip()
    return text or None


def _canonical_witness_receipt_bytes(receipt: dict) -> bytes:
    """Canonical bytes the witness signs (M6 evidence pack contract).

    canonical = JSON.stringify({artifact_sha256, inbox_id, line_sha256,
    received_at, seq}) with EXACTLY this key order, compact separators,
    UTF-8 bytes. Raises KeyError when a field is missing.
    """
    ordered = {
        "artifact_sha256": receipt["artifact_sha256"],
        "inbox_id": receipt["inbox_id"],
        "line_sha256": receipt["line_sha256"],
        "received_at": receipt["received_at"],
        "seq": receipt["seq"],
    }
    return json.dumps(ordered, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _verify_witness_receipt(
    payload_raw, receipt, pubkey, file_sha256: str
) -> tuple[bool, str]:
    """Verify one signed witness receipt. Returns (ok, failure_reason)."""
    import hashlib as _hashlib

    from cryptography.exceptions import InvalidSignature

    if not isinstance(payload_raw, str):
        return False, "receipt check failed: payload_raw is not a string"
    if not isinstance(receipt, dict):
        return False, "receipt check failed: receipt is not an object"
    for _field in ("artifact_sha256", "inbox_id", "line_sha256", "received_at", "seq", "signature"):
        if receipt.get(_field) is None and _field not in receipt:
            return False, f"receipt check failed: receipt missing field '{_field}'"
        if _field != "seq" and receipt.get(_field) is None:
            return False, f"receipt check failed: receipt missing field '{_field}'"
    if receipt.get("seq") is None:
        return False, "receipt check failed: receipt missing field 'seq'"
    try:
        want_line = _hashlib.sha256(payload_raw.encode("utf-8")).hexdigest()
    except Exception as exc:
        return False, f"receipt check failed: cannot hash payload_raw ({exc})"
    if str(receipt.get("line_sha256") or "") != want_line:
        return False, (
            "receipt check failed: line_sha256 mismatch "
            f"(sha256(payload_raw)={want_line} != receipt.line_sha256={receipt.get('line_sha256')})"
        )
    try:
        canonical = _canonical_witness_receipt_bytes(receipt)
    except KeyError as exc:
        return False, f"receipt check failed: receipt missing field {exc}"
    except Exception as exc:
        return False, f"receipt check failed: cannot build canonical receipt ({exc})"
    try:
        sig_hex = str(receipt.get("signature") or "").strip().removeprefix("0x")
        pubkey.verify(bytes.fromhex(sig_hex), canonical)
    except InvalidSignature:
        return False, "receipt check failed: signature invalid (Ed25519 verification failed)"
    except Exception as exc:
        return False, f"receipt check failed: signature malformed ({exc})"
    if str(receipt.get("artifact_sha256") or "") != str(file_sha256 or ""):
        return False, (
            "receipt check failed: artifact_sha256 mismatch "
            f"(receipt.artifact_sha256={receipt.get('artifact_sha256')} != "
            f"sha256(file bytes)={file_sha256})"
        )
    return True, ""


def _check_witness_log(epi_file: Path, manifest, witness_log, witness_pubkey: str | None = None) -> dict:
    """Compare the sealed file against the customer's witness log.

    Returns {"status", "received_at", "matches", "detail"} with status one of
    NOT CHECKED (no log supplied), WITNESSED, NOT IN WITNESS LOG, MISMATCH.
    Never raises.
    """
    result: dict = {
        "status": "NOT CHECKED",
        "received_at": None,
        "matches": 0,
        "detail": "no witness log supplied (--witness-log)",
    }
    if not witness_log:
        return result
    try:
        raw_text = Path(witness_log).read_text(encoding="utf-8")
    except Exception as exc:
        # The verifier asked for this check; a typo in the path must not
        # silently drop it.
        result["status"] = "UNREADABLE"
        result["detail"] = f"witness log {witness_log} could not be read ({exc})"
        return result
    lines = raw_text.splitlines()
    # --- Detect the NEW signed doc (M6 witness.json): a single JSON object
    # with a "lines" array. Anything else falls through to legacy JSONL.
    doc_pubkey_raw = None
    doc_lines_raw: list | None = None
    try:
        _doc = json.loads(raw_text) if raw_text.strip() else None
    except Exception:
        _doc = None
    if isinstance(_doc, dict) and isinstance(_doc.get("lines"), list):
        doc_pubkey_raw = _doc.get("witness_pubkey")
        doc_lines_raw = _doc.get("lines")
    entries: list[dict] = []
    signed_items: list[dict] = []  # {payload_raw, receipt, line_received_at, top_received_at, inner}
    legacy_entries: list[dict] = []

    def _parse_inner(payload_raw):
        try:
            if not isinstance(payload_raw, str):
                return None
            inner = json.loads(payload_raw)
            return inner if isinstance(inner, dict) else None
        except Exception:
            return None

    if doc_lines_raw is not None:
        for item in doc_lines_raw:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("payload_raw"), str) and isinstance(item.get("receipt"), dict):
                signed_items.append(
                    {
                        "payload_raw": item.get("payload_raw"),
                        "receipt": item.get("receipt"),
                        "line_received_at": item.get("received_at"),
                        "top_received_at": None,
                        "inner": _parse_inner(item.get("payload_raw")),
                        "raw": item,
                    }
                )
            elif item.get("workflow_id"):
                legacy_entries.append(item)
            else:
                # Unknown shape inside a signed doc: keep it visible for the
                # UNREADABLE count but never matchable.
                entries.append(item)
        _reports_count = len(signed_items) + len(legacy_entries)
        if not signed_items and not legacy_entries:
            result["status"] = "UNREADABLE"
            result["detail"] = (
                f"{witness_log} contains no witness reports ({len(doc_lines_raw)} lines, "
                "0 JSON objects) — is it the --out file of `epi witness serve`?"
            )
            return result
    else:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        for entry in entries:
            if isinstance(entry.get("payload_raw"), str) and isinstance(entry.get("receipt"), dict):
                signed_items.append(
                    {
                        "payload_raw": entry.get("payload_raw"),
                        "receipt": entry.get("receipt"),
                        "line_received_at": entry.get("received_at"),
                        "top_received_at": entry.get("received_at"),
                        "inner": _parse_inner(entry.get("payload_raw")),
                        "raw": entry,
                    }
                )
            else:
                legacy_entries.append(entry)
        _reports = [e for e in legacy_entries if e.get("workflow_id") and e.get("manifest_hash")]
        if not _reports and not signed_items:
            # Wrong file, empty file or not a witness log: the check could not be
            # done. Never let that read as "the vendor never reported this".
            result["status"] = "UNREADABLE"
            result["detail"] = (
                f"{witness_log} contains no witness reports ({len(lines)} lines, "
                f"{len(entries)} JSON objects) — is it the --out file of `epi witness serve`?"
            )
            return result
        _reports_count = len(_reports) + len(signed_items)
    # --- Trusted keys: --witness-pubkey flag > EPI_WITNESS_PUBKEY env >
    # package-pinned keys (epi_core/witness_keys.py). The witness_pubkey
    # shipped INSIDE the file (witness.json) is NEVER trust: a forger
    # self-stamps any run with their own key and swaps it in — a passport
    # printing its own stamp sample. It is kept only to name the key in the
    # NOT CONFIRMED message below.
    from epi_core.witness_keys import pinned_witness_pubkeys

    # Explicit auditor keys (flag/env) vs package pins. Package pins count
    # for RECEIPTS but never turn a plain unsigned log into auditor mode:
    # the customer's own received.jsonl must keep verifying after pinning.
    _explicit_hexes: list[str] = []
    for _candidate in (
        [_clean_witness_pubkey(witness_pubkey)]
        + [_clean_witness_pubkey(os.environ.get("EPI_WITNESS_PUBKEY"))]
    ):
        if _candidate and _candidate not in _explicit_hexes:
            _explicit_hexes.append(_candidate)
    _trusted_hexes: list[str] = list(_explicit_hexes)
    for _candidate in pinned_witness_pubkeys():
        if _candidate and _candidate not in _trusted_hexes:
            _trusted_hexes.append(_candidate)
    doc_key = _clean_witness_pubkey(doc_pubkey_raw)
    workflow_id = str(getattr(manifest, "workflow_id", ""))
    same_legacy = [e for e in legacy_entries if str(e.get("workflow_id") or "") == workflow_id]
    same_signed = [
        s
        for s in signed_items
        if isinstance(s.get("inner"), dict)
        and str((s["inner"] or {}).get("workflow_id") or "") == workflow_id
    ]
    # Signed lines whose payload_raw is not valid JSON (or has no
    # workflow_id) can never match, but they are still evidence that the
    # log was consulted: keep them out of `same` exactly like legacy
    # entries with a foreign workflow id.
    same = same_legacy + same_signed  # type: ignore[operator]
    result["matches"] = len(same)
    if not same:
        result["status"] = "NOT IN WITNESS LOG"
        result["detail"] = (
            f"workflow {workflow_id} not found in {_reports_count} witness reports; "
            "a missing entry for a case the customer knows happened is itself evidence"
        )
        return result
    try:
        from epi_core.serialize import get_canonical_hash
        import hashlib as _hashlib

        manifest_hash = get_canonical_hash(manifest, exclude_fields=["signature"])
        file_sha256 = _hashlib.sha256(Path(epi_file).read_bytes()).hexdigest()
    except Exception as exc:
        result["detail"] = f"could not hash sealed file ({exc})"
        return result
    try:
        from epi_core.webhook import witness_content_digest

        content_digest = witness_content_digest(manifest)
    except Exception:
        content_digest = None

    def _signed_received_at(item: dict) -> str | None:
        receipt = item.get("receipt") or {}
        return (
            (receipt.get("received_at") if isinstance(receipt, dict) else None)
            or item.get("line_received_at")
            or item.get("top_received_at")
            or ((item.get("inner") or {}).get("received_at") if isinstance(item.get("inner"), dict) else None)
        )

    if signed_items and not _trusted_hexes:
        # FAIL CLOSED: this file carries witness receipts, so WITNESSED
        # is only meaningful against a key the reviewer pinned OUT OF
        # BAND. No trusted key was provided (flag, env, or package pin),
        # so the stamps were not checked at all. A key arriving inside
        # the file proves nothing — self-signed packs verify against
        # their own forgery. Never WITNESSED here, never silent.
        try:
            _times = []
            for item in same_signed:
                _t = _signed_received_at(item)
                if _t:
                    _times.append(str(_t))
            if _times:
                result["received_at"] = max(_times)
        except Exception:
            pass
        result["receipt_verified"] = 0
        result["receipt_failures"] = len(same_signed)
        _names_key = f" The file names key {doc_key[:16]}…;" if doc_key else ""
        result["status"] = "NOT CONFIRMED"
        result["detail"] = (
            "WITNESS STAMP NOT CONFIRMED: this file carries witness receipts but no "
            "trusted EPI witness key was provided, so no stamp was checked."
            f"{_names_key} a key that arrives inside the file proves nothing — a forger "
            "swaps in their own. Pin the EPI witness key out of band (fetch it from "
            "https://cloud.epilabs.org/.well-known/epi-witness-key.json and confirm the "
            "fingerprint through an independent channel, such as a prior signed "
            "checkpoint or your contract) and re-run with "
            "--witness-pubkey <key> (or EPI_WITNESS_PUBKEY)."
        )
        return result
    if not signed_items and not _explicit_hexes:
        # Pure unsigned log, no auditor key: the operator's OWN log (e.g.
        # their `epi witness serve --out` file). Package pins deliberately do
        # NOT apply here — otherwise pinning would break every customer's
        # self-hosted flow. The verdict says whose log it is: a file handed
        # over by someone else proves nothing without signed receipts.
        candidates: list[dict] = list(same_legacy)
        for entry in candidates:
            if (
                entry.get("manifest_hash") == manifest_hash
                and entry.get("file_sha256") == file_sha256
            ):
                _at = entry.get("_witness_received_at", entry.get("received_at"))
                result["status"] = "WITNESSED"
                result["mode"] = "own-log-unsigned"
                result["received_at"] = _at
                result["detail"] = (
                    "WITNESSED — YOUR OWN LOG (unsigned): customer record matches "
                    f"(received {_at or 'unknown time'}). Trusted only because you kept "
                    "this log yourself; a file received from someone else proves "
                    "nothing — demand signed receipts and pin the EPI witness key."
                )
                return result
        for entry in candidates:
            # Re-packaged after the witness (e.g. `epi-register` added a
            # transparency receipt and re-signed): the sealed evidence is what the
            # customer was told about, the outer file is not byte-identical.
            if content_digest and entry.get("content_digest") == content_digest:
                _at = entry.get("_witness_received_at", entry.get("received_at"))
                result["status"] = "WITNESSED"
                result["mode"] = "own-log-unsigned"
                result["received_at"] = _at
                result["repackaged"] = True
                result["detail"] = (
                    "WITNESSED — YOUR OWN LOG (unsigned): sealed contents match the "
                    "customer record "
                    f"(received {_at or 'unknown time'}); the file was "
                    "re-packaged afterwards (e.g. viewer refreshed or transparency receipt "
                    "added, and re-signed). Trusted only because you kept this log "
                    "yourself."
                )
                return result
        result["status"] = "MISMATCH"
        _latest = max(
            (str(e.get("_witness_received_at", e.get("received_at")) or "") for e in candidates),
            default="",
        ) or "unknown time"
        result["received_at"] = _latest
        result["detail"] = (
            f"a different version of this case (same workflow id) was reported to you "
            f"({len(same)} report(s), latest {_latest}); this copy was never reported"
        )
        return result
    # --- Trusted key(s) configured: only verified receipts count. Every
    # workflow-matched line without a passing receipt (unsigned legacy
    # entries included) is skipped; if none verify the answer is MISMATCH
    # naming the receipt failure, never WITNESSED.
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        pubkeys = []
        for _hx in _trusted_hexes:
            try:
                pubkeys.append(Ed25519PublicKey.from_public_bytes(bytes.fromhex(_hx)))
            except Exception:
                continue
        pubkey_error: str | None = None
        if not pubkeys:
            pubkey_error = "invalid witness public key (no configured key parses)"
    except Exception as exc:
        pubkeys = []
        pubkey_error = f"invalid witness public key ({exc})"
    verified: list[dict] = []
    failures: list[str] = []
    for entry in same_legacy:
        failures.append(
            "missing witness receipt (unsigned entry; a witness public key is "
            "configured so only signed receipts count)"
        )
    for item in same_signed:
        if not pubkeys:
            failures.append(pubkey_error or "invalid witness public key")
            continue
        if not isinstance(item.get("inner"), dict):
            failures.append("receipt check failed: payload_raw is not valid JSON")
            continue
        _ok = False
        _reason = "receipt check failed"
        _key_reasons: list[str] = []
        for _pub in pubkeys:
            _ok, _reason = _verify_witness_receipt(
                item.get("payload_raw"), item.get("receipt"), _pub, file_sha256
            )
            if _ok:
                break
            _key_reasons.append(_reason or "receipt check failed")
        if _ok:
            verified.append(item)
        else:
            # With several trusted keys the loop tries each in turn, so the
            # last reason may blame the wrong key while an earlier key proved
            # the content differs. A proven content mismatch must win: it is
            # the MISMATCH signal, never a wrong-key artefact. Only the
            # artifact comparison is signature-proven (the signature is
            # verified first, then the receipt's file hash is compared), so
            # only it counts here; line_sha256 is checked before any
            # signature verifies and proves nothing about the file.
            _content = next(
                (r for r in _key_reasons if "artifact_sha256 mismatch" in r),
                None,
            )
            failures.append(_content or _reason or "receipt check failed")
    result["receipt_verified"] = len(verified)
    result["receipt_failures"] = len(failures)
    if not verified:
        _first = failures[0] if failures else "no verifiable receipt"
        # Key mismatch is NOT content alteration: every receipt failed only
        # because no trusted key verifies its signature, so the stamp is not
        # from the EPI witness. MISMATCH must mean the file content differs
        # (a verified receipt for a different version), never a wrong key —
        # telling an auditor "altered" when nothing was altered is a
        # trust-critical false positive.
        _sig_only = bool(failures) and all(
            ("signature invalid" in f)
            or ("signature malformed" in f)
            or ("invalid witness public key" in f)
            for f in failures
        )
        if _sig_only:
            result["status"] = "NOT CONFIRMED"
            # An explicitly pinned key (flag/env) that verifies nothing is a
            # forgery signal, not an unchecked stamp: the auditor named the
            # key and the stamp is not from it. The decision step FAILs this
            # in every mode; with only package pins (no explicit key) it
            # stays WARN outside strict.
            result["explicit_key"] = bool(_explicit_hexes)
            _names_key = f" The file names key {doc_key[:16]}…;" if doc_key else ""
            result["detail"] = (
                "WITNESS STAMP NOT CONFIRMED — NOT FROM THE EPI WITNESS: this file "
                f"carries witness receipts but none verifies against a trusted key ({len(failures)} "
                f"receipt failure(s)): {_first}.{_names_key} Pin the EPI witness key "
                "out of band (fetch it from "
                "https://cloud.epilabs.org/.well-known/epi-witness-key.json and confirm "
                "the fingerprint through an independent channel, such as a prior signed "
                "checkpoint or your contract) and re-run with "
                "--witness-pubkey <key> (or EPI_WITNESS_PUBKEY)."
            )
            return result
        result["status"] = "MISMATCH"
        result["received_at"] = None
        # Try to surface a reported time even when nothing verified.
        try:
            _times = []
            for item in same_signed:
                _t = _signed_received_at(item)
                if _t:
                    _times.append(str(_t))
            for entry in same_legacy:
                if entry.get("received_at"):
                    _times.append(str(entry.get("received_at")))
            if _times:
                result["received_at"] = max(_times)
        except Exception:
            pass
        result["detail"] = (
            f"witness receipt verification failed for {len(same)} matched line(s) "
            f"({len(failures)} receipt failure(s)): {_first}; "
            "this copy was never reported with a valid receipt"
        )
        return result
    for item in verified:
        inner = item.get("inner") or {}
        if inner.get("manifest_hash") == manifest_hash and inner.get("file_sha256") == file_sha256:
            _at = _signed_received_at(item)
            result["status"] = "WITNESSED"
            result["mode"] = "verified-receipt"
            result["received_at"] = _at
            result["detail"] = (
                "WITNESSED — verified witness receipt: customer record matches "
                f"(received {_at or 'unknown time'})"
            )
            return result
    for item in verified:
        inner = item.get("inner") or {}
        if content_digest and inner.get("content_digest") == content_digest:
            _at = _signed_received_at(item)
            result["status"] = "WITNESSED"
            result["mode"] = "verified-receipt"
            result["received_at"] = _at
            result["repackaged"] = True
            result["detail"] = (
                "WITNESSED — verified witness receipt: sealed contents match the "
                "customer record "
                f"(received {_at or 'unknown time'}); the file was "
                "re-packaged afterwards (e.g. viewer refreshed or transparency receipt "
                "added, and re-signed)"
            )
            return result
    result["status"] = "MISMATCH"
    _latest = max((_signed_received_at(v) or "" for v in verified), default="") or "unknown time"
    result["received_at"] = _latest
    result["detail"] = (
        f"a different version of this case (same workflow id) was reported to you "
        f"({len(verified)} verified receipt(s), latest {_latest}); this copy was never reported"
    )
    return result


def _emit_json_report(report: dict) -> None:
    """Write a machine-readable verification report directly to stdout."""
    try:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    except BrokenPipeError:
        pass
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
    report_out: Path | None = None,
    epi_file: Path | None = None,
) -> None:
    """Emit a user-facing or JSON verification failure and exit 1."""
    if report_out is not None:
        # The auditor asked for a report file: write one even when the file
        # could not be read far enough for a full report.
        try:
            from datetime import datetime, timezone

            report_out.parent.mkdir(parents=True, exist_ok=True)
            report_out.write_text(
                "EPI VERIFICATION REPORT\n"
                f"File:      {epi_file}\n"
                f"Checked:   {datetime.now(timezone.utc).isoformat()}\n"
                "DECISION:  FAIL\n"
                f"Reason:    {message}\n",
                encoding="utf-8",
            )
            if not json_output:
                console.print(f"[green][OK][/green] Verification report written: {report_out}")
        except OSError:
            pass
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
    report_out.parent.mkdir(parents=True, exist_ok=True)
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
        typer.Option(
            "--policy",
            help="Governance policy: permissive, standard (default), strict (claims/audit: unknown sealer FAILs).",
        ),
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
    offline: bool = typer.Option(
        False,
        "--offline",
        help="No network: skip DID resolution and remote fetches (local pins still apply).",
    ),
    witness_log: Path | None = None,
    witness_pubkey: str | None = None,
    tsa_root: list[Path] | None = None,
    require_timestamp: bool = False,
    require_human_approval: bool = False,
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
    except (FileNotFoundError, PermissionError, OSError):
        tip = (
            f"[red][FAIL] Error:[/red] File not found: {epi_file}\n"
            "[dim]Tip: epi looks relative to your current folder. Use a full path, e.g.[/dim]\n"
            + (
                '[dim]  epi verify "C:\\Users\\you\\project\\artifact.epi"[/dim]\n'
                if os.name == "nt"
                else '[dim]  epi verify "$HOME/project/artifact.epi"[/dim]\n'
            )
            + "[dim]Recordings made with record() are in ./epi-recordings/ (list them: epi ls).[/dim]\n"
            + "[dim]Hosted (no path issues): https://epilabs.org/verify[/dim]"
        )
        _handle_verification_error(
            message=f"File not found: {epi_file}",
            json_output=json_output,
            console_message=tip,
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
    # WP-SEC-4: strict is always local-only — no network at all. A remote
    # listing can never satisfy a strict identity requirement.
    registry.offline = bool(offline) or bool(strict) or policy == VerificationPolicy.STRICT

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

            _warn_legacy_canonicalizer_dispatch(getattr(manifest, "spec_version", None))

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
            _has_sig = False
            try:
                import zipfile as _zf

                with _zf.ZipFile(epi_file) as _z:
                    _has_sig = bool(json.loads(_z.read("manifest.json")).get("signature"))
            except Exception:
                pass
            _handle_verification_error(
                message=f"Structural validation failed: {e}",
                json_output=json_output,
                console_message=f"[red][FAIL] Structural validation failed:[/red] {e}",
                error_type="structural_validation_failed",
                has_signature=_has_sig,
                report_out=report_out,
                epi_file=epi_file,
            )

        # ========== STEP 2: INTEGRITY CHECKS (Facts) ==========
        if verbose:
            console.print("\n[bold]Step 2: Integrity Checks (Facts)[/bold]")

        integrity_ok, mismatches = EPIContainer.verify_integrity(epi_file)

        if verbose:
            # Coverage honesty: name what integrity does NOT cover. Review
            # files are mutable-by-design, SCITT receipts are verified
            # cryptographically (not by file hash), and an unsigned
            # manifest vouches for its own file list.
            try:
                import zipfile as _zf

                with EPIContainer._payload_zip_path(epi_file) as _payload:
                    with _zf.ZipFile(_payload, "r") as _z:
                        _names = [n for n in _z.namelist() if not n.endswith("/")]
                _reviews = [n for n in _names if n == "review.json" or n == "review_index.json" or n.startswith("reviews/")]
                _scitt = [n for n in _names if n.startswith("artifacts/scitt/")]
                if _reviews:
                    console.print(
                        f"  [yellow]![/yellow] {len(_reviews)} review file(s) exempt from "
                        "file hashes (additive, verified via review ledger instead)"
                    )
                if _scitt:
                    console.print(
                        f"  [yellow]![/yellow] {len(_scitt)} SCITT file(s) exempt from "
                        "file hashes (verified via receipt instead)"
                    )
            except Exception:
                pass
            if manifest.signature is None:
                console.print(
                    "  [yellow]![/yellow] Unsigned artifact: manifest.json vouches for "
                    "its own file list — hashes prove self-consistency, not authorship"
                )

        if verbose:
            poly_ok, poly_detail = EPIContainer.verify_polyglot_viewer(epi_file)
            if not poly_ok:
                console.print(f"  [red][FAIL][/red] Polyglot viewer: {poly_detail}")
            elif poly_detail and "legacy" in poly_detail:
                console.print(f"  [yellow]![/yellow] Polyglot viewer: {poly_detail}")
            elif "__polyglot_viewer__" not in mismatches:
                console.print("  [green][OK][/green] Polyglot viewer HTML integrity verified")

        # ========== STEP 3: FORENSIC AUDIT (Facts) ==========
        # Moved forward as these are objective 'facts'
        sequence_ok = True
        completeness_ok = True
        steps_hash_ok = True
        chain_ok = True
        chain_breaks = []
        chain_present = True
        seq_comp_gaps = []
        step_count_ok = True  # AUD-CO-02: safe default for old artifacts
        steps: list[dict] = []
        actual_step_count = 0
        claimed_step_count = manifest.total_steps
        audit_result = {}

        try:
            import hashlib as _hashlib
            import json

            steps = EPIContainer.read_steps(epi_file)
            spec_ver = getattr(manifest, "spec_version", None) if manifest else None
            chain_ok, chain_breaks = _verify_step_chain(steps, spec_version=spec_ver)
            chain_present = _chain_links_present(steps)
            if steps:

                    # 1. Index Sequence Audit (Monotonicity, anchored at 0).
                    # A truncated prefix ([5,6,7]) is monotonic but not complete.
                    indices = [s.get("index", 0) for s in steps]
                    sequence_ok = (
                        (indices[0] == 0)
                        and all(indices[i] == indices[i - 1] + 1 for i in range(1, len(indices)))
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
                        actual_hash = _hashlib.sha256(EPIContainer.read_member_bytes(epi_file, "steps.jsonl")).hexdigest()
                        steps_hash_ok = actual_hash == claimed_hash

                    # 5. prev_hash chain: dispatched above even when steps is empty

                                        # 5.5 AUD-CO-05: Verification Class Classification
                    # Classify steps as recomputable (deterministic, verifiable by re-execution)
                    # or attested_only (non-deterministic, must trust the recorder).
                    recomputable_count = 0
                    attested_count = 0
                    for s in steps:
                        vc = s.get("verification_class") if isinstance(s, dict) else None
                        if not vc and isinstance(s, dict):
                            vc = (s.get("content") or {}).get("verification_class")
                        if vc == "recomputable":
                            recomputable_count += 1
                        elif vc == "attested_only":
                            attested_count += 1
                    unclassified_count = len(steps) - recomputable_count - attested_count
                    if recomputable_count + attested_count > 0:
                        vc_summary = f"{recomputable_count} recomputable, {attested_count} attested"
                        if unclassified_count > 0:
                            vc_summary += f", {unclassified_count} unclassified"
                    else:
                        vc_summary = "not classified"
                    audit_result["verification_class"] = {
                        "status": "not_classified" if (recomputable_count + attested_count == 0) else "classified",
                        "recomputable": recomputable_count,
                        "attested_only": attested_count,
                        "unclassified": unclassified_count,
                        "summary": vc_summary,
                    }

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
                # Use EPIContainer.read_member_bytes for container-format safety
                try:
                    statement_bytes = EPIContainer.read_member_bytes(epi_file, stmt_path)
                except (ValueError, KeyError):
                    statement_bytes = None
                try:
                    receipt_bytes = EPIContainer.read_member_bytes(epi_file, rcpt_path)
                except (ValueError, KeyError):
                    receipt_bytes = None
                if statement_bytes is None:
                    raise Exception(f"SCITT statement not found in archive: {stmt_path}")
                if receipt_bytes is None:
                    raise Exception(f"SCITT receipt not found in archive: {rcpt_path}")

                # Verify statement against manifest (structure + payload hash)
                verify_scitt_statement(statement_bytes, manifest, public_key_bytes=None)

                # Verify receipt signature against statement
                # Fetch service public key from the transparency service or cache
                service_pub_key = _fetch_scitt_service_key(
                    scitt_info.get("service_url"), offline=offline
                )
                if service_pub_key:
                    try:
                        from epi_core.scitt import verify_scitt_receipt
                        verify_scitt_receipt(receipt_bytes, statement_bytes, service_pub_key)
                        transparency_ok = True
                        if verbose:
                            console.print("  [green][OK][/green] SCITT receipt cryptographically verified")
                    except Exception as exc:
                        # A local receipt is signed by the issuing machine's
                        # own service key; on any other machine it simply
                        # cannot be checked (unknown), not proven invalid.
                        _is_local = str(scitt_info.get("service_url") or "").lower() == "local"
                        transparency_ok = None if _is_local else False
                        if verbose:
                            console.print(f"  [red][FAIL][/red] SCITT receipt signature invalid: {exc}")
                else:
                    # Service key unavailable: structural shape alone is NOT proof.
                    # Report unknown (None) so callers cannot mistake it for a
                    # cryptographic verification.
                    receipt = cbor2.loads(receipt_bytes)
                    if isinstance(receipt, cbor2.CBORTag) and receipt.tag == 18:
                        transparency_ok = None
                        if verbose:
                            console.print("  [yellow][WARN][/yellow] SCITT receipt structurally shaped (COSE tag 18) but service key unavailable — transparency UNVERIFIED, not verified")
                    else:
                        transparency_ok = False

                if verbose:
                    if transparency_ok is True:
                        console.print("  [green][OK][/green] SCITT receipt cryptographically verified")
                    elif transparency_ok is None:
                        console.print("  [yellow][WARN][/yellow] SCITT transparency unverified (receipt present, no service key)")
                    else:
                        console.print("  [red][FAIL][/red] SCITT receipt invalid")
            except Exception as exc:
                transparency_ok = False
                if verbose:
                    console.print(f"  [yellow][WARN][/yellow] SCITT verification failed: {exc}")

        
        # ========== STEP 4.75: ANNEX IV COMPLIANCE CHECK ==========
        annex_iv_ok = True
        try:
            annex_members = [m for m in EPIContainer.list_members(epi_file) if m.startswith("artifacts/annex_iv/")]
            if annex_members:
                if verbose:
                    console.print("\n[bold]Step 4.75: Annex IV Compliance[/bold]")
                for am in annex_members:
                    sig = EPIContainer.read_member_text(epi_file, am)
                    data = json.loads(sig)
                    appr = data.get("approval",{})
                    if appr.get("signature"):
                        parts = appr["signature"].split(":",2)
                        if len(parts)==3 and parts[0]=="ed25519":
                            ac = {k:v for k,v in appr.items() if k!="signature"}
                            cd = dict(data); cd["approval"] = ac; cd.pop("signature",None)
                            can = json.dumps(cd, sort_keys=True, separators=(",",":"), default=str)
                            try:
                                from epi_core.keys import KeyManager
                                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                                pb = KeyManager().load_public_key(parts[1])
                                ed = Ed25519PublicKey.from_public_bytes(pb)
                                ed.verify(bytes.fromhex(parts[2]), can.encode("utf-8"))
                                if verbose:
                                    color = "green"
                                    console.print(f"  [green][OK][/green] Signed: {am}")
                            except Exception:
                                annex_iv_ok = False
                                if verbose:
                                    console.print(f"  [red][FAIL][/red] Invalid signature: {am}")
                        else:
                            annex_iv_ok = False
                            if verbose:
                                console.print(f"  [red][FAIL][/red] Bad signature format: {am}")
                    else:
                        if verbose:
                            console.print(f"  [yellow][INFO][/yellow] Unsigned: {am}")
        except Exception as exc:
            annex_iv_ok = False
            if verbose:
                console.print(f"  [red][FAIL][/red] Annex IV check error: {exc}")
        if annex_iv_ok and verbose:
            console.print(f"  [green]All Annex IV sections validated.[/green]")

        # Sealed payload completeness (not capture completeness).
        # true = recorder truncated before seal → fail.
        # None = artifact sealed through 4.4.1; may have truncated strings at 2000 chars → warn.
        # false = this seal asserts full step payloads.
        content_truncated = manifest.content_truncated
        integrity_ok = sealed_payload_gate(manifest, integrity_ok)
        if content_truncated is True:
            if verbose:
                console.print(
                    "  [red][FAIL][/red] Manifest content_truncated=true — "
                    "step payloads were shortened before seal"
                )
        elif content_truncated is None:
            if verbose:
                console.print(
                    "  [yellow][WARN][/yellow] Manifest has no content_truncated field — "
                    "artifacts sealed through 4.4.1 may have truncated step strings at 2000 characters. "
                    "Do not treat those payloads as complete."
                )
        elif verbose:
            console.print(
                "  [green][OK][/green] content_truncated=false — sealed step payloads are full "
                "(viewer previews may still shorten display)"
            )

        # ========== STEP 5: CREATE REPORT & APPLY POLICY ==========
        forensic_reason: str | None = None
        if not completeness_ok and seq_comp_gaps:
            forensic_reason = seq_comp_gaps[0]
        elif not chain_ok and chain_breaks:
            forensic_reason = chain_breaks[0]
        elif not sequence_ok:
            forensic_reason = "step sequence invalid"
        elif not completeness_ok:
            forensic_reason = "step sequence incomplete (e.g. tool.call without tool.response)"
        elif content_truncated is True:
            forensic_reason = "manifest content_truncated=true (payload shortened before seal)"

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
            chain_present=chain_present,
            transparency_ok=transparency_ok,
            completeness_gaps=seq_comp_gaps,
            forensic_reason=forensic_reason,
        )

        # ========== STEP 4.8: CAPTURE MANIFEST (Feature 1) ==========
        # Machine-readable scope declaration; absent on pre-v artifacts.
        _cap_manifest: dict | None = None
        _cap_downgrade_n = 0
        try:
            _cap_manifest = EPIContainer.read_member_json(epi_file, "artifacts/manifest.json")
        except Exception:
            _cap_manifest = None
        if isinstance(_cap_manifest, dict):
            try:
                _cap_downgrade_n = len(_cap_manifest.get("fail_open_events") or [])
            except Exception:
                _cap_downgrade_n = 0
            report["capture_manifest"] = _cap_manifest
            report["capture_manifest_present"] = True
            report["enforcement_downgraded"] = _cap_downgrade_n > 0
            report["enforcement_downgrade_count"] = _cap_downgrade_n
            if _cap_downgrade_n > 0:
                # Top-line warning-level flag — never render identically to fully-enforced.
                report["summary"]["integrity"] = (
                    f"VERIFIED (enforcement downgraded for {_cap_downgrade_n} events)"
                    if integrity_ok else report["summary"].get("integrity", "FAILED")
                )
        else:
            report["capture_manifest"] = None
            report["capture_manifest_present"] = False
            report["enforcement_downgraded"] = False
            report["enforcement_downgrade_count"] = 0
        if verbose:
            if _cap_manifest is None:
                console.print(
                    "  [yellow]![/yellow] No capture manifest (pre-v artifact, scope undeclared)"
                )
            else:
                _cp = _cap_manifest.get("capture_path", "unknown")
                _ce = _cap_manifest.get("gateway_enforcement", "not_applicable")
                console.print(f"  [green][OK][/green] Capture manifest: path={_cp} enforcement={_ce}")
                if _cap_downgrade_n > 0:
                    console.print(
                        f"  [yellow][WARN][/yellow] INTEGRITY: VERIFIED "
                        f"(enforcement downgraded for {_cap_downgrade_n} events)"
                    )

        # ========== STEP 4.9: FORWARD-SECURE CHECKPOINTS (Feature 2) ==========
        _cp_ok = True
        _cp_messages: list[str] = []
        _cp_records: list[dict] = []
        try:
            _tsa_roots = _tsa_trust_roots(tsa_root)
        except Exception:
            _tsa_roots = []
        try:
            from epi_core.checkpoints import verify_checkpoints

            _cp_ok, _cp_messages, _cp_records = verify_checkpoints(
                epi_file, steps, trust_roots=_tsa_roots
            )
        except Exception as _cp_err:
            _cp_ok = False
            _cp_messages = [f"checkpoint verification error: {_cp_err}"]
            _cp_records = []
        report["checkpoints"] = {
            "ok": _cp_ok,
            "messages": _cp_messages,
            "count": len(_cp_records),
        }
        if not _cp_ok:
            integrity_ok = False
            # Specific message matters — never a generic failure alone.
            # Keep facts/report consistent: the local integrity_ok feeds nothing
            # else after report creation, so update the report fields directly.
            for _key in ("facts",):
                try:
                    report[_key]["integrity_ok"] = False
                    report[_key]["chain_ok"] = False
                except Exception:
                    pass
            try:
                report["integrity_ok"] = False
            except Exception:
                pass
            try:
                report["summary"]["integrity"] = _cp_messages[0] if _cp_messages else "FAILED"
            except Exception:
                pass
        if verbose:
            if _cp_records:
                console.print(
                    f"  [green][OK][/green] Checkpoints: {len(_cp_records)} record(s) present"
                    if _cp_ok else
                    f"  [red][FAIL][/red] Checkpoints: {len(_cp_records)} record(s), issues found"
                )
                for _m in _cp_messages:
                    if _m.startswith("CHECKPOINT TIMESTAMP UNVERIFIED"):
                        console.print(f"  [yellow][WARN][/yellow] {_m}")
                    else:
                        console.print(f"  [red][FAIL][/red] {_m}")
            else:
                console.print("  [dim]Checkpoints: none (seal-time notarization only)[/dim]")

        # ========== STEP 4.9b: CAPTURE-TIME CHECKPOINTS (gateway exports) ==========
        # Raw-event chain from artifacts/capture/events.jsonl vs capture
        # checkpoints. Old exports and SDK seals carry no capture evidence
        # and pass vacuously with their prior verdicts.
        _cc_ok = True
        _cc_messages: list[str] = []
        _cc_records: list[dict] = []
        try:
            from epi_core.case_store import verify_capture_checkpoints

            _cc_ok, _cc_messages, _cc_records = verify_capture_checkpoints(
                epi_file, trust_roots=_tsa_roots
            )
        except Exception as _cc_err:
            _cc_ok = False
            _cc_messages = [f"capture checkpoint verification error: {_cc_err}"]
            _cc_records = []
        report["capture_checkpoints"] = {
            "ok": _cc_ok,
            "messages": _cc_messages,
            "count": len(_cc_records),
        }
        if not _cc_ok:
            integrity_ok = False
            try:
                report["facts"]["integrity_ok"] = False
                report["facts"]["chain_ok"] = False
            except Exception:
                pass
            try:
                report["integrity_ok"] = False
            except Exception:
                pass
            try:
                report["summary"]["integrity"] = _cc_messages[0] if _cc_messages else "FAILED"
            except Exception:
                pass
        if verbose:
            if _cc_records:
                console.print(
                    f"  [green][OK][/green] Capture checkpoints: {len(_cc_records)} record(s) present"
                    if _cc_ok else
                    f"  [red][FAIL][/red] Capture checkpoints: {len(_cc_records)} record(s), issues found"
                )
                for _m in _cc_messages:
                    if _m.startswith("CAPTURE TIMESTAMP UNVERIFIED"):
                        console.print(f"  [yellow][WARN][/yellow] {_m}")
                    else:
                        console.print(f"  [red][FAIL][/red] {_m}")
            else:
                console.print("  [dim]Capture checkpoints: none (not a gateway export)[/dim]")
        # ========== STEP 4.95: RFC 3161 TIMESTAMP VALIDATION ==========
        # Offline validation of seal-time and checkpoint tokens against pinned
        # TSA roots. Old artifacts (no imprint_scheme) report legacy/presence
        # only and never change the decision.
        try:
            _timestamps = _build_timestamps_block(epi_file, manifest, _cp_records, tsa_root)
        except Exception as _ts_err:
            _timestamps = {
                "seal": [],
                "checkpoints": [],
                "earliest_verified": None,
                "statement": "timestamps not evaluated in this report",
                "clock_warning": None,
            }
            if verbose:
                console.print(f"  [yellow]![/yellow] Timestamp validation skipped: {_ts_err}")
        report["timestamps"] = _timestamps
        try:
            report["facts"]["timestamp_verified"] = bool(
                any(e.get("status") == "valid" for e in _timestamps.get("seal", []))
                or any(c.get("status") == "valid" for c in _timestamps.get("checkpoints", []))
            )
        except Exception:
            pass

        # Apply the selected governance policy
        active_policy = VerificationPolicy.STRICT if strict else policy
        apply_policy(report, active_policy)
        # Preserve checkpoint failure through policy application.
        if not _cp_ok:
            try:
                report["decision"]["status"] = "FAIL"
                _rs = report["decision"].get("reason", "")
                _cp_first = _cp_messages[0] if _cp_messages else "checkpoint verification failed"
                if _cp_first not in _rs:
                    report["decision"]["reason"] = f"{_rs} {_cp_first}".strip()
            except Exception:
                pass
        # Preserve capture-checkpoint failure the same way.
        if not _cc_ok:
            try:
                report["decision"]["status"] = "FAIL"
                _rs = report["decision"].get("reason", "")
                _cc_first = _cc_messages[0] if _cc_messages else "capture checkpoint verification failed"
                if _cc_first not in _rs:
                    report["decision"]["reason"] = f"{_rs} {_cc_first}".strip()
            except Exception:
                pass
        # A new-scheme seal token that fails validation means tampering: FAIL
        # in every policy. Missing or legacy tokens never change the decision
        # (unless --require-timestamp is set). The tamper detail REPLACES the
        # policy reason (which may still read "Integrity verified ..."), and
        # file integrity is left as measured: the hashes verified, it is the
        # time attestation that is broken.
        _ts_invalid = [
            e for e in _timestamps.get("seal", [])
            if e.get("status") in _TIMESTAMP_TAMPER_STATUSES
        ]
        if _ts_invalid:
            try:
                report["decision"]["status"] = "FAIL"
                report["decision"]["reason"] = str(
                    _ts_invalid[0].get("detail") or "seal timestamp invalid"
                )
            except Exception:
                pass
        if require_timestamp and not any(
            e.get("status") == "valid" for e in _timestamps.get("seal", [])
        ):
            try:
                _prior = report["decision"].get("status")
                report["decision"]["status"] = "FAIL"
                _rs = report["decision"].get("reason", "")
                _msg = "no valid seal-time timestamp (--require-timestamp)"
                if _msg not in _rs:
                    if _prior == "FAIL":
                        report["decision"]["reason"] = f"{_rs}; {_msg}".strip("; ")
                    else:
                        # Only the timestamp requirement failed; say so plainly
                        # rather than appending to a "verified" sentence.
                        report["decision"]["reason"] = (
                            f"{_msg[0].upper()}{_msg[1:]}. The seal itself is intact."
                        )
            except Exception:
                pass
        if _timestamps.get("clock_warning") and report.get("decision", {}).get("status") == "PASS":
            try:
                report["decision"]["status"] = "WARN"
                _rs = report["decision"].get("reason", "")
                report["decision"]["reason"] = (
                    f"{_rs} {_timestamps['clock_warning']}".strip()
                )
            except Exception:
                pass
        # Preserve downgrade flag through policy application (apply_policy rewrites decision).
        if _cap_downgrade_n > 0 and integrity_ok:
            try:
                if report.get("decision", {}).get("status") == "PASS":
                    report["decision"]["status"] = "WARN"
                    _rs = report["decision"].get("reason", "")
                    report["decision"]["reason"] = (
                        f"{_rs} INTEGRITY: VERIFIED (enforcement downgraded for {_cap_downgrade_n} events)".strip()
                    )
            except Exception:
                pass
        # ========== CUSTOMER WITNESS LOG (--witness-log) ==========
        # MISMATCH means the file differs from what the customer was told at
        # seal time: FAIL in every policy. A missing entry is WARN (FAIL under
        # strict); an unreadable log FAILs.
        try:
            _witness = _check_witness_log(epi_file, manifest, witness_log, witness_pubkey)
        except Exception:
            _witness = {"status": "NOT CHECKED", "received_at": None, "matches": 0,
                        "detail": "witness check crashed"}
        report["witness"] = _witness
        if _witness.get("status") == "UNREADABLE":
            try:
                _prior = report["decision"].get("status")
                report["decision"]["status"] = "FAIL"
                _rs = report["decision"].get("reason", "")
                _msg = str(_witness.get("detail"))
                report["decision"]["reason"] = (
                    f"{_rs}; {_msg}" if _prior == "FAIL" else
                    f"Witness check not done: {_msg}. The seal itself is intact."
                )
            except Exception:
                pass
        elif _witness.get("status") == "NOT IN WITNESS LOG":
            # A seal the vendor never reported is exactly what a re-run or
            # re-sealed case looks like. Never a clean PASS.
            try:
                if report["decision"].get("status") == "PASS":
                    # strict = claim/audit acceptance (scripts rely on exit 1).
                    report["decision"]["status"] = (
                        "FAIL" if active_policy == VerificationPolicy.STRICT else "WARN"
                    )
                    report["decision"]["reason"] = (
                        "Seal and signer are valid, but this seal was never reported to "
                        f"your witness log ({_witness.get('detail')}). It may be a re-run "
                        "or re-sealed copy; ask the vendor for the copy that is in your "
                        "witness log."
                    )
            except Exception:
                pass
        elif _witness.get("status") == "NOT CONFIRMED":
            # Receipt-bearing file, no trusted key: the stamps are UNCHECKED.
            # Never a clean PASS; FAIL under strict (the auditor acceptance
            # command), WARN otherwise. Exception: the auditor explicitly
            # pinned a key and the stamp is not from it — a forged stamp.
            # That FAILs in every mode; "unconfirmed" would understate a fake.
            try:
                _prior = report["decision"].get("status")
                if _witness.get("explicit_key"):
                    if _prior != "FAIL":
                        _rs = report["decision"].get("reason", "")
                        _msg = (
                            "Witness stamp is NOT FROM THE EPI WITNESS: a key was "
                            "explicitly pinned and no receipt verifies against it."
                        )
                        report["decision"]["status"] = "FAIL"
                        report["decision"]["reason"] = (
                            f"{_rs}; {_msg}".strip("; ") if _prior == "WARN" else _msg
                        )
                elif _prior == "PASS":
                    report["decision"]["status"] = (
                        "FAIL" if active_policy == VerificationPolicy.STRICT else "WARN"
                    )
                    report["decision"]["reason"] = (
                        "Seal and signer are valid, but the witness stamps were not "
                        f"checked ({_witness.get('detail')})"
                    )
            except Exception:
                pass
        if _witness.get("status") == "MISMATCH":
            # The file's own seal may be perfectly valid (a re-export or a
            # re-signed copy). What failed is: it is not what you were told.
            # FAIL in every policy, but never mislabelled as "file altered".
            try:
                _prior = report["decision"].get("status")
                report["decision"]["status"] = "FAIL"
                _rs = report["decision"].get("reason", "")
                _msg = str(_witness.get("detail") or "witness mismatch")
                report["decision"]["reason"] = (
                    f"{_rs}; {_msg}" if _prior == "FAIL" else
                    f"Not the version reported to you: {_msg}. Ask the vendor for the "
                    "copy that is in your witness log."
                )
            except Exception:
                pass

        # ========== HUMAN APPROVAL (who approved, if anyone) ==========
        # Computed whenever the file carries reviews or agent approval steps,
        # so nobody needs a second flag to see it. Never trusts the file's own
        # claim: only a key pinned as an approver, distinct from the sealing
        # key, counts as human_signed. An invalid approval FAILs (fail-closed).
        try:
            from epi_core.review import verify_human_approvals

            _human = verify_human_approvals(epi_file)
        except Exception as _human_err:
            _human = {
                "status": "none",
                "approvals": [],
                "requests": [],
                "present": False,
                "requirement_met": False,
                "detail": f"human approval not evaluated: {_human_err}",
            }
        _human["required"] = bool(require_human_approval)
        report["human_approval"] = _human
        if _human.get("status") == "failed":
            try:
                _prior = report["decision"].get("status")
                _rs = report["decision"].get("reason", "")
                _msg = str(_human.get("detail") or "an approval is invalid")
                report["decision"]["status"] = "FAIL"
                report["decision"]["reason"] = (
                    f"{_rs}; approval invalid: {_msg}" if _prior == "FAIL"
                    else f"Approval invalid — {_msg}. The seal itself is intact."
                )
            except Exception:
                pass
        if require_human_approval and not _human.get("requirement_met"):
            try:
                _prior = report["decision"].get("status")
                _rs = report["decision"].get("reason", "")
                _detail = _human.get("detail") or "no human-signed approval"
                _msg = f"Human approval required: {_detail}"
                report["decision"]["status"] = "FAIL"
                report["decision"]["reason"] = f"{_rs}; {_msg}" if _prior == "FAIL" else _msg
            except Exception:
                pass

        # ========== AIUC-1 DOMAIN MAPPING ==========
        if aiuc1:
            aiuc1_statuses = map_verification_to_aiuc1(report, manifest=manifest, steps=steps, epi_path=epi_file)
            report["aiuc1"] = aiuc1_summary(aiuc1_statuses)
            if verbose:
                console.print("\n[bold]Evidence by AIUC-1 domain[/bold] [dim](EPI's own checks, not an AIUC-1 result)[/dim]")
                for domain_id, status in aiuc1_statuses.items():
                    color = _AIUC1_COLORS.get(status.status, "dim")
                    words = _AIUC1_WORDS.get(status.status, status.status)
                    console.print(f"  [{color}]{domain_id}. {status.label}: {words}[/{color}]")

        # ========== STEP 5: REVIEW TRUST CHECKS ==========
        try:
            from epi_core.review import read_review

            _latest_review = read_review(epi_file)
        except Exception:
            _latest_review = None

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
            gov = getattr(manifest, "governance", None) or {}
            org_root = gov.get("org_root") if isinstance(gov, dict) else None
            print_trust_report(report, epi_file, verbose, org_root=org_root)
            if review_report is not None:
                print_review_trust_report(review_report)
            elif _latest_review is not None:
                # Discoverability: surface that a review exists without failing the run
                who = getattr(_latest_review, "reviewed_by", None) or "reviewer"
                console.print(
                    f"\n[dim]Human review present (by {who}). "
                    f"Full binding check: [cyan]epi verify {epi_file.name} --review[/cyan][/dim]"
                )

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
            console.print("[dim]Upload this file to verify in your browser:[/dim]")
            console.print(f"[green]{epi_file.resolve()}[/green]\n")
            try:
                import webbrowser
                webbrowser.open(portal_url)
            except Exception:
                console.print("[yellow]Could not open browser automatically.[/yellow]")
                console.print(f"[cyan]Please visit: {portal_url}[/cyan]")

        if qr and not json_output:
            portal_url = "https://epilabs.org/verify"
            console.print("\n[bold cyan]Scan this QR code to verify on your phone:[/bold cyan]")
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


def print_trust_report(report: dict, epi_file: Path, verbose: bool = False, org_root: str | None = None):
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

    # Header chrome: green only for org-trusted PASS. Unpinned seal is yellow
    # UNVERIFIED IDENTITY — never "SEAL OK" (skim must not imply claim safety).
    #
    # "PINNED" is reserved for a key the VERIFIER pinned. A key that only
    # appears in a did:web document published by the file's own author is
    # self-asserted — the signer vouches for themselves — and must never be
    # described with the word "pinned" (red-team F-19).
    id_upper = str(identity_status).upper()
    pin_source = str((identity or {}).get("pin_source") or "none").lower()
    self_asserted = id_upper == "KNOWN" and pin_source == "did_web"
    if decision_status == "PASS" and id_upper == "KNOWN" and not self_asserted:
        status_symbol = "[bold green]✔ SEAL · IDENTITY PINNED[/bold green]"
        panel_style = "green"
    elif decision_status == "PASS" and self_asserted:
        status_symbol = "[bold yellow]✔ SEAL · SIGNER SELF-ASSERTED (DID)[/bold yellow]"
        panel_style = "yellow"
    elif decision_status == "PASS":
        status_symbol = "[bold green]✔ PASS[/bold green]"
        panel_style = "green"
    elif decision_status == "WARN" and id_upper == "KNOWN" and self_asserted:
        status_symbol = "[bold yellow]⚠ SIGNER SELF-ASSERTED (DID) · SEE WARNING[/bold yellow]"
        panel_style = "yellow"
    elif decision_status == "WARN" and id_upper == "KNOWN":
        # Signer is pinned; something else (witness log, clock) needs a look.
        _wit_hdr = (report.get("witness") or {}).get("status") if isinstance(report, dict) else None
        if _wit_hdr == "NOT IN WITNESS LOG":
            status_symbol = "[bold yellow]⚠ NOT IN YOUR WITNESS LOG · SIGNER PINNED[/bold yellow]"
        elif not completeness_ok:
            status_symbol = "[bold yellow]⚠ EVIDENCE INCOMPLETE · SIGNER PINNED[/bold yellow]"
        else:
            status_symbol = "[bold yellow]⚠ SIGNER PINNED · SEE WARNING[/bold yellow]"
        panel_style = "yellow"
    elif decision_status == "WARN" and id_upper == "LOCAL":
        status_symbol = "[bold yellow]⚠ LOCAL SEALER · NOT ORG-PINNED[/bold yellow]"
        panel_style = "yellow"
    elif decision_status == "WARN":
        status_symbol = "[bold yellow]⚠ UNVERIFIED IDENTITY[/bold yellow]"
        panel_style = "yellow"
    elif not (integrity_ok and sequence_ok and chain_ok):
        status_symbol = "[bold red]✘ SEAL FAIL — FILE ALTERED[/bold red]"
        panel_style = "red"
    elif signature_valid is False:
        status_symbol = "[bold red]✘ SEAL FAIL — SIGNATURE INVALID[/bold red]"
        panel_style = "red"
    elif ((report.get("witness") or {}).get("status") if isinstance(report, dict) else None) == "MISMATCH":
        status_symbol = "[bold red]✘ FAIL — NOT THE VERSION REPORTED TO YOU[/bold red]"
        panel_style = "red"
    elif signature_valid is True and id_upper == "UNKNOWN" and (
        "facts" in report and (report.get("identity") or {}).get("pinned_names")
    ):
        status_symbol = "[bold red]✘ FAIL — NOT A KEY YOU TRUST[/bold red]"
        panel_style = "red"
    else:
        # Seal intact; a policy requirement (identity, timestamp, ...) failed.
        status_symbol = "[bold red]✘ FAIL — SEAL INTACT, REQUIREMENT NOT MET[/bold red]"
        panel_style = "red"

    content_lines = []

    # Capture Manifest — prominent, never buried. Downgraded artifacts must
    # not render identically to fully-enforced ones.
    _cap = report.get("capture_manifest")
    _downgrade_n = int(report.get("enforcement_downgrade_count") or 0)
    if _cap is None and not report.get("capture_manifest_present", True):
        content_lines.append(
            "[bold]INTEGRITY: scope undeclared[/bold]  "
            "[dim]— No capture manifest (pre-v artifact, scope undeclared)[/dim]"
        )
        content_lines.append("")
    elif isinstance(_cap, dict):
        _cp = _cap.get("capture_path", "unknown")
        _ce = _cap.get("gateway_enforcement", "not_applicable")
        content_lines.append(
            f"[bold]CAPTURE: path={_cp} enforcement={_ce}[/bold]"
        )
        if _downgrade_n > 0 and decision_status != "FAIL":
            content_lines.append(
                f"[bold yellow]INTEGRITY: VERIFIED "
                f"(enforcement downgraded for {_downgrade_n} events)[/bold yellow]"
            )
            # Downgrade top-line chrome to warning-level even if identity is pinned.
            status_symbol = (
                f"[bold yellow]⚠ VERIFIED (enforcement downgraded for {_downgrade_n} events)[/bold yellow]"
            )
            panel_style = "yellow"
        content_lines.append("")

    # Decision Layer — identity failure mode first when unpinned
    if decision_status == "WARN" and signature_valid is True and integrity_ok and id_upper != "KNOWN":
        if id_upper == "LOCAL":
            content_lines.append(
                "[bold]DECISION: WARN[/bold]  "
                "[dim]— LOCAL SEALER (seal valid · not org-pinned)[/dim]"
            )
        else:
            content_lines.append(
                "[bold]DECISION: WARN[/bold]  "
                "[dim]— UNVERIFIED IDENTITY (seal valid · signer unknown)[/dim]"
            )
    else:
        content_lines.append(f"[bold]DECISION: {decision_status}[/bold]")
    content_lines.append(f"Policy: {decision_policy}")
    content_lines.append(f"Reason: {decision_reason}")
    content_lines.append("")

    # Identity Layer FIRST — trust context before green seal proofs
    content_lines.append(
        "[bold underline]IDENTITY (who sealed — required for claim trust)[/bold underline]"
    )
    id_status_display = identity_status
    pinned_names = identity.get("pinned_names") if isinstance(identity, dict) else None
    pinned_names = [str(n) for n in (pinned_names or []) if str(n).strip()]
    untrusted_despite_pins = bool(id_upper == "UNKNOWN" and pinned_names)
    if id_upper == "UNKNOWN":
        if untrusted_despite_pins:
            id_status_display = f"NOT A KEY YOU TRUST (you have pinned: {', '.join(pinned_names)})"
        else:
            id_status_display = "NOT_PINNED"
    if identity_status == "KNOWN":
        id_color = "green"
    elif identity_status == "LOCAL":
        id_color = "yellow"
    elif identity_status in ("REVOKED", "MISMATCH") or untrusted_despite_pins:
        id_color = "red"
    else:
        id_color = "yellow"
    if identity_status == "KNOWN" and self_asserted:
        # Self-asserted identity must not read as green/pinned (red-team F-19).
        id_color = "yellow"
        id_status_display = "SELF-ASSERTED (not pinned)"
    content_lines.append(f"  [{id_color}]- Status:       {id_status_display}[/{id_color}]")
    if self_asserted:
        content_lines.append(
            "  [yellow]- Trust:        The signer published this key in their own DID "
            "document at their own domain.[/yellow]"
        )
        content_lines.append(
            "  [yellow]                That is self-assertion, not a pin you chose. "
            "Require an org pin with: epi verify --policy strict[/yellow]"
        )
    if untrusted_despite_pins:
        content_lines.append(
            "  [red]- Trust:        This file was not sealed by a key you trust.[/red]"
        )
    _canon_fp = identity.get("fingerprint") if isinstance(identity, dict) else None
    _name_is_fp = bool(
        _canon_fp and identity_name
        and str(identity_name).replace(" ", "") == _canon_fp.replace(" ", "")
    )
    content_lines.append(f"  - Name:         {'—' if _name_is_fp else (identity_name or '—')}")
    if _canon_fp:
        content_lines.append(
            f"  - Fingerprint:  {_canon_fp}  [dim](confirm with the sender by phone)[/dim]"
        )
    else:
        fp = None
        if isinstance(identity, dict):
            fp = identity.get("public_key_fingerprint") or identity.get("public_key_id")
        if not fp:
            fp = public_key_id
        if fp:
            content_lines.append(f"  - Fingerprint:  {fp}…")
    local_name = identity.get("local_key_name") if isinstance(identity, dict) else None
    if local_name:
        content_lines.append(f"  - Local key:    {local_name} (matches this computer — not org pin)")
    did_identity = identity.get("did") if isinstance(identity, dict) else None
    if did_identity:
        _det = str(identity.get("detail") or "") if isinstance(identity, dict) else ""
        if "Verified via DID:WEB" in _det:
            _did_note = "(resolved; key listed in the DID document)"
        elif "DID" in _det:
            _did_note = ""  # the Detail line already says what happened
        else:
            _did_note = "(claimed by the file; not checked)"
        content_lines.append(f"  - DID:          {did_identity} {_did_note}".rstrip())
    if org_root:
        # Named only — this command never verifies a bundle. Point at the
        # command that does, same honesty as the browser viewer tooltip.
        # Two lines, command first on its own: a narrow terminal can only
        # wrap after the variable tail, never inside the command phrase.
        content_lines.append(
            f"  - Org root:     {str(org_root)[:16]}… (named, not verified here)"
        )
        file_name = Path(epi_file).name if hasattr(epi_file, "name") or isinstance(epi_file, str) else str(epi_file)
        content_lines.append(
            f"  confirm: epi org bundle verify {file_name} <bundle.json>"
        )
    content_lines.append(f"  - Detail:       {identity_detail}")
    if "LISTED" in str(identity_detail) and identity_name:
        # WP-SEC-4: the key appears in the public registry file, which is
        # unsigned and informational only — never a pin. Say so explicitly.
        content_lines.append(
            f'  - Registry:     listed as "{identity_name}" by epilabs.org (not a pin)'
        )
    content_lines.append("")

    # Fact Layer (seal) — objective proofs; valid seal alone is not identity
    content_lines.append("[bold underline]SEAL (Objective Proofs — not identity)[/bold underline]")
    i_color = "green" if integrity_ok else "red"
    content_lines.append(
        f"  [{i_color}]- Integrity:    {'Verified' if integrity_ok else 'FAILED'}[/{i_color}]"
    )

    s_color = "green" if signature_valid else ("yellow" if signature_valid is None else "red")
    s_text = "Valid" if signature_valid else ("Unsigned" if signature_valid is None else "INVALID")
    content_lines.append(f"  [{s_color}]- Signature:    {s_text}[/{s_color}]")

    f_ok = sequence_ok and completeness_ok and chain_ok
    f_color = "green" if f_ok else "red"
    f_text = "PASS" if f_ok else "FAIL"
    f_reason = (
        facts.get("forensic_reason")
        or report.get("forensic_reason")
        or ""
    )
    if not f_ok and not f_reason:
        gaps = facts.get("completeness_gaps") or report.get("completeness_gaps") or []
        if gaps:
            f_reason = str(gaps[0])
        elif not chain_ok:
            f_reason = "prev_hash chain broken"
        elif not sequence_ok:
            f_reason = "step sequence invalid"
        elif not completeness_ok:
            f_reason = "step sequence incomplete (e.g. tool.call without tool.response)"
    if f_ok:
        content_lines.append(f"  [{f_color}]- Forensic:     {f_text}[/{f_color}]")
    else:
        detail = f" — {f_reason}" if f_reason else ""
        content_lines.append(f"  [{f_color}]- Forensic:     {f_text}{detail}[/{f_color}]")

    # Timestamp status — validated offline by epi verify against pinned TSA
    # roots. New-scheme tokens never render "presence only"; legacy tokens
    # (sealed before imprints existed) and reports that never evaluated
    # timestamps keep the honest presence-only wording.
    _ts_block = report.get("timestamps") or {}
    _seal_entries = _ts_block.get("seal") or []
    if not _seal_entries and str(_ts_block.get("statement", "")).startswith(
        "timestamps not evaluated"
    ):
        # Notarization status — RFC 3161 token presence only. The token's CMS
        # signature, chain, and messageImprint are NOT validated (see
        # KNOWN_LIMITATIONS.md), so this never renders green.
        notarization_status = "dim]Not available"
        try:
            epi_path = Path(epi_file) if isinstance(epi_file, str) else epi_file
            from zipfile import ZipFile
            with ZipFile(epi_path, "r") as zf:
                if "artifacts/notarization/notarization.json" in zf.namelist():
                    notar_data = json.loads(zf.read("artifacts/notarization/notarization.json"))
                    provider = (notar_data.get("notarized_at") or {}).get("provider", "unknown")
                    tsa_url = (notar_data.get("notarized_at") or {}).get("url", "")
                    gen_time = notar_data.get("tsa_genTime") or ""
                    notarization_status = f"yellow]RFC 3161 token present ({provider}"
                    if tsa_url:
                        notarization_status += f" via {tsa_url}"
                    if gen_time:
                        notarization_status += f" · genTime {gen_time}"
                    notarization_status += "; signature not validated)"
        except Exception:
            pass
        content_lines.append(f"  - Notarized:    [{notarization_status}")
    else:
        _ts_invalid = [
            e for e in _seal_entries
            if e.get("status") in ("imprint_mismatch", "bad_signature", "cert_invalid")
        ]
        _ts_valid = [e for e in _seal_entries if e.get("status") == "valid"]
        _ts_legacy = [e for e in _seal_entries if e.get("status") == "legacy"]
        if _ts_invalid:
            content_lines.append(
                f"  [red]- Timestamp:    INVALID — {_ts_invalid[0].get('detail')}[/red]"
            )
        elif _ts_valid:
            _ts_earliest = min(e["gen_time"] for e in _ts_valid if e.get("gen_time"))
            _ts_roots = sorted(
                {str(e.get("tsa_root") or e.get("url") or "?") for e in _ts_valid}
            )
            _ts_where = "; ".join(f'chain to pinned root "{r}"' for r in _ts_roots)
            _ts_keyed = [e for e in _ts_valid if e.get("key_bound")]
            if _ts_keyed:
                _raw_fp = str(_ts_keyed[0].get("imprinted_key_fingerprint") or "?")
                _ts_fp = " ".join(
                    _raw_fp[i : i + 4] for i in range(0, len(_raw_fp), 4)
                )
                _ts_what = f"sealed by key {_ts_fp} no later than {_ts_earliest}"
            else:
                _ts_what = (
                    f"contents existed no later than {_ts_earliest} "
                    "(CONTENTS-ONLY — signing key not bound)"
                )
            content_lines.append(
                f"  [green]- Timestamp:    VERIFIED — {_ts_what} ({_ts_where})[/green]"
            )
        elif _ts_legacy:
            content_lines.append(
                "  [yellow]- Timestamp:    legacy token — imprint not recomputable "
                "(sealed before 4.6); presence only[/yellow]"
            )
        else:
            content_lines.append("  - Timestamp:    none")
        if _ts_block.get("clock_warning"):
            content_lines.append(
                f"  [yellow]- Clock:       {_ts_block['clock_warning']}[/yellow]"
            )

    # Customer witness log check (--witness-log). Silent unless requested.
    _wit = report.get("witness") or {}
    _wit_status = _wit.get("status") or "NOT CHECKED"
    _file_ok = bool(integrity_ok and sequence_ok and chain_ok and signature_valid is not False)
    if _wit_status == "WITNESSED" and not _file_ok:
        _received = _wit.get("received_at") or "unknown time"
        content_lines.append(
            f"  [red]- Witness:      a report for this case exists (received {_received}), "
            "but THIS file was altered — it is not what was reported[/red]"
        )
    elif _wit_status == "WITNESSED":
        _received = _wit.get("received_at") or "unknown time"
        if _wit.get("mode") == "verified-receipt":
            content_lines.append(
                f"  [green]- Witness:      WITNESSED — verified witness receipt (received {_received})[/green]"
            )
        else:
            content_lines.append(
                f"  [green]- Witness:      WITNESSED — YOUR OWN LOG (unsigned) (received {_received})[/green]"
            )
            content_lines.append(
                "  [dim]                Trusted only because you kept this log yourself; a file "
                "received from someone else proves nothing.[/dim]"
            )
        if _wit.get("repackaged"):
            content_lines.append(
                "  [dim]                re-packaged after the witness; sealed contents unchanged[/dim]"
            )
    elif _wit_status == "NOT IN WITNESS LOG":
        content_lines.append(
            "  [yellow]- Witness:      NOT IN WITNESS LOG — this file was never reported "
            "to this witness log when it was sealed (re-run or re-sealed copy?)[/yellow]"
        )
    elif _wit_status == "UNREADABLE":
        content_lines.append(
            f"  [red]- Witness:      NOT CHECKED — {_wit.get('detail')}[/red]"
        )
    elif _wit_status == "NOT CONFIRMED":
        content_lines.append(
            f"  [red]- Witness:      STAMP NOT CONFIRMED — {_wit.get('detail')}[/red]"
        )
    elif _wit_status == "MISMATCH":
        content_lines.append(
            f"  [red]- Witness:      DIFFERENT VERSION — {_wit.get('detail')}[/red]"
        )

    # Human approval (step 3a). One line, and only when the run carries reviews
    # or approval steps, or the operator asked with --require-human-approval.
    _human = report.get("human_approval") if isinstance(report, dict) else None
    if isinstance(_human, dict) and (_human.get("present") or _human.get("required")):
        _h_status = str(_human.get("status") or "none").upper()
        _h_color = {
            "VERIFIED": "green",
            "NONE": "dim",
            "UNVERIFIED": "yellow",
            "INCOMPLETE": "yellow",
            "DENIED": "red",
            "FAILED": "red",
        }.get(_h_status, "yellow")
        content_lines.append(
            f"  [{_h_color}]- Human approval: {_h_status} — {_human.get('detail') or ''}[/{_h_color}]"
        )

    # Who signed in when the sealer ran (EPI evidence server, optional sign-in).
    # Read from environment.json, which the file hashes cover, and shown only
    # when integrity and signature both passed.
    if isinstance(report, dict) and report.get("integrity_ok") and report.get("signature_valid"):
        try:
            from zipfile import ZipFile as _Zip

            with _Zip(Path(epi_file), "r") as _zf:
                if "environment.json" in _zf.namelist():
                    _who = (json.loads(_zf.read("environment.json")) or {}).get("sealer_identity") or {}
                    if _who.get("verified") is True:
                        _label = (
                            _who.get("email")
                            or (f"@{_who['username']}" if _who.get("username") else "")
                            or f"account {str(_who.get('account_id', ''))[:8]}"
                        )
                        content_lines.append(
                            f"  - Signed in:    {_label} via {_who.get('verified_by', 'identity provider')} "
                            "[dim](asserted by the sealing server; not proof of who typed the chat)[/dim]"
                        )
        except Exception:
            pass

    # Capture scope details (known gaps etc.) — part of SEAL facts.
    if isinstance(_cap, dict):
        _gaps = _cap.get("known_gaps") or []
        _surfaces = _cap.get("instrumented_surfaces") or []
        _stream = _cap.get("streaming", False)
        content_lines.append(f"  - Capture:      path={_cap.get('capture_path', 'unknown')} streaming={str(_stream).lower()}")
        if _surfaces and verbose:
            # Internal hook names: useful to engineers, noise to reviewers.
            content_lines.append(f"  - Surfaces:     {', '.join([str(s) for s in _surfaces[:6]])}{' …' if len(_surfaces) > 6 else ''}")
        _active = _cap.get("active_surfaces") or []
        if _active:
            content_lines.append(f"  - Active:       {', '.join([str(s) for s in _active[:6]])}{' …' if len(_active) > 6 else ''}")
        else:
            content_lines.append(
                "  - Active:       no auto-captured calls (steps were logged by the program itself)"
            )
        if _gaps:
            content_lines.append(f"  - Known gaps:   {len(_gaps)} declared (not captured by this recording)")
            for _g in _gaps[:3]:
                content_lines.append(f"      · {str(_g)[:100]}")
            if len(_gaps) > 3:
                content_lines.append(f"      · … {len(_gaps) - 3} more (epi verify -v)")

    # Checkpoints — specific messages, never generic alone.
    _cps = report.get("checkpoints") if isinstance(report, dict) else None
    if isinstance(_cps, dict):
        _cp_count = int(_cps.get("count") or 0)
        _cp_ok = bool(_cps.get("ok", True))
        _cp_msgs = list(_cps.get("messages") or [])
        if _cp_count > 0 and _cp_ok:
            content_lines.append(f"  - Checkpoints:  { _cp_count} verified (forward-secure)")
        elif _cp_count > 0:
            content_lines.append(f"  [red]- Checkpoints:  {_cp_count} record(s), ISSUES FOUND[/red]")
            for _m in _cp_msgs[:3]:
                content_lines.append(f"  [red]  {_m}[/red]")
        else:
            content_lines.append("  - Checkpoints:  none (seal-time notarization only)")


    if not chain_ok:
        content_lines.append("  [red]- Chain:        BROKEN (prev_hash mismatch)[/red]")

    # Transparency (SCITT)
    transparency_ok = facts.get("transparency_ok")
    _scitt_url_any = (
        ((report.get("identity") or {}).get("scitt") or {}).get("service_url")
        if isinstance(report, dict) else None
    )
    if transparency_ok is None and str(_scitt_url_any or "").strip().lower() == "local":
        content_lines.append(
            "  [yellow]- Transparency: LOCAL (self-issued receipt; only checkable on the "
            "machine that issued it)[/yellow]"
        )
    if transparency_ok is not None:
        _scitt_url = (
            ((report.get("identity") or {}).get("scitt") or {}).get("service_url")
            if isinstance(report, dict) else None
        )
        if transparency_ok and str(_scitt_url or "").strip().lower() == "local":
            # `epi-register` without --service: a receipt the sealer issued to
            # itself. Valid, but not an independent ledger entry.
            content_lines.append(
                "  [yellow]- Transparency: LOCAL (self-issued receipt, not an independent "
                "ledger)[/yellow]"
            )
        else:
            t_color = "green" if transparency_ok else "red"
            t_text = "VERIFIED" if transparency_ok else "FAILED"
            content_lines.append(f"  [{t_color}]- Transparency: {t_text} (SCITT)[/{t_color}]")

    # AIUC-1 Domain Layer
    aiuc1_data = report.get("aiuc1")
    if aiuc1_data:
        content_lines.append("")
        content_lines.append("[bold underline]EVIDENCE BY AIUC-1 DOMAIN[/bold underline]")
        content_lines.append("[dim]  EPI's own evidence checks, not an AIUC-1 result or certification.[/dim]")
        domains = aiuc1_data.get("domains", {})
        for domain_id in ["A", "B", "C", "D", "E", "F"]:
            domain = domains.get(domain_id)
            if not domain:
                continue
            d_status = domain.get("status", "UNKNOWN")
            d_label = domain.get("label", domain_id)
            d_color = _AIUC1_COLORS.get(d_status, "dim")
            d_text = _AIUC1_WORDS.get(d_status, d_status)
            content_lines.append(f"  [{d_color}]{domain_id}. {d_label}: {d_text}[/{d_color}]")
        overall = aiuc1_data.get("overall", "UNKNOWN")
        o_color = _AIUC1_COLORS.get(overall, "dim")
        o_text = _AIUC1_WORDS.get(overall, overall)
        content_lines.append(f"  [{o_color}]All domains: {o_text}[/{o_color}]")

    if "warnings" in report and report["warnings"]:
        content_lines.append("")
        content_lines.append("[bold yellow]Warnings:[/bold yellow]")
        for w in report["warnings"]:
            content_lines.append(f"  [yellow]![/yellow] {w}")

    # Pin / strict guidance when seal is valid but signer is not org-pinned
    if (
        signature_valid is True
        and id_upper in ("UNKNOWN", "LOCAL", "")
        and decision_status in ("WARN", "PASS")
    ):
        content_lines.append("")
        if id_upper == "LOCAL":
            content_lines.append(
                "[dim]Seal is cryptographically valid. Identity is LOCAL (key on this PC) — "
                "not an org trust pin. A full re-sign forgery also looks like this.[/dim]"
            )
        else:
            content_lines.append(
                "[dim]Seal is cryptographically valid. Identity is not pinned — "
                "anyone can re-sign a rebuilt chain with a fresh key.[/dim]"
            )
        if id_upper == "LOCAL":
            _own = (identity.get("local_key_name") if isinstance(identity, dict) else None) or "default"
            content_lines.append(f"[dim]  Your own key: epi keys trust {_own}[/dim]")
        else:
            content_lines.append(
                "[dim]  Pin the sender's key obtained from them directly — never from this file:[/dim]"
            )
            content_lines.append(
                "[dim]    epi keys trust --from-did did:web:<their-domain> --name <sender>[/dim]"
            )
            content_lines.append(
                "[dim]    epi keys trust <their-key-file> --name <sender>   then compare the "
                "Fingerprint by phone[/dim]"
            )
        content_lines.append(
            f'[dim]  epi verify "{epi_file}" --policy strict[/dim]'
        )
        content_lines.append(
            "[dim]For insurers / claim acceptance: always use --policy strict "
            "(FAIL until org pin).[/dim]"
        )

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
