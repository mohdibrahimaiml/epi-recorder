"""Small runtime helpers shared by the paid package."""
from __future__ import annotations

from epi_core.connectors import fetch_live_record
from epi_core.redactor import get_default_redactor
from epi_core.telemetry import (
    TelemetryError,
    track_event,
    validate_event_payload,
    validate_pilot_signup_payload,
)
from epi_core.time_utils import utc_now, utc_now_iso
from epi_core.workspace import create_recording_workspace

__all__ = [
    "TelemetryError",
    "create_recording_workspace",
    "fetch_live_record",
    "get_default_redactor",
    "track_event",
    "utc_now",
    "utc_now_iso",
    "validate_event_payload",
    "validate_pilot_signup_payload",
]
