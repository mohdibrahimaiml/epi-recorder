"""EPI Cloud's hosted witness is a paid feature (Startup and above).

A Free workspace's report comes back 402. The CLI must say why in plain words,
keep the report queued (so upgrading and flushing delivers it), and never tell
the user to fix their secret or network.
"""

from __future__ import annotations

from epi_core.webhook import describe_witness_failure


def test_402_says_free_plan_and_keeps_the_report():
    info = describe_witness_failure("HTTP Error 402: Payment Required", cloud_login=True, customer="Acme Bank")
    assert info["status"] == 402
    assert "Startup and above" in info["reason"]
    assert "kept on this computer" in info["reason"]
    assert info["retry_helps"] is True
    assert "epi witness flush" in info["fix"]
    assert "cloud login" not in info["fix"]


def test_other_statuses_are_unchanged():
    assert describe_witness_failure("HTTP Error 401: Unauthorized", cloud_login=True)["fix"] == "run: epi cloud login"
    assert describe_witness_failure("HTTP Error 410: Gone", cloud_login=True)["retry_helps"] is False
