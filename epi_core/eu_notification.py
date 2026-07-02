"""EU AI Act database notification data model.

Generates signed, SCITT-anchored notification payloads for high-risk AI system
registration with EU member state authorities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


class EUDatabaseNotification(BaseModel):
    """EU AI Act Article 49 / 66 notification for high-risk AI system registration.

    Generates a cryptographically signed notification record that can be submitted
    to the EU database when the API becomes available.
    """

    system_name: str = Field(..., description="Name of the high-risk AI system")
    manufacturer: str = Field(..., description="Legal name of the manufacturer/provider")
    authorized_representative: Optional[str] = Field(
        None, description="Authorized representative in the EU (if manufacturer is non-EU)"
    )
    conformity_assessment_body: Optional[str] = Field(
        None, description="Notified body that performed the conformity assessment"
    )
    risk_category: Literal["limited", "high", "unacceptable"] = Field(
        ..., description="Risk classification per EU AI Act Annex III"
    )
    conformity_declaration_ref: str = Field(
        ..., description="Reference to Section 8 Declaration of Conformity"
    )
    technical_documentation_hash: str = Field(
        ..., description="SHA-256 hash of the complete Annex IV .epi file"
    )
    scitt_receipt_id: Optional[str] = Field(
        None, description="SCITT transparency service receipt ID (if anchored)"
    )
    notification_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Date of notification generation",
    )
    member_states: list[str] = Field(
        default_factory=list,
        description="Member states where the system is deployed (ISO 3166-1 alpha-2 codes)",
    )
    system_version: str = Field("1.0.0", description="System version")
    intended_purpose: Optional[str] = Field(None, description="Brief intended purpose")
    contact_email: Optional[str] = Field(None, description="Technical contact email")
    contact_phone: Optional[str] = Field(None, description="Technical contact phone")

    def model_dump_notification(self) -> dict:
        """Dump notification as a JSON-serializable dict for signing."""
        data = self.model_dump(mode="json")
        data.setdefault("member_states", [])
        return data


__all__ = ["EUDatabaseNotification"]
