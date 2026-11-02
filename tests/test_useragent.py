"""The CLI must identify itself at the Cloudflare edge (error 1010)."""

from __future__ import annotations

from epi_core.useragent import user_agent


def test_user_agent_identifies_the_client():
    value = user_agent()
    assert value.startswith("epi-recorder/")
    assert len(value) > len("epi-recorder/")
