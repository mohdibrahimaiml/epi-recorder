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
    assert "not a tamper finding" in text
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


def test_release_approval_unpinned_is_not_unapproved() -> None:
    text = "\n".join(
        _format_release_lines(
            {
                "status": "approver_not_pinned",
                "name": "claims-policy",
                "version": "1.4",
                "approvals": {
                    "required": 1,
                    "have": 0,
                    "valid": 1,
                    "approvers": [
                        {"name": "DEMO KEY", "pinned": False},
                    ],
                },
                "detail": (
                    "approved by DEMO KEY - APPROVER NOT PINNED (0/1 pinned); "
                    "pin with: epi approvers add <their-key-file> --name 'DEMO KEY'"
                ),
                "path": "C:/Downloads/claims-policy-1.4.epi",
                "release_discovery": "next_to_decision",
                "release_duplicates_skipped": 1,
            }
        )
    )
    assert "APPROVER NOT PINNED" in text
    assert "approved by DEMO KEY" in text
    assert "epi approvers add" in text
    assert "using release file next to the decision: claims-policy-1.4.epi" in text
    assert "ignored 1 identical copy" in text
    assert "approved by 0/1" not in text
