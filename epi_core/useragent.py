"""Identify EPI clients at the edge.

Cloudflare in front of ``cloud.epilabs.org`` answers 403 (error 1010) to
urllib's default ``Python-urllib/3.x`` User-Agent. Every urllib request the CLI
makes to Cloud must carry a real client identity. ``requests`` is already
allowed, but using this helper there too keeps the logs honest.
"""

from __future__ import annotations


def user_agent() -> str:
    try:
        from epi_core import __version__ as version
    except Exception:  # pragma: no cover - version resolution is best effort
        version = "unknown"
    return f"epi-recorder/{version}"
