"""Field transformation functions: AGT AuditEntry → EPI step.

Every transformation is explicit, recorded, and reversible where possible.
No silent dropping of unknown fields.
"""

from __future__ import annotations

from datetime import datetime

from .errors import AGTTransformError
from .schemas import FieldMapping, MappingReport


# ─────────────────────────────────────────────────────────────
# AGT event_type → EPI step kind mapping
# ─────────────────────────────────────────────────────────────

EVENT_TYPE_TO_KIND = {
    "tool_invocation": "tool.call",
    "tool_blocked": "tool.blocked",
    "policy_evaluation": "policy.eval",
    "policy_violation": "policy.violation",
    "rogue_detection": "security.alert",
    "agent_invocation": "agent.delegate",
}

KIND_TO_EVENT_TYPE = {v: k for k, v in EVENT_TYPE_TO_KIND.items()}

# Default: unknown AGT event types become "agt.unknown.{event_type}"


def map_event_type(event_type: str, report: MappingReport) -> str:
    """Map AGT event_type to EPI step kind."""
    if event_type in EVENT_TYPE_TO_KIND:
        epi_kind = EVENT_TYPE_TO_KIND[event_type]
        report.field_mappings.append(
            FieldMapping(
                source_field="event_type",
                target_field="kind",
                mapping_type="translated",
                source_value=event_type,
                target_value=epi_kind,
                notes=f"AGT '{event_type}' → EPI '{epi_kind}'",
            )
        )
        return epi_kind

    # Unknown event type — preserve as agt.unknown.*
    epi_kind = f"agt.unknown.{event_type}"
    report.field_mappings.append(
        FieldMapping(
            source_field="event_type",
            target_field="kind",
            mapping_type="translated",
            source_value=event_type,
            target_value=epi_kind,
            notes=f"Unknown AGT event type '{event_type}' — prefixed",
        )
    )
    report.warnings.append(
        f"Unknown event_type '{event_type}' — mapped to '{epi_kind}'"
    )
    return epi_kind


# ─────────────────────────────────────────────────────────────
# AGT action → EPI action mapping
# ─────────────────────────────────────────────────────────────

ACTION_MAP = {
    "allow": "allowed",
    "deny": "denied",
    "audit": "audited",
    "quarantine": "quarantined",
    "warning": "warned",
}


def map_action(action: str, report: MappingReport) -> str:
    """Map AGT action to EPI action string."""
    result = ACTION_MAP.get(action, action)
    report.field_mappings.append(
        FieldMapping(
            source_field="action",
            target_field="action",
            mapping_type="translated" if action in ACTION_MAP else "exact",
            source_value=action,
            target_value=result,
        )
    )
    return result


# ─────────────────────────────────────────────────────────────
# AGT outcome → EPI status mapping
# ─────────────────────────────────────────────────────────────

OUTCOME_MAP = {
    "success": "completed",
    "failure": "failed",
    "denied": "blocked",
    "error": "error",
}


def map_outcome(outcome: str, report: MappingReport) -> str:
    """Map AGT outcome to EPI status."""
    result = OUTCOME_MAP.get(outcome, outcome)
    report.field_mappings.append(
        FieldMapping(
            source_field="outcome",
            target_field="status",
            mapping_type="translated" if outcome in OUTCOME_MAP else "exact",
            source_value=outcome,
            target_value=result,
        )
    )
    return result


# ─────────────────────────────────────────────────────────────
# AGT agent_did → EPI agent_name mapping
# ─────────────────────────────────────────────────────────────


def map_agent_did(did: str, report: MappingReport) -> str:
    """Extract short agent name from DID.

    did:web:sales-assistant.example.com → sales-assistant
    did:web:agent.example.com → agent
    """
    if did.startswith("did:web:"):
        host = did[8:].split(":")[0]  # Remove did:web: prefix
        name = host.split(".")[0]  # Take first subdomain
    else:
        name = did.split(":")[-1] if ":" in did else did

    report.field_mappings.append(
        FieldMapping(
            source_field="agent_did",
            target_field="agent_name",
            mapping_type="derived",
            source_value=did,
            target_value=name,
            notes="Extracted name from DID",
        )
    )
    return name


# ─────────────────────────────────────────────────────────────
# AGT AuditEntry → EPI step content dict
# ─────────────────────────────────────────────────────────────


def build_step_content(entry: dict, report: MappingReport) -> dict:
    """Build EPI step content dict from AGT AuditEntry data.

    Preserves all AGT 'data' fields under 'agt_data' namespace.
    Maps known top-level fields to EPI equivalents.
    """
    content: dict = {}

    # Map known fields
    if "resource" in entry and entry["resource"]:
        content["resource"] = entry["resource"]
        report.field_mappings.append(
            FieldMapping(
                source_field="resource",
                target_field="content.resource",
                mapping_type="exact",
                source_value=str(entry["resource"])[:50],
                target_value=str(entry["resource"])[:50],
            )
        )

    # Map policy_decision if present
    if "policy_decision" in entry and entry["policy_decision"]:
        content["policy_decision"] = entry["policy_decision"]
        report.field_mappings.append(
            FieldMapping(
                source_field="policy_decision",
                target_field="content.policy_decision",
                mapping_type="exact",
                source_value=str(entry["policy_decision"])[:50],
            )
        )

    # Map trace_id if present
    if "trace_id" in entry and entry["trace_id"]:
        content["trace_id"] = entry["trace_id"]
        report.field_mappings.append(
            FieldMapping(
                source_field="trace_id",
                target_field="content.trace_id",
                mapping_type="exact",
                source_value=entry["trace_id"],
            )
        )

    # Preserve all AGT data fields under agt_data namespace
    if "data" in entry and entry["data"]:
        content["agt_data"] = entry["data"]
        report.field_mappings.append(
            FieldMapping(
                source_field="data",
                target_field="content.agt_data",
                mapping_type="preserved_raw",
                source_value=str(list(entry["data"].keys())),
                notes=f"Preserved {len(entry['data'])} raw data fields",
            )
        )

    # Store entry_hash for hash chain verification
    if "entry_hash" in entry and entry["entry_hash"]:
        content["agt_entry_hash"] = entry["entry_hash"]
        report.field_mappings.append(
            FieldMapping(
                source_field="entry_hash",
                target_field="content.agt_entry_hash",
                mapping_type="preserved_raw",
                source_value=entry["entry_hash"][:20] + "...",
            )
        )

    return content
