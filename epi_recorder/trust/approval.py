"""ApprovalGate — async pause/resume, now with signed PRE-ACTION approval.

The old in-memory gate is still here (``request`` / ``resolve`` / ``wait_for``)
for existing callers. The signed path is ``request_signed`` (sync tool) or
``async_request_signed`` (async tool): it builds a request that binds the tool,
canonical arguments, nonce and expiry, lets a pinned approver sign that exact
request from another machine, verifies the response, and returns a grant whose
``release`` must be called immediately before the tool runs.

Ordering is anchored by the customer's witness: ``release`` reports
``epi.approval_executed`` before the tool runs. The vendor's hash chain alone
is labelled as vendor-written by verification.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("epi.approval")

_LOCAL_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def auto_approve_enabled() -> bool:
    return os.environ.get("EPI_AUTO_APPROVE", "0") == "1"


def warn_auto_approve() -> None:
    if auto_approve_enabled():
        message = (
            "EPI_AUTO_APPROVE=1: approvals are recorded as 'auto (not a person)' "
            "and never count as human. Use only for tests/dev."
        )
        logger.warning(message)
        print(f"[EPI] WARNING: {message}", file=sys.stderr)


@dataclass
class ApprovalTicket:
    """A pending approval request."""

    ticket_id: str
    action: str
    reason: str
    requested_at: float
    timeout_seconds: int
    context: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, approved, denied, expired
    reviewer: Optional[str] = None
    reviewed_at: Optional[float] = None
    notes: Optional[str] = None
    request_id: Optional[str] = None
    nonce: Optional[str] = None
    tool: Optional[str] = None
    args_digest: Optional[str] = None
    request_digest: Optional[str] = None
    expires_at: Optional[str] = None
    args_display: Optional[dict] = None
    redacted_fields: Optional[list] = None

    @property
    def is_expired(self) -> bool:
        if self.status != "pending":
            return False
        return time.time() - self.requested_at > self.timeout_seconds

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "action": self.action,
            "reason": self.reason,
            "status": self.status,
            "requested_at": self.requested_at,
            "timeout_seconds": self.timeout_seconds,
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at,
            "notes": self.notes,
            "context": self.context,
            "request_id": self.request_id,
            "nonce": self.nonce,
            "tool": self.tool,
            "args_digest": self.args_digest,
            "request_digest": self.request_digest,
            "expires_at": self.expires_at,
        }


class ApprovalRequiredError(Exception):
    """Raised when an action requires approval and no auto-approval is configured."""

    def __init__(self, ticket: ApprovalTicket):
        self.ticket = ticket
        super().__init__(
            f"Approval required for action '{ticket.action}' (ticket: {ticket.ticket_id}). "
            f"Reason: {ticket.reason}"
        )


class PreActionApprovalBlocked(Exception):
    """A pre-action approval did not unlock the gate; the tool must not run."""

    def __init__(self, request: dict | None, reason: str):
        self.request = request or {}
        self.reason = str(reason)
        super().__init__(f"Pre-action approval blocked: {self.reason}")


def _inbox_dir() -> Path:
    override = os.environ.get("EPI_APPROVAL_INBOX_DIR")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("EPI_HOME")
    if base:
        return Path(base).expanduser() / "approvals" / "inbox"
    return Path.home() / ".epi" / "approvals" / "inbox"


def _used_nonce_path() -> Path:
    return _inbox_dir().parent / "used_nonces.json"


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _nonce_used(request_id: str, nonce: str) -> bool:
    state = _read_json(_used_nonce_path()) or {}
    return f"{request_id}:{nonce}" in (state.get("used") or {})


def _mark_nonce_used(request_id: str, nonce: str) -> None:
    from epi_core.filelock import FileLock

    path = _used_nonce_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _LOCAL_LOCK, FileLock(path, timeout=10.0):
            state = _read_json(path) or {"used": {}}
            used = dict(state.get("used") or {})
            used[f"{request_id}:{nonce}"] = _now()
            if len(used) > 5000:
                # Bounded: keep the newest by ISO timestamp.
                used = dict(sorted(used.items(), key=lambda item: item[1])[-5000:])
            state["used"] = used
            _write_json(path, state)
    except Exception as exc:
        logger.warning("Could not record used approval nonce: %s", exc)


@dataclass
class PreActionGrant:
    gate: "ApprovalGate"
    request: dict
    response: dict
    tool: str
    released: bool = False

    def release(self, arguments: dict[str, Any] | None = None) -> None:
        """Log and witness the execution, then let the caller run the tool."""
        from epi_core.pre_action import (
            args_digest,
            response_signature_hash,
        )

        if self.released:
            raise PreActionApprovalBlocked(self.request, "this approval was already released")
        actual = args_digest(self.tool, arguments or {})
        expected = str(self.request.get("args_digest") or "")
        if actual != expected:
            self.gate._record_step(
                "approval.args_mismatch",
                {
                    "request_id": self.request.get("request_id"),
                    "expected_args_digest": expected,
                    "actual_args_digest": actual,
                    "tool": self.tool,
                },
            )
            raise PreActionApprovalBlocked(
                self.request, "the arguments changed after approval"
            )
        if not self.response.get("auto"):
            if _nonce_used(str(self.request.get("request_id")), str(self.request.get("nonce"))):
                self.gate._record_step(
                    "approval.blocked",
                    {
                        "request_id": self.request.get("request_id"),
                        "reason": "approval reused",
                    },
                )
                raise PreActionApprovalBlocked(self.request, "this approval was already used")
            _mark_nonce_used(str(self.request.get("request_id")), str(self.request.get("nonce")))
        self.gate._record_step(
            "approval.executed",
            {
                "request_id": self.request.get("request_id"),
                "tool": self.tool,
                "args_digest": expected,
                "response_signature_hash": response_signature_hash(self.response),
                "executed_at": _now(),
                "auto": bool(self.response.get("auto")),
            },
        )
        chain_head = self.gate._chain_head()
        self.gate._report_executed(
            self.request,
            self.response,
            chain_head=chain_head,
        )
        self.released = True


class ApprovalGate:
    """Manages approval requests and responses for agent actions."""

    def __init__(
        self,
        *,
        auto_approve_after_timeout: bool = False,
        default_timeout: int = 300,
        webhook_url: Optional[str] = None,
        inbox_dir: Path | str | None = None,
        registry: Any | None = None,
        witness_url: str | None = None,
        witness_secret: str | None = None,
        signer: Any | None = None,
        signer_name: str | None = None,
        sealing_key: str | None = None,
        step_sink: Any | None = None,
        delivery_timeout: float = 2.0,
        workflow_id: str | None = None,
    ):
        self.auto_approve_after_timeout = auto_approve_after_timeout
        self.default_timeout = default_timeout
        self.webhook_url = webhook_url
        self._inbox = Path(inbox_dir) if inbox_dir else _inbox_dir()
        self._registry = registry
        self.witness_url = witness_url
        self.witness_secret = witness_secret
        self.signer = signer
        self.signer_name = signer_name
        self.sealing_key = sealing_key
        self._step_sink = step_sink
        self.delivery_timeout = max(0.0, float(delivery_timeout))
        self.workflow_id = workflow_id

        self._tickets: Dict[str, ApprovalTicket] = {}
        self._events: Dict[str, asyncio.Event] = {}
        self._on_request: Optional[Callable[[ApprovalTicket], Any]] = None
        self._warned_no_sink = False

    def set_on_request(self, callback: Callable[[ApprovalTicket], Any] | None) -> None:
        self._on_request = callback

    # ------------------------------------------------------------------
    # Old in-memory API (unchanged behaviour)
    # ------------------------------------------------------------------

    async def request(
        self,
        action: str,
        *,
        reason: str = "",
        timeout: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        ticket = ApprovalTicket(
            ticket_id=f"apr_{uuid.uuid4().hex[:16]}",
            action=action,
            reason=reason,
            requested_at=time.time(),
            timeout_seconds=timeout or self.default_timeout,
            context=context or {},
        )
        self._tickets[ticket.ticket_id] = ticket
        event = asyncio.Event()
        self._events[ticket.ticket_id] = event
        if self._on_request:
            try:
                self._on_request(ticket)
            except Exception:
                pass
        if auto_approve_enabled():
            warn_auto_approve()
            self.resolve(ticket.ticket_id, approved=True, reviewer="auto")
            return True
        try:
            await asyncio.wait_for(event.wait(), timeout=ticket.timeout_seconds)
        except asyncio.TimeoutError:
            ticket.status = "expired"
            if self.auto_approve_after_timeout:
                ticket.status = "approved"
                ticket.reviewer = "auto_timeout"
                ticket.reviewed_at = time.time()
                return True
            return False
        ticket = self._tickets.get(ticket.ticket_id)
        return bool(ticket and ticket.status == "approved")

    def resolve(
        self,
        ticket_id: str,
        *,
        approved: bool,
        reviewer: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        ticket = self._tickets.get(ticket_id)
        if ticket is None or ticket.status != "pending":
            return False
        ticket.status = "approved" if approved else "denied"
        ticket.reviewer = reviewer or "unknown"
        ticket.reviewed_at = time.time()
        ticket.notes = notes
        event = self._events.pop(ticket_id, None)
        if event:
            event.set()
        return True

    async def wait_for(self, ticket_id: str, *, timeout: Optional[int] = None) -> bool:
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            return False
        if ticket.status != "pending":
            return ticket.status == "approved"
        event = self._events.get(ticket_id)
        if event is None:
            event = asyncio.Event()
            self._events[ticket_id] = event
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout or ticket.timeout_seconds)
        except asyncio.TimeoutError:
            pass
        ticket = self._tickets.get(ticket_id)
        return bool(ticket and ticket.status == "approved")

    def get_ticket(self, ticket_id: str) -> Optional[ApprovalTicket]:
        return self._tickets.get(ticket_id)

    def list_pending(self) -> list[ApprovalTicket]:
        return [t for t in self._tickets.values() if t.status == "pending" and not t.is_expired]

    # ------------------------------------------------------------------
    # Signed pre-action path
    # ------------------------------------------------------------------

    def _sink(self):
        if self._step_sink is not None:
            return self._step_sink
        from epi_recorder.trust.context import current_step_sink

        return current_step_sink()

    def _warn_no_sink(self) -> None:
        message = (
            "pre-action approval has no recording session: request/response/"
            "execution saved to the approvals inbox and witnessed, but not "
            "sealed into a run. Use contextvars.copy_context() in a thread pool."
        )
        logger.warning(message)
        print(f"[EPI] WARNING: {message}", file=sys.stderr)

    def _record_step(self, kind: str, content: dict) -> None:
        sink = self._sink()
        if sink is not None:
            try:
                writer = getattr(sink, "log_step_unredacted", None)
                if callable(writer):
                    writer(kind, content)
                else:
                    sink.log_step(kind, content)
                return
            except Exception as exc:
                logger.warning("Could not record %s step: %s", kind, exc)
        self._warn_no_sink()
        request_id = str(content.get("request_id") or "unknown")
        try:
            _write_json(self._inbox / f"{request_id}.{kind.replace('.', '_')}.json", content)
        except Exception:
            pass

    def _chain_head(self) -> str | None:
        sink = self._sink()
        if sink is None:
            return None
        try:
            return sink.chain_head()
        except Exception:
            return None

    def _targets(self) -> list[str]:
        from epi_core.webhook import split_witness_urls

        if self.witness_url:
            return split_witness_urls(self.witness_url)
        return split_witness_urls(os.environ.get("EPI_WITNESS_URL"))

    def _secret(self) -> str | None:
        if self.witness_secret is not None:
            return self.witness_secret
        return os.environ.get("EPI_WITNESS_SECRET")

    def _producer_signature(self, request: dict) -> None:
        if self.signer is None:
            return
        try:
            from epi_core.pre_action import sign_request

            public_hex = self.signer.public_key().public_bytes_raw().hex()
            request["producer_public_key"] = public_hex
            request["producer_signature"] = sign_request(
                request, self.signer, self.signer_name or "default"
            )
        except Exception as exc:
            logger.warning("Could not sign approval request: %s", exc)

    def _report_request(self, request: dict) -> None:
        try:
            from epi_core.webhook import report_approval_request

            report_approval_request(
                request,
                urls=self._targets(),
                secret=self._secret(),
                signer=self.signer,
                key_name=self.signer_name,
                timeout_seconds=self.delivery_timeout,
            )
        except Exception as exc:
            logger.warning("Approval request witness failed: %s", exc)

    def _report_response(self, request: dict, response: dict) -> None:
        try:
            from epi_core.webhook import report_approval_response

            report_approval_response(
                request,
                response,
                urls=self._targets(),
                secret=self._secret(),
                timeout_seconds=self.delivery_timeout,
            )
        except Exception as exc:
            logger.warning("Approval response witness failed: %s", exc)

    def _report_executed(self, request: dict, response: dict, *, chain_head: str | None) -> None:
        try:
            from epi_core.webhook import report_approval_executed

            report_approval_executed(
                request,
                response,
                chain_head=chain_head,
                urls=self._targets(),
                secret=self._secret(),
                timeout_seconds=self.delivery_timeout,
            )
        except Exception as exc:
            logger.warning("Approval execution witness failed: %s", exc)

    def _prepare(
        self,
        *,
        tool: str,
        arguments: dict[str, Any],
        rule: dict[str, Any] | None,
        release_ref: dict[str, Any] | None,
        timeout: float | None,
        workflow_id: str | None,
        vendor_description: str | None,
    ) -> dict[str, Any]:
        from epi_core.pre_action import build_request

        request = build_request(
            tool=tool,
            arguments=arguments,
            workflow_id=workflow_id or self.workflow_id or "workflow",
            request_id=f"aprq_{uuid.uuid4().hex[:16]}",
            nonce=secrets.token_hex(16),
            timeout_seconds=timeout or self.default_timeout,
            rule=rule,
            release_ref=release_ref,
            vendor_description=vendor_description,
        )
        self._producer_signature(request)
        _write_json(self._inbox / f"{request['request_id']}.request.json", request)
        self._record_step("approval.request", dict(request))
        self._report_request(request)
        return request

    def _response_path(self, request: dict) -> Path:
        return self._inbox / f"{request.get('request_id')}.response.json"

    def _accept(self, request: dict, response: dict) -> PreActionGrant:
        from epi_core.pre_action import find_private_key_on_host, verify_response

        sealing_key = self.sealing_key
        if not sealing_key:
            try:
                from epi_core.keys import KeyManager

                sealing_key = KeyManager().load_public_key(
                    os.environ.get("EPI_KEY_NAME", "default")
                ).hex()
            except Exception:
                sealing_key = None
        ok, why = verify_response(
            request,
            response,
            registry=self._registry,
            sealing_key=sealing_key,
        )
        colocated = bool(
            find_private_key_on_host(str(response.get("public_key") or ""))
        )
        step_content = {
            "request_id": request.get("request_id"),
            "request_digest": request.get("request_digest"),
            "response": response,
            "valid": bool(ok),
            "error": None if ok else why,
            "approver_key_colocated": colocated,
        }
        self._record_step("approval.response", step_content)
        self._report_response(request, response)
        if not ok:
            self._record_step(
                "approval.blocked",
                {
                    "request_id": request.get("request_id"),
                    "reason": why,
                },
            )
            raise PreActionApprovalBlocked(request, why)
        if str(response.get("decision") or "") != "approve":
            self._record_step(
                "approval.blocked",
                {
                    "request_id": request.get("request_id"),
                    "reason": f"approver decision was {response.get('decision')!r}",
                },
            )
            raise PreActionApprovalBlocked(request, "the approver denied this action")
        return PreActionGrant(
            gate=self,
            request=request,
            response=response,
            tool=str(request.get("tool") or ""),
        )

    def _auto_grant(self, request: dict) -> PreActionGrant:
        from epi_core.pre_action import sign_response

        warn_auto_approve()
        response = sign_response(
            request,
            decision="approve",
            approver="auto (not a person)",
            key_fingerprint="",
            public_key="",
            private_key=None,
            auto=True,
        )
        self._record_step(
            "approval.response",
            {
                "request_id": request.get("request_id"),
                "request_digest": request.get("request_digest"),
                "response": response,
                "valid": True,
                "approver_key_colocated": False,
                "auto": True,
            },
        )
        self._report_response(request, response)
        return PreActionGrant(
            gate=self,
            request=request,
            response=response,
            tool=str(request.get("tool") or ""),
        )

    def request_signed(
        self,
        *,
        tool: str,
        arguments: dict[str, Any],
        reason: str = "",
        timeout: float | None = None,
        rule: dict[str, Any] | None = None,
        release_ref: dict[str, Any] | None = None,
        workflow_id: str | None = None,
        vendor_description: str | None = None,
    ) -> PreActionGrant:
        """Block until a pinned approver signs this exact call (sync tools)."""
        request = self._prepare(
            tool=tool,
            arguments=arguments,
            rule=rule,
            release_ref=release_ref,
            timeout=timeout,
            workflow_id=workflow_id,
            vendor_description=vendor_description or (reason or None),
        )
        if auto_approve_enabled():
            return self._auto_grant(request)

        response_path = self._response_path(request)
        deadline = datetime.fromisoformat(str(request["expires_at"]).replace("Z", "+00:00"))
        while datetime.now(timezone.utc) <= deadline:
            if response_path.is_file():
                response = _read_json(response_path)
                if response is not None:
                    return self._accept(request, response)
            time.sleep(0.5)
        self._record_step(
            "approval.blocked",
            {
                "request_id": request.get("request_id"),
                "reason": "expired before a response arrived",
            },
        )
        raise PreActionApprovalBlocked(request, "the approval request expired")

    async def async_request_signed(
        self,
        *,
        tool: str,
        arguments: dict[str, Any],
        reason: str = "",
        timeout: float | None = None,
        rule: dict[str, Any] | None = None,
        release_ref: dict[str, Any] | None = None,
        workflow_id: str | None = None,
        vendor_description: str | None = None,
    ) -> PreActionGrant:
        """Async variant: waits without blocking the event loop."""
        request = self._prepare(
            tool=tool,
            arguments=arguments,
            rule=rule,
            release_ref=release_ref,
            timeout=timeout,
            workflow_id=workflow_id,
            vendor_description=vendor_description or (reason or None),
        )
        if auto_approve_enabled():
            return self._auto_grant(request)

        response_path = self._response_path(request)
        deadline = datetime.fromisoformat(str(request["expires_at"]).replace("Z", "+00:00"))
        while datetime.now(timezone.utc) <= deadline:
            if response_path.is_file():
                response = _read_json(response_path)
                if response is not None:
                    return self._accept(request, response)
            await asyncio.sleep(0.5)
        self._record_step(
            "approval.blocked",
            {
                "request_id": request.get("request_id"),
                "reason": "expired before a response arrived",
            },
        )
        raise PreActionApprovalBlocked(request, "the approval request expired")
