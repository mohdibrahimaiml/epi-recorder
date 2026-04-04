"""
Timezone-aware UTC helpers for EPI runtime code.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp as ISO 8601."""
    return utc_now().isoformat()
