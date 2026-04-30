"""
EPI Core Schemas - Pydantic models for manifest and steps.
"""

from datetime import datetime
from typing import Any, Dict, Optional, List, Union, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from epi_core._version import get_version
from epi_core.time_utils import utc_now


class PolicyModel(BaseModel):
    """
    Formal schema for policy enforcement outcomes.
    """
    policy_id: str = Field(..., description="Unique identifier for the policy set applied")
    version: str = Field(..., description="Version of the policy definition")
    status: Literal["compliant", "violation", "warning"] = Field(...)
    rules: List[str] = Field(default_factory=list, description="List of rule IDs evaluated")
    violation_count: int = Field(default=0)
    remediation: Optional[str] = Field(None, description="Suggested fix if violation occurred")


class ManifestModel(BaseModel):
    """
    Manifest model for .epi files.
    
    This is the global header analogous to a PDF catalog.
    Contains metadata, file hashes, and cryptographic signature.
    """
    
    spec_version: str = Field(
        default_factory=get_version,
        description="EPI specification version"
    )
    
    workflow_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for this workflow execution"
    )
    
    created_at: datetime = Field(
        default_factory=utc_now,
        description="Timestamp when the .epi file was created (UTC)"
    )
    
    cli_command: Optional[str] = Field(
        default=None,
        description="The command-line invocation that produced this workflow"
    )
    
    env_snapshot_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of environment.json (environment snapshot)"
    )
    
    file_manifest: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of file paths to their SHA-256 hashes for integrity verification"
    )
    
    public_key: Optional[str] = Field(
        default=None,
        description="Hex-encoded public key used for verification"
    )
    
    signature: Optional[str] = Field(
        default=None,
        description="Ed25519 signature of the canonical JSON hash (SHA-256) of this manifest (excluding signature field). Uses JSON canonicalization for spec v2+."
    )

    container_format: Optional[Literal["legacy-zip", "envelope-v2"]] = Field(
        default=None,
        description="Physical container format used for this .epi artifact."
    )

    analysis_status: Optional[Literal["complete", "skipped", "error"]] = Field(
        default=None,
        description="Whether deterministic analysis completed, was intentionally skipped, or failed during packing"
    )

    analysis_error: Optional[str] = Field(
        default=None,
        description="Short non-sensitive analysis failure reason when analysis_status is error"
    )
    
    # New metadata fields for decision tracking
    goal: Optional[str] = Field(
        default=None,
        description="Goal or objective of this workflow execution"
    )
    
    notes: Optional[str] = Field(
        default=None,
        description="Additional notes or context about this workflow"
    )
    
    metrics: Optional[Dict[str, Union[float, str]]] = Field(
        default=None,
        description="Key-value metrics for this workflow (accuracy, latency, etc.)"
    )

    source: Optional[Dict[str, str]] = Field(
        default=None,
        description="System integration identity and framework bindings"
    )

    total_steps: Optional[int] = Field(None)
    total_validators: Optional[int] = Field(None)
    total_llm_calls: Optional[int] = Field(None)
    passed: Optional[int] = Field(None)
    failed: Optional[int] = Field(None)
    corrected: Optional[int] = Field(None)

    trust: Optional[Dict[str, Any]] = Field(
        default=None,
        description="""
        Immediate cryptographic verification state structure.
        Expected keys: 
          - public_key_id: Unique name/ID of the key
          - registry_url: Source of truth for this key's trust
          - fingerprint: SHA-256 fingerprint of the public key
          - steps_hash: Integrity hash for the steps.jsonl file
        """
    )
    
    approved_by: Optional[str] = Field(
        default=None,
        description="Person or entity who approved this workflow execution"
    )
    
    tags: Optional[List[str]] = Field(
        default=None,
        description="Tags for categorizing this workflow"
    )

    governance: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional governance metadata (DID identity, trust score, source, etc.)",
    )

    viewer_version: Optional[str] = Field(
        default=None,
        description="Preferred viewer shell version for this artifact (e.g. 'minimal', 'forensic', '2.0')"
    )

    policy: Optional[PolicyModel] = Field(
        default=None,
        description="Formal policy evaluation result and rules applied",
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "spec_version": "1.0-keystone",
                "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
                "created_at": "2025-01-15T10:30:00Z",
                "cli_command": "epi record --out demo.epi -- python train.py",
                "env_snapshot_hash": "a3c5f...",
                "file_manifest": {
                    "steps.jsonl": "b4d6e...",
                    "environment.json": "a3c5f...",
                    "artifacts/output.txt": "c7f8a..."
                },
                "analysis_status": "complete",
                "signature": "ed25519:3a4b5c6d...",
                "container_format": "envelope-v2",
                "goal": "Improve model accuracy",
                "notes": "Switched to GPT-4 for better reasoning",
                "metrics": {"accuracy": 0.92, "latency": 210},
                "approved_by": "alice@company.com",
                "tags": ["prod-candidate", "v1.0"]
            }
        }
    )


class StepModel(BaseModel):
    """
    Step model for recording individual events in a workflow timeline.
    
    Each step is an immutable record in steps.jsonl (NDJSON format).
    """
    
    index: int = Field(
        description="Sequential step number (0-indexed)"
    )
    
    timestamp: datetime = Field(
        default_factory=utc_now,
        description="Timestamp when this step occurred (UTC)"
    )
    
    kind: str = Field(
        description="Step type: shell.command, python.call, llm.request, llm.response, file.write, security.redaction, validation.pass, validation.fail, validation.corrected, validation.start"
    )
    
    content: Dict[str, Any] = Field(
        default_factory=dict,
        description="Step-specific data (command, output, prompt, response, etc.)"
    )
    
    trace_id: Optional[str] = Field(
        default=None,
        description="Global W3C execution trace identifier"
    )
    
    span_id: Optional[str] = Field(
        default=None,
        description="Specific W3C execution span identifier"
    )
    
    parent_span_id: Optional[str] = Field(
        default=None,
        description="Parent W3C execution span identifier"
    )

    prev_hash: Optional[str] = Field(
        default=None,
        description="Canonical hash (SHA-256) of the previous step in the timeline, forming an immutable chain."
    )

    # Optional governance metadata for scoped step-level audit information.
    # Use only when relevant (e.g. `agent.decision` events) to avoid noise.
    governance: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional governance metadata for this step (policy_id, decision, trust_score, agent_did, etc.)",
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "index": 0,
                "timestamp": "2025-01-15T10:30:00Z",
                "kind": "llm.request",
                "content": {
                    "provider": "openai",
                    "model": "gpt-4"
                },
                "trace_id": "0af7651916cd43dd8448eb211c80319c",
                "span_id": "b7ad6b7169203331"
            }
        }
    )


class ValidationPayload(BaseModel):
    """
    Validation event payload for use in StepModel.content.

    Represents outcomes from validation systems (Guardrails, Pydantic, Outlines, etc.).

    Optional — not enforced on StepModel. Use when kind is validation.*.

    Examples:
        # Pass validation
        validation_pass = ValidationPayload(
            validator="guardrails",
            result="pass",
            score=0.95
        )

        # Fail validation with details
        validation_fail = ValidationPayload(
            validator="guardrails",
            result="fail",
            score=0.1,
            input_ref=5,  # reference to step index
            details={
                "error_type": "RefusalValidationError",
                "message": "Output contains refused content"
            }
        )

        # Corrected output
        validation_corrected = ValidationPayload(
            validator="guardrails",
            result="corrected",
            input_ref=5,
            output_ref=6,  # reference to step index of corrected output
            details={"regenerated": True}
        )
    """

    validator: str = Field(
        description="Name of validator (e.g., 'guardrails', 'pydantic', 'outlines', 'custom')"
    )

    result: Literal["pass", "fail", "corrected"] = Field(
        description="Validation outcome: pass (succeeded), fail (rejected), corrected (auto-fixed)"
    )

    input_ref: Optional[int] = Field(
        default=None,
        description="Reference to input step index (0-indexed) if validation was in response to a prior step"
    )

    output_ref: Optional[int] = Field(
        default=None,
        description="Reference to output step index (0-indexed) for corrected outcomes, or artifact reference"
    )

    score: Optional[float] = Field(
        default=None,
        description="Confidence/severity score (0.0-1.0). 1.0 = passed cleanly, 0.0 = failed completely"
    )

    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Validator-specific details: error_type, message, suggestions, metadata, etc."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "validator": "guardrails",
                "result": "fail",
                "score": 0.25,
                "input_ref": 5,
                "details": {
                    "error_type": "RefusalValidationError",
                    "message": "Output contains refused topic",
                    "suggestions": ["regenerate", "refine_prompt"]
                }
            }
        }
    )

