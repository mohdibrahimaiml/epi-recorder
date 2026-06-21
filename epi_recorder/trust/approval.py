"""
ApprovalGate — Async pause/resume mechanism for human-in-the-loop approval.

Halts agent execution until a human reviewer approves or denies an action.
Works via asyncio.Event() for local agents, with webhook callback support
for external approval systems.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


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
        }


class ApprovalRequiredError(Exception):
    """Raised when an action requires approval and no auto-approval is configured."""

    def __init__(self, ticket: ApprovalTicket):
        self.ticket = ticket
        super().__init__(
            f"Approval required for action '{ticket.action}' (ticket: {ticket.ticket_id}). "
            f"Reason: {ticket.reason}"
        )


class ApprovalGate:
    """
    Manages approval requests and responses for agent actions.

    Usage:
        gate = ApprovalGate(auto_approve_after_timeout=False)

        try:
            approved = await gate.request(
                action="refund_customer",
                reason="Refund amount $5000 exceeds threshold",
                timeout=300,
            )
        except ApprovalRequiredError as exc:
            # Agent must handle this — pause, notify human, wait for callback
            ticket = exc.ticket
            # ... send to dashboard, wait for webhook ...
            approved = await gate.wait_for(ticket.ticket_id, timeout=300)
    """

    def __init__(
        self,
        *,
        auto_approve_after_timeout: bool = False,
        default_timeout: int = 300,
        webhook_url: Optional[str] = None,
    ):
        self.auto_approve_after_timeout = auto_approve_after_timeout
        self.default_timeout = default_timeout
        self.webhook_url = webhook_url

        # Active tickets indexed by ticket_id
        self._tickets: Dict[str, ApprovalTicket] = {}
        # Events to signal when tickets are resolved
        self._events: Dict[str, asyncio.Event] = {}

        # Optional callback for when tickets are created
        self._on_request: Optional[Callable[[ApprovalTicket], Any]] = None

    def set_on_request(self, callback: Callable[[ApprovalTicket], Any] | None) -> None:
        """Set a callback invoked whenever a new approval is requested."""
        self._on_request = callback

    async def request(
        self,
        action: str,
        *,
        reason: str = "",
        timeout: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Request approval for an action.

        Args:
            action: The action being requested (e.g., "refund_customer").
            reason: Human-readable explanation of why approval is needed.
            timeout: Seconds to wait before auto-expiring. None = default.
            context: Additional context for the reviewer.

        Returns:
            True if approved, False if denied.

        Raises:
            ApprovalRequiredError: If the gate is configured to not auto-approve
                                   and the caller should handle the async wait.
        """
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

        # Notify external system if configured
        if self._on_request:
            try:
                self._on_request(ticket)
            except Exception:
                pass  # Notification failure should not block

        # Check for EPI_AUTO_APPROVE env (development/testing convenience)
        if os.environ.get("EPI_AUTO_APPROVE", "0") == "1":
            self.resolve(ticket.ticket_id, approved=True, reviewer="auto")
            return True

        # Wait for resolution
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

        # Check final status
        ticket = self._tickets.get(ticket.ticket_id)
        if ticket is None:
            return False
        return ticket.status == "approved"

    def resolve(
        self,
        ticket_id: str,
        *,
        approved: bool,
        reviewer: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Resolve an approval ticket (called by webhook/dashboard/human reviewer).

        Args:
            ticket_id: The ticket to resolve.
            approved: True to approve, False to deny.
            reviewer: Identity of the reviewer.
            notes: Optional review notes.

        Returns:
            True if the ticket was found and resolved.
        """
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            return False

        if ticket.status != "pending":
            return False

        ticket.status = "approved" if approved else "denied"
        ticket.reviewer = reviewer or "unknown"
        ticket.reviewed_at = time.time()
        ticket.notes = notes

        # Signal any waiting coroutine
        event = self._events.pop(ticket_id, None)
        if event:
            event.set()

        return True

    async def wait_for(self, ticket_id: str, *, timeout: Optional[int] = None) -> bool:
        """
        Wait for an existing ticket to be resolved.

        Args:
            ticket_id: The ticket to wait for.
            timeout: Max seconds to wait.

        Returns:
            True if approved, False if denied or expired.
        """
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
        if ticket is None:
            return False
        return ticket.status == "approved"

    def get_ticket(self, ticket_id: str) -> Optional[ApprovalTicket]:
        """Get a ticket by ID."""
        return self._tickets.get(ticket_id)

    def list_pending(self) -> list[ApprovalTicket]:
        """List all pending tickets."""
        return [t for t in self._tickets.values() if t.status == "pending" and not t.is_expired]
