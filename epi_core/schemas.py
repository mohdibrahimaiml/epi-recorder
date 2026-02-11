"""
EPI Core Schemas - Pydantic models for manifest and steps.
"""

from datetime import datetime
from typing import Any, Dict, Optional, List, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ManifestModel(BaseModel):
    """
    Manifest model for .epi files.
    
    This is the global header analogous to a PDF catalog.
    Contains metadata, file hashes, and cryptographic signature.
    """
    
    spec_version: str = Field(
        default="2.4.0",
        description="EPI specification version"
    )
    
    workflow_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for this workflow execution"
    )
    
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the .epi file was created (UTC)"
    )
    
    cli_command: Optional[str] = Field(
        default=None,
        description="The command-line invocation that produced this workflow"
    )
    
    env_snapshot_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of env.json (environment snapshot)"
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
        description="Ed25519 signature of the canonical CBOR hash of this manifest (excluding signature field)"
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
    
    approved_by: Optional[str] = Field(
        default=None,
        description="Person or entity who approved this workflow execution"
    )
    
    tags: Optional[List[str]] = Field(
        default=None,
        description="Tags for categorizing this workflow"
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
                    "env.json": "a3c5f...",
                    "artifacts/output.txt": "c7f8a..."
                },
                "signature": "ed25519:3a4b5c6d...",
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
        default_factory=datetime.utcnow,
        description="Timestamp when this step occurred (UTC)"
    )
    
    kind: str = Field(
        description="Step type: shell.command, python.call, llm.request, llm.response, file.write, security.redaction"
    )
    
    content: Dict[str, Any] = Field(
        description="Step-specific data (command, output, prompt, response, etc.)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "index": 0,
                "timestamp": "2025-01-15T10:30:00Z",
                "kind": "llm.request",
                "content": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "prompt": "Explain quantum computing",
                    "parameters": {"temperature": 0.7}
                }
            }
        }
    )



 