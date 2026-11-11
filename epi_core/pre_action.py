"""Signed PRE-ACTION approvals: request, response, execution, and audit.

A gated tool does not run until a pinned approver signs *this exact call*.
The request binds the tool and canonical arguments (``args_digest``), a
nonce, an expiry, the redacted argument display and the vendor's context.
The approver signs the request digest. The gate releases the tool only after
verifying that signature, the approver's pin, the digest, the expiry and
single use.

Ordering cannot be proven by the vendor's own hash chain: the vendor writes
that chain. At the moment the gate releases the tool it reports
``epi.approval_executed`` to the customer's witness, so the customer holds
request, response and execution receipts on their own clock. Verification
uses that order when ``--witness-log`` is supplied and labels the hash-chain
fallback as vendor-written.

Limits (docs/KNOWN_LIMITATIONS.md): the gate proves what the gate saw. Code
that calls the tool without the interceptor is not covered, and redacted
argument fields are approved blind.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import time
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

PRE_ACTION_VERSION = "1.0.0"

STEP_REQUEST = "approval.request"
STEP_RESPONSE = "approval.response"
STEP_EXECUTED = "approval.executed"
STEP_BLOCKED = "approval.blocked"
STEP_ARGS_MISMATCH = "approval.args_mismatch"

WITNESS_REQUEST = "epi.approval_request"
WITNESS_RESPONSE = "epi.approval_response"
WITNESS_EXECUTED = "epi.approval_executed"

#: Statuses used by verification.
APPROVED = "approved_before_action"
ACTION_BEFORE_APPROVAL = "action_before_approval"
ACTION_WITHOUT_APPROVAL = "action_without_approval"
DENIED_BUT_EXECUTED = "denied_but_executed"
ARGS_CHANGED = "args_changed_after_approval"
APPROVAL_EXPIRED = "approval_expired"
APPROVAL_REUSED = "approval_reused"
SIGNED_BY_SEALING_KEY = "signed_by_sealing_key"
UNKNOWN_APPROVER = "unknown_approver"
AUTO_APPROVED = "auto_approved"
EXECUTION_NOT_WITNESSED = "execution_not_witnessed"
CHAIN_ONLY = "approved_before_action_hash_chain_only"
NOT_USED = "not_used"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: float | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    return str(value)


def parse_time(value: Any) -> datetime | None:
    try:
        text = str(value or "").replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _canonical(value: Any) -> bytes:
    import rfc8785

    return rfc8785.dumps(value)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def canonicalize(value: Any) -> Any:
    """JSON-safe, deterministic form of tool arguments."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (bytes, bytearray)):
        return {"__bytes_b64__": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, (list, tuple, set)):
        return [canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): canonicalize(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if hasattr(value, "model_dump"):
        try:
            return canonicalize(value.model_dump(mode="json"))
        except Exception:
            pass
    return {"__type__": type(value).__name__, "__repr__": repr(value)[:2000]}


def args_digest(tool: str, arguments: dict[str, Any]) -> str:
    return _digest({"tool": str(tool), "args": canonicalize(arguments or {})})


def _redacted_paths(original: Any, redacted: Any, prefix: str, out: list[str]) -> None:
    if isinstance(original, dict) and isinstance(redacted, dict):
        for key in original:
            child = f"{prefix}.{key}" if prefix else str(key)
            _redacted_paths(original[key], redacted.get(key), child, out)
        return
    if isinstance(original, list) and isinstance(redacted, list):
        for index, item in enumerate(original):
            child = f"{prefix}[{index}]"
            _redacted_paths(item, redacted[index] if index < len(redacted) else None, child, out)
        return
    if original != redacted:
        out.append(prefix or "<root>")


def args_display(arguments: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Canonical args with per-field redaction, plus the hidden field paths.

    Exact non-secret values are visible to the approver; secret fields are
    placeholders and listed in ``redacted_fields`` (approved blind).
    """
    canonical = canonicalize(arguments or {})
    try:
        from epi_core.redactor import get_default_redactor

        redacted, _count = get_default_redactor().redact(canonical)
    except Exception:
        redacted = canonical
    paths: list[str] = []
    try:
        _redacted_paths(canonical, redacted, "", paths)
    except Exception:
        paths = []
    return redacted, sorted(set(paths))


def _request_digest_fields() -> tuple[str, ...]:
    return (
        "version",
        "request_id",
        "nonce",
        "workflow_id",
        "agent_host",
        "tool",
        "args_digest",
        "args_display",
        "redacted_fields",
        "context_digest",
        "vendor_description",
        "release_ref",
        "requested_at",
        "expires_at",
        "producer_public_key",
    )


def request_digest(request: dict[str, Any]) -> str:
    body = {field: request.get(field) for field in _request_digest_fields()}
    return _digest(body)


def build_request(
    *,
    tool: str,
    arguments: dict[str, Any],
    workflow_id: str,
    request_id: str,
    nonce: str,
    timeout_seconds: float,
    rule: dict[str, Any] | None = None,
    release_ref: dict[str, Any] | None = None,
    vendor_description: str | None = None,
    producer_public_key: str | None = None,
) -> dict[str, Any]:
    canonical_args = canonicalize(arguments or {})
    display, redacted_fields = args_display(arguments or {})
    context = {
        "rule_id": (rule or {}).get("rule_id"),
        "rule_name": (rule or {}).get("rule_name"),
        "reason": (rule or {}).get("reason"),
        "release_ref": release_ref,
    }
    requested = time.time()
    request: dict[str, Any] = {
        "version": PRE_ACTION_VERSION,
        "request_id": str(request_id),
        "nonce": str(nonce),
        "workflow_id": str(workflow_id),
        "agent_host": socket.gethostname(),
        "tool": str(tool),
        "args_digest": args_digest(tool, canonical_args),
        "args_display": display,
        "redacted_fields": redacted_fields,
        "context_digest": _digest(context),
        "vendor_description": vendor_description,
        "release_ref": release_ref,
        "requested_at": _iso(requested),
        "expires_at": _iso(requested + max(1.0, float(timeout_seconds))),
        "producer_public_key": producer_public_key,
    }
    request["request_digest"] = request_digest(request)
    return request


def validate_request(request: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(request, dict):
        return False, "request is not a JSON object"
    recomputed = request_digest(request)
    if recomputed != str(request.get("request_digest") or ""):
        return False, "request_digest does not match the request contents"
    if request.get("version") != PRE_ACTION_VERSION:
        return False, f"unsupported pre-action version {request.get('version')!r}"
    if not request.get("args_digest") or not request.get("nonce"):
        return False, "request is missing args_digest or nonce"
    return True, "ok"


def producer_signature_payload(request: dict[str, Any]) -> bytes:
    return bytes.fromhex(str(request.get("request_digest") or ""))


def sign_request(request: dict[str, Any], private_key: Any, key_name: str) -> str:
    signature = private_key.sign(producer_signature_payload(request))
    public_hex = private_key.public_key().public_bytes_raw().hex()
    return f"ed25519:{public_hex}:{signature.hex()}"


def _response_fields() -> tuple[str, ...]:
    return (
        "version",
        "request_id",
        "request_digest",
        "decision",
        "approver",
        "key_fingerprint",
        "public_key",
        "signed_on_host",
        "reason",
        "signed_at",
        "auto",
    )


def response_digest(response: dict[str, Any]) -> str:
    return _digest({field: response.get(field) for field in _response_fields()})


def sign_response(
    request: dict[str, Any],
    *,
    decision: str,
    approver: str,
    key_fingerprint: str,
    public_key: str,
    private_key: Any,
    reason: str | None = None,
    signed_at: str | None = None,
    auto: bool = False,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "version": PRE_ACTION_VERSION,
        "request_id": str(request.get("request_id")),
        "request_digest": str(request.get("request_digest")),
        "decision": str(decision),
        "approver": str(approver),
        "key_fingerprint": str(key_fingerprint),
        "public_key": str(public_key),
        "signed_on_host": socket.gethostname(),
        "reason": str(reason or ""),
        "signed_at": signed_at or _now(),
        "auto": bool(auto),
    }
    if auto:
        response["signature"] = None
        return response
    signature = private_key.sign(bytes.fromhex(response_digest(response)))
    response["signature"] = f"ed25519:{public_key}:{signature.hex()}"
    return response


def verify_response_signature(response: dict[str, Any]) -> tuple[bool, str]:
    signature = str(response.get("signature") or "")
    parts = signature.split(":", 2)
    if len(parts) != 3 or parts[0] != "ed25519":
        return False, "response is not signed (or the signature format is invalid)"
    if len(parts[1]) != 64 or len(parts[2]) != 128:
        return False, "response signature has the wrong length"
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(parts[1]))
        key.verify(bytes.fromhex(parts[2]), bytes.fromhex(response_digest(response)))
        return True, "valid"
    except InvalidSignature:
        return False, "response signature does not match its contents"
    except Exception as exc:
        return False, f"response signature could not be verified ({exc})"


def verify_response(
    request: dict[str, Any],
    response: dict[str, Any],
    *,
    registry: Any = None,
    sealing_key: str | None = None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Full gate-time check. Returns ``(ok, reason)``; reason is user-facing."""
    if not isinstance(response, dict):
        return False, "no approval response"
    if response.get("auto"):
        return False, "auto-approval is not a person"
    if str(response.get("request_id")) != str(request.get("request_id")):
        return False, "response is for a different request"
    if str(response.get("request_digest")) != str(request.get("request_digest")):
        return False, "response does not sign this request digest"
    if str(response.get("decision") or "") != "approve":
        return False, f"approver decision was {response.get('decision')!r}"
    ok, why = verify_response_signature(response)
    if not ok:
        return False, why
    public_key = str(response.get("public_key") or "").lower()
    if not public_key:
        return False, "response has no approver public key"
    if sealing_key and public_key == str(sealing_key).lower():
        return False, "the sealing key cannot approve its own action"
    if registry is None:
        try:
            from epi_core.approvers import ApproverRegistry

            registry = ApproverRegistry()
        except Exception:
            registry = None
    if registry is None or not registry.is_approver(public_key):
        return False, "approver key is not pinned with the approver role"
    expires = parse_time(request.get("expires_at"))
    signed = parse_time(response.get("signed_at"))
    current = now or datetime.now(timezone.utc)
    if expires and current > expires:
        return False, "the approval request expired"
    if expires and signed and signed > expires:
        return False, "the approval was signed after the request expired"
    return True, "ok"


def response_signature_hash(response: dict[str, Any]) -> str:
    return hashlib.sha256(str(response.get("signature") or "").encode("utf-8")).hexdigest()


def find_private_key_on_host(public_key_hex: str, keys_dir: Path | None = None) -> str | None:
    """Name of a local approver key matching this public key, if readable here."""
    try:
        from epi_core.approvers import _resolve_default_approver_keys_dir
        from epi_core.keys import KeyManager

        directory = Path(keys_dir) if keys_dir else _resolve_default_approver_keys_dir()
        km = KeyManager(keys_dir=directory)
        for item in km.list_keys():
            if not item.get("has_private"):
                continue
            try:
                if km.load_public_key(item["name"]).hex().lower() == public_key_hex.lower():
                    return str(item["name"])
            except Exception:
                continue
    except Exception:
        return None
    return None


def _step_content(step: dict[str, Any]) -> dict[str, Any]:
    content = step.get("content")
    return content if isinstance(content, dict) else {}


def _step_kind(step: dict[str, Any]) -> str:
    return str(step.get("kind") or "")


def _find_witness(entries: Iterable[dict[str, Any]], kind: str, request_id: str) -> list[dict[str, Any]]:
    found = [
        entry
        for entry in entries
        if str(entry.get("type") or "") == kind
        and str(entry.get("request_id") or "") == request_id
    ]
    return found


def _earliest_received(entries: list[dict[str, Any]]) -> str | None:
    times = [str(entry.get("received_at") or "") for entry in entries if entry.get("received_at")]
    return min(times) if times else None


def analyze(
    steps: list[dict[str, Any]],
    witness_entries: Iterable[dict[str, Any]] | None = None,
    *,
    registry: Any = None,
    sealing_key: str | None = None,
) -> dict[str, Any]:
    """Verify every pre-action approval recorded in a sealed run.

    ``witness_entries`` are the customer's received reports; when supplied,
    the order is decided by their ``received_at``, never by the vendor chain.
    """
    entries = list(witness_entries or [])
    indexed = list(enumerate(steps or []))
    requests: dict[str, dict[str, Any]] = {}
    responses: dict[str, list[dict[str, Any]]] = {}
    executed: dict[str, list[dict[str, Any]]] = {}
    tool_calls: list[dict[str, Any]] = []

    for index, step in indexed:
        kind = _step_kind(step)
        content = _step_content(step)
        if kind == STEP_REQUEST:
            request_id = str(content.get("request_id") or "")
            if request_id:
                requests[request_id] = {"index": index, "content": content, "step": step}
        elif kind == STEP_RESPONSE:
            request_id = str(content.get("request_id") or "")
            if request_id and isinstance(content.get("response"), dict):
                responses.setdefault(request_id, []).append(
                    {"index": index, "content": content, "step": step}
                )
        elif kind == STEP_EXECUTED:
            request_id = str(content.get("request_id") or "")
            if request_id:
                executed.setdefault(request_id, []).append(
                    {"index": index, "content": content, "step": step}
                )
        elif kind == "tool.call":
            tool_calls.append({"index": index, "content": content, "step": step})

    results: list[dict[str, Any]] = []
    for request_id, item in requests.items():
        request = item["content"]
        request_index = item["index"]
        findings: list[str] = []
        status = APPROVED
        basis = "hash chain only (vendor-written, not independent)"
        independent = False
        response_items = responses.get(request_id) or []
        executed_items = executed.get(request_id) or []

        # --- chain order --------------------------------------------------
        if len(response_items) > 1 or len(executed_items) > 1:
            status = APPROVAL_REUSED
            findings.append("more than one response or execution for this request")
        response_item = response_items[0] if response_items else None
        execution_item = executed_items[0] if executed_items else None
        if response_item is None:
            status = ACTION_WITHOUT_APPROVAL
            findings.append("tool ran without an approval response")
        elif status != APPROVAL_REUSED:
            response = response_item["content"].get("response") or {}
            ok, why = verify_response(
                request,
                response,
                registry=registry,
                sealing_key=sealing_key,
                now=parse_time(response.get("signed_at")),
            )
            if not ok:
                if "auto" in why:
                    status = AUTO_APPROVED
                elif "sealing key" in why:
                    status = SIGNED_BY_SEALING_KEY
                elif "not pinned" in why or "approver role" in why:
                    status = UNKNOWN_APPROVER
                elif "expired" in why:
                    status = APPROVAL_EXPIRED
                elif "decision" in why:
                    status = DENIED_BUT_EXECUTED
                else:
                    status = ACTION_WITHOUT_APPROVAL
                findings.append(why)
            else:
                if response_item["content"].get("approver_key_colocated"):
                    findings.append("approver key is on the agent host (not independent)")
                if execution_item is None:
                    tool_item = next(
                        (
                            call
                            for call in tool_calls
                            if call["index"] > request_index
                            and str(call["content"].get("approval_request_id") or "") == request_id
                        ),
                        None,
                    )
                    execution_item = tool_item
                if execution_item is None:
                    status = ACTION_WITHOUT_APPROVAL
                    findings.append("no execution step follows the approval")
                elif response_item["index"] > execution_item["index"]:
                    status = ACTION_BEFORE_APPROVAL
                    findings.append("the approval response is after the execution in the chain")
                else:
                    expected = str(request.get("args_digest") or "")
                    actual = str(execution_item["content"].get("args_digest") or "")
                    if actual and expected and actual != expected:
                        status = ARGS_CHANGED
                        findings.append("arguments at execution differ from the approved arguments")

        # --- independent order from the customer's witness ---------------
        if response_item is not None:
            witness_request = _find_witness(entries, WITNESS_REQUEST, request_id)
            witness_response = _find_witness(entries, WITNESS_RESPONSE, request_id)
            witness_executed = _find_witness(entries, WITNESS_EXECUTED, request_id)
            if witness_entries is not None:
                if len(witness_executed) > 1:
                    status = APPROVAL_REUSED
                    findings.append("the same approval was executed more than once (witness)")
                elif not witness_executed:
                    if status == APPROVED:
                        status = EXECUTION_NOT_WITNESSED
                    findings.append("witness has no execution receipt for this request")
                elif not witness_response:
                    status = ACTION_BEFORE_APPROVAL
                    findings.append(
                        "the customer received an execution report before any approval report"
                    )
                elif not witness_request:
                    if status == APPROVED:
                        status = EXECUTION_NOT_WITNESSED
                    findings.append("witness has no request receipt for this approval")
                else:
                    req_time = _earliest_received(witness_request)
                    resp_time = _earliest_received(witness_response)
                    exe_time = _earliest_received(witness_executed)
                    basis = "witness received_at (independent)"
                    independent = True
                    if req_time and resp_time and exe_time:
                        if exe_time < resp_time:
                            status = ACTION_BEFORE_APPROVAL
                            findings.append(
                                "the customer received the execution report before the approval"
                            )
                        elif resp_time < req_time:
                            status = ACTION_BEFORE_APPROVAL
                            findings.append(
                                "the customer received the approval before the request"
                            )
                        else:
                            basis = "witness received_at (independent)"
                            independent = True

        if status == APPROVED and response_item is not None:
            # Independent order is required for a clean finding; without it the
            # result stays APPROVED but is labelled vendor-chain-only by the
            # formatter (and does not satisfy --require-pre-action-approval).
            pass

        results.append(
            {
                "request_id": request_id,
                "tool": request.get("tool"),
                "status": status,
                "basis": basis,
                "independent": independent,
                "approver": (
                    (response_item["content"].get("response") or {}).get("approver")
                    if response_item
                    else None
                ),
                "approver_public_key": (
                    (response_item["content"].get("response") or {}).get("public_key")
                    if response_item
                    else None
                ),
                "approver_key_colocated": bool(
                    response_item["content"].get("approver_key_colocated")
                    if response_item
                    else False
                ),
                "request_index": request_index,
                "response_index": response_item["index"] if response_item else None,
                "execution_index": execution_item["index"] if execution_item else None,
                "findings": findings,
            }
        )

    problems = [
        item for item in results if item["status"] not in (APPROVED, CHAIN_ONLY)
    ]
    return {
        "status": "not_used" if not results else ("ok" if not problems else "problems"),
        "requests": results,
        "problems": len(problems),
        "independent": any(item["independent"] for item in results),
        "witness_checked": witness_entries is not None,
    }
