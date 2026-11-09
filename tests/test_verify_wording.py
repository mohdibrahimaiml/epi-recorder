"""Plain-language wording for missing release/approver evidence.

A reviewer who verifies a shared file on its own must not read "NOT FOUND" or
"UNKNOWN" as "the vendor failed". These lines mean "not supplied" and "not
pinned", and say how to finish the check.
"""

from __future__ import annotations

from epi_cli.verify import _format_pre_action_lines, _format_release_lines


def test_missing_release_says_not_supplied_and_how_to_check() -> None:
    text = "\n".join(
        _format_release_lines(
            {
                "status": "not_found",
                "release_id": "rel_123",
                "detail": "no release rel_123 with the pinned digest was supplied",
            }
        )
    )
    assert "RELEASE DECLARED - NOT SUPPLIED" in text
    assert "not a failure" in text
    assert "--release-dir" in text
    assert "RELEASE NOT FOUND" not in text


def test_unpinned_approver_says_signed_and_how_to_pin() -> None:
    text = "\n".join(
        _format_pre_action_lines(
            {
                "requests": [
                    {
                        "status": "unknown_approver",
                        "approver": "DEMO APPROVER",
                        "basis": "hash chain only (vendor-written, not independent)",
                    }
                ]
            }
        )
    )
    assert "signed by DEMO APPROVER" in text
    assert "APPROVER NOT PINNED" in text
    assert "epi approvers add" in text
    assert "UNKNOWN APPROVER" not in text
