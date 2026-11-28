"""Operation identity primitives for EPI evidence steps.

An *operation* is one observed execution unit — an LLM call, a tool invocation, an
approval — that begins with a start event and ends with a terminal event.
``epi-operation/v1`` supplies the recorder-owned pairing identity that lets
verification decide whether a recorded lifecycle is complete **without** using
event order as evidence.

Design contract: ``docs/rfcs/operation-identity-and-event-completeness.md``.

Nothing in this module is wired into the recorder or verifier yet; it is the
shared vocabulary both sides use.
"""

from __future__ import annotations

import secrets
from typing import Any

#: Wire-format marker. Bumping this changes which artifacts are audited by
#: operation identity rather than by name matching.
SCHEME = "epi-operation/v1"

ROLE_START = "start"
ROLE_COMMITMENT = "commitment"
ROLE_TERMINAL = "terminal"

#: kind -> (family, role). Event kinds are frozen: ``llm.call`` is a first-class
#: start alias for the LangChain adapter, not a rename of ``llm.request``.
LIFECYCLE: dict[str, tuple[str, str]] = {
    "llm.request": ("llm", ROLE_START),
    "llm.call": ("llm", ROLE_START),
    "llm.pre_commit": ("llm", ROLE_COMMITMENT),
    "llm.response": ("llm", ROLE_TERMINAL),
    "llm.error": ("llm", ROLE_TERMINAL),
    "tool.call": ("tool", ROLE_START),
    "tool.response": ("tool", ROLE_TERMINAL),
    "agent.approval.request": ("approval", ROLE_START),
    "agent.approval.response": ("approval", ROLE_TERMINAL),
}

FAMILIES: tuple[str, ...] = ("llm", "tool", "approval")


def new_group_id() -> str:
    """Identifier stable across observed attempts of one logical operation."""
    return "opg_" + secrets.token_hex(16)


def new_operation_id() -> str:
    """Identifier unique to one observed attempt."""
    return "opo_" + secrets.token_hex(16)


def make_correlation(
    group_id: str,
    operation_id: str,
    attempt: int = 1,
    external_id: str | None = None,
) -> dict[str, Any]:
    """Build a ``content.correlation`` payload.

    ``external_id`` preserves a provider or framework identifier (OpenAI
    ``call_id``, LangChain ``run_id``) for humans and cross-tooling. It is
    explicitly **not** a pairing key under this scheme.
    """
    if attempt < 1:
        raise ValueError("attempt must be a positive integer")
    payload: dict[str, Any] = {
        "scheme": SCHEME,
        "group_id": group_id,
        "operation_id": operation_id,
        "attempt": attempt,
    }
    if external_id:
        payload["external_id"] = str(external_id)
    return payload


def validate_correlation(value: Any) -> dict[str, Any] | None:
    """Return a normalised correlation payload, or ``None`` if unusable.

    Malformed identity is treated as *absent*, never repaired: guessing an
    identifier would reintroduce the defect this scheme exists to remove.
    """
    if not isinstance(value, dict):
        return None
    if value.get("scheme") != SCHEME:
        return None
    group_id = value.get("group_id")
    operation_id = value.get("operation_id")
    if not isinstance(group_id, str) or not group_id:
        return None
    if not isinstance(operation_id, str) or not operation_id:
        return None
    attempt = value.get("attempt", 1)
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        return None
    out: dict[str, Any] = {
        "scheme": SCHEME,
        "group_id": group_id,
        "operation_id": operation_id,
        "attempt": attempt,
    }
    external_id = value.get("external_id")
    if isinstance(external_id, str) and external_id:
        out["external_id"] = external_id
    return out


def classify_step(step: Any) -> tuple[str, str] | None:
    """Map a sealed step to ``(family, role)``, or ``None`` if not audited."""
    if not isinstance(step, dict):
        return None
    kind = step.get("kind")
    if not isinstance(kind, str):
        return None
    return LIFECYCLE.get(kind)
