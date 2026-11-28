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


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------

STATUS_COMPLETE = "complete"
STATUS_INCOMPLETE = "incomplete"
STATUS_UNKNOWN = "consistent_scope_unknown"
STATUS_NO_EVENTS = "no_observed_lifecycle_events"

BASIS_OPERATION = "operation_identity"
BASIS_NAME = "name_based"

FINDING_KEYS: tuple[str, ...] = (
    "missing_terminals",
    "orphan_terminals",
    "duplicate_operations",
    "duplicate_terminals",
    "unresolved_commitments",
    "unbound_commitments",
    "ambiguous_correlations",
    "family_mismatches",
    "ungoverned_steps",
)

_ROLE_BUCKET = {
    ROLE_START: "starts",
    ROLE_COMMITMENT: "commits",
    ROLE_TERMINAL: "terminals",
}


def _content(step: dict) -> dict:
    content = step.get("content")
    return content if isinstance(content, dict) else {}


def _step_index(step: dict, position: int) -> int:
    index = step.get("index")
    if isinstance(index, int) and not isinstance(index, bool):
        return index
    return position


def _legacy_key(step: dict, content: dict, family: str) -> str | None:
    """The only fields a pre-``epi-operation/v1`` artifact may pair on.

    Tools fall back to the tool name: legacy records frequently carry no
    ``call_id``, and the analyzer already pairs on the name. Ambiguous repeats
    of one name are reported, never resolved by order.
    """
    if family == "tool":
        value = content.get("call_id")
        if value in (None, ""):
            value = content.get("tool")
    elif family == "llm":
        value = step.get("span_id")
        if value in (None, ""):
            value = content.get("span_id")
        if value in (None, ""):
            value = content.get("call_id")
    else:
        value = content.get("action")
    if value is None or value == "":
        return None
    return str(value)


def _record(step: dict, position: int, family: str, role: str) -> dict:
    content = _content(step)
    return {
        "pos": position,
        "index": _step_index(step, position),
        "family": family,
        "role": role,
        "kind": step.get("kind"),
        "content": content,
        "corr": validate_correlation(content.get("correlation")),
        "key": _legacy_key(step, content, family),
    }


def _finding(record: dict, **extra: Any) -> dict:
    entry = {
        "family": record["family"],
        "kind": record["kind"],
        "index": record["index"],
    }
    corr = record.get("corr")
    if isinstance(corr, dict):
        entry["operation_id"] = corr["operation_id"]
        entry["group_id"] = corr["group_id"]
        entry["attempt"] = corr["attempt"]
    entry.update(extra)
    return entry


def _approval_answered(record: dict, answered: set[str], case_level: bool) -> bool:
    if record["family"] != "approval":
        return False
    if case_level:
        return True
    approval_id = record["content"].get("approval_id")
    return approval_id is not None and str(approval_id) in answered


def _missing_message(record: dict) -> str:
    step = record["index"] + 1
    if record["family"] == "tool":
        return f"tool.call at step {step} is missing a corresponding tool.response"
    if record["family"] == "llm":
        return (
            f"{record['kind']} at step {step} is missing a corresponding "
            "response or error"
        )
    action = record["content"].get("action")
    return (
        f"agent.approval.request for '{action}' at step {step} "
        "is missing a response"
    )


def _commit_message(record: dict) -> str:
    step = record["index"] + 1
    return (
        f"llm.pre_commit at step {step} was committed but never executed — "
        "response never arrived (crash, timeout, or cancellation)"
    )


def _audit_governed(
    family_records: list[dict],
    mismatch_ops: set[str],
    answered: set[str],
    case_level: bool,
    findings: dict[str, list],
    gaps: list[str],
) -> tuple[int, int, int, str]:
    """Audit one family whose producers emit ``epi-operation/v1`` identity."""
    ops: dict[str, dict[str, list]] = {}
    order: list[str] = []
    incomplete = False
    started = 0

    for record in family_records:
        if record["role"] == ROLE_START:
            started += 1
        corr = record["corr"]
        if corr is None:
            findings["ungoverned_steps"].append(_finding(record))
            gaps.append(
                f"{record['kind']} at step {record['index'] + 1} has no "
                "epi-operation correlation in a family that is otherwise "
                "correlated"
            )
            incomplete = True
            continue
        operation_id = corr["operation_id"]
        if operation_id not in ops:
            ops[operation_id] = {"starts": [], "commits": [], "terminals": []}
            order.append(operation_id)
        ops[operation_id][_ROLE_BUCKET[record["role"]]].append(record)

    completed = 0
    orphaned = 0

    for operation_id in order:
        entry = ops[operation_id]
        starts = entry["starts"]
        commits = entry["commits"]
        terminals = entry["terminals"]

        if operation_id in mismatch_ops:
            # Already reported as a family mismatch; fail closed.
            incomplete = True
            continue

        if len(starts) > 1:
            for record in starts[1:]:
                findings["duplicate_operations"].append(
                    _finding(record, operation_id=operation_id)
                )
            gaps.append(f"operation '{operation_id}' starts more than once")
            incomplete = True

        if len(terminals) > 1:
            for record in terminals[1:]:
                findings["duplicate_terminals"].append(
                    _finding(record, operation_id=operation_id)
                )
            gaps.append(f"operation '{operation_id}' has more than one terminal event")
            incomplete = True

        if terminals:
            completed += 1
            continue

        if not starts:
            orphaned += 0
            for record in commits:
                findings["unbound_commitments"].append(
                    _finding(record, operation_id=operation_id)
                )
                gaps.append(
                    f"llm.pre_commit at step {record['index'] + 1} has no "
                    "matching operation start"
                )
                incomplete = True
            continue

        for record in starts:
            if _approval_answered(record, answered, case_level):
                continue
            findings["missing_terminals"].append(
                _finding(record, operation_id=operation_id)
            )
            gaps.append(_missing_message(record))
            incomplete = True

        for record in commits:
            findings["unresolved_commitments"].append(
                _finding(record, operation_id=operation_id)
            )
            gaps.append(_commit_message(record))
            incomplete = True

    for operation_id in order:
        entry = ops[operation_id]
        if entry["terminals"] and not entry["starts"]:
            orphaned += len(entry["terminals"])
            for record in entry["terminals"]:
                findings["orphan_terminals"].append(
                    _finding(record, operation_id=operation_id)
                )
                gaps.append(
                    f"{record['kind']} at step {record['index'] + 1} has no "
                    "matching operation start"
                )
                incomplete = True

    status = STATUS_INCOMPLETE if incomplete else STATUS_COMPLETE
    return started, completed, orphaned, status


def _audit_legacy(
    family_records: list[dict],
    answered: set[str],
    case_level: bool,
    findings: dict[str, list],
    gaps: list[str],
    warnings: list[str],
) -> tuple[int, int, int, str]:
    """Audit one family that predates ``epi-operation/v1``.

    Pairing uses only a *unique* ``call_id`` / ``span_id`` / ``action``.
    Event order is never used as evidence. Ambiguity consumes nothing and is
    reported as a warning, never as a proven gap: a start may have been
    discharged by a terminal we cannot attribute.
    """
    starts = [r for r in family_records if r["role"] == ROLE_START]
    terminals = [r for r in family_records if r["role"] == ROLE_TERMINAL]
    paired: set[int] = set()
    ambiguous = 0
    orphaned = 0

    for terminal in terminals:
        key = terminal["key"]
        if key is None:
            ambiguous += 1
            findings["ambiguous_correlations"].append(
                _finding(terminal, reason="no_pairing_identity")
            )
            warnings.append(
                f"{terminal['kind']} at step {terminal['index'] + 1} cannot be "
                "matched: no call_id/span_id/action"
            )
            continue

        candidates = [
            start
            for start in starts
            if start["pos"] not in paired and start["key"] == key
        ]

        if len(candidates) == 1:
            paired.add(candidates[0]["pos"])
        elif not candidates:
            orphaned += 1
            findings["orphan_terminals"].append(_finding(terminal))
            warnings.append(
                f"{terminal['kind']} at step {terminal['index'] + 1} has no "
                "matching start event"
            )
        else:
            ambiguous += 1
            findings["ambiguous_correlations"].append(
                _finding(terminal, reason="multiple_candidates")
            )
            warnings.append(
                f"{terminal['kind']} at step {terminal['index'] + 1} matches "
                f"{len(candidates)} pending operations; left unmatched"
            )

    unpaired = [
        start
        for start in starts
        if start["pos"] not in paired
        and not _approval_answered(start, answered, case_level)
    ]

    if ambiguous:
        for start in unpaired:
            findings["missing_terminals"].append(
                _finding(start, ambiguous_family=True)
            )
            warnings.append(_missing_message(start))
        return len(starts), len(paired), orphaned, STATUS_UNKNOWN

    for start in unpaired:
        findings["missing_terminals"].append(_finding(start))
        gaps.append(_missing_message(start))

    # A pre-commit with no terminal at all is "committed but never executed".
    # Only reported when the family has no terminal events: with terminals
    # present the commitment cannot be attributed without operation identity.
    commits = [r for r in family_records if r["role"] == ROLE_COMMITMENT]
    if not terminals:
        for commit in commits:
            findings["unresolved_commitments"].append(_finding(commit))
            gaps.append(_commit_message(commit))
        if commits:
            return len(starts), len(paired), orphaned, STATUS_INCOMPLETE

    status = STATUS_INCOMPLETE if unpaired else STATUS_UNKNOWN
    return len(starts), len(paired), orphaned, status


def audit_event_sequence(
    steps: list[dict] | None,
    answered_approval_ids: set[str] | None = None,
    case_level_answered: bool = False,
) -> dict[str, Any]:
    """Audit operation lifecycles without ever using event order as evidence.

    Returns the ``facts.event_audit`` payload described in
    ``docs/rfcs/operation-identity-and-event-completeness.md`` plus ``gaps`` and
    ``warnings`` for human-facing output.
    """
    answered = {str(x) for x in (answered_approval_ids or set())}
    records: list[dict] = []
    present: set[str] = set()
    governed: set[str] = set()
    ungoverned_kinds: list[str] = []
    seen_kinds: set[str] = set()

    for position, step in enumerate(steps or []):
        if not isinstance(step, dict):
            continue
        classified = classify_step(step)
        if classified is None:
            kind = step.get("kind")
            if isinstance(kind, str) and kind and kind not in seen_kinds:
                seen_kinds.add(kind)
                ungoverned_kinds.append(kind)
            continue
        family, role = classified
        record = _record(step, position, family, role)
        records.append(record)
        present.add(family)
        if record["corr"] is not None:
            governed.add(family)

    findings: dict[str, list] = {key: [] for key in FINDING_KEYS}
    findings["ungoverned_kinds"] = ungoverned_kinds
    gaps: list[str] = []
    warnings: list[str] = []

    # An operation identity reused across families is not a valid identity.
    op_families: dict[str, set[str]] = {}
    for record in records:
        if record["corr"] is not None:
            op_families.setdefault(record["corr"]["operation_id"], set()).add(
                record["family"]
            )
    mismatch_ops = {
        operation_id
        for operation_id, families in op_families.items()
        if len(families) > 1
    }
    for operation_id in sorted(mismatch_ops):
        first = next(
            record
            for record in records
            if record["corr"] is not None
            and record["corr"]["operation_id"] == operation_id
        )
        findings["family_mismatches"].append(
            _finding(first, operation_id=operation_id, families=sorted(op_families[operation_id]))
        )
        gaps.append(
            f"operation '{operation_id}' is used across multiple families "
            f"({', '.join(sorted(op_families[operation_id]))})"
        )

    families_out: dict[str, dict[str, str]] = {}
    started = completed = orphaned = 0

    for family in FAMILIES:
        family_records = [r for r in records if r["family"] == family]
        if not family_records:
            continue
        if family in governed:
            fam_started, fam_completed, fam_orphaned, status = _audit_governed(
                family_records, mismatch_ops, answered, case_level_answered,
                findings, gaps,
            )
            basis = BASIS_OPERATION
        else:
            fam_started, fam_completed, fam_orphaned, status = _audit_legacy(
                family_records, answered, case_level_answered,
                findings, gaps, warnings,
            )
            basis = BASIS_NAME
        started += fam_started
        completed += fam_completed
        orphaned += fam_orphaned
        families_out[family] = {"status": status, "basis": basis}

    statuses = [entry["status"] for entry in families_out.values()]
    if not families_out:
        overall = STATUS_NO_EVENTS
    elif STATUS_INCOMPLETE in statuses:
        overall = STATUS_INCOMPLETE
    elif all(status == STATUS_COMPLETE for status in statuses):
        overall = STATUS_COMPLETE
    else:
        overall = STATUS_UNKNOWN

    bases = {entry["basis"] for entry in families_out.values()}
    if not bases:
        basis_overall: str = "none"
        scheme_overall: str | None = None
    elif len(bases) == 1:
        basis_overall = next(iter(bases))
        scheme_overall = SCHEME if basis_overall == BASIS_OPERATION else None
    else:
        basis_overall = "mixed"
        scheme_overall = "mixed"

    return {
        "status": overall,
        "scheme": scheme_overall,
        "basis": basis_overall,
        "families": families_out,
        "counts": {
            "started": started,
            "completed": completed,
            "orphaned": orphaned,
        },
        **findings,
        "gaps": gaps,
        "warnings": warnings,
    }


def compatibility_completeness_ok(audit: dict[str, Any]) -> bool:
    """The legacy ``completeness_ok`` boolean, derived from the audit.

    ``consistent_scope_unknown`` stays ``True``: an old artifact must not be
    failed for identifiers it never had. Only a proven gap is ``False``.
    """
    return audit.get("status") != STATUS_INCOMPLETE
