"""Workflow actions must be pinned to a commit SHA, not a mutable tag.

A tag is a pointer someone else can move. `actions/checkout@v7` resolves to
whatever that tag points at on the day the job runs, so a compromised or
re-pointed upstream tag executes with this repository's workflow token — in
the release and signing workflows, with their secrets.

Pinning to a 40-hex commit is immutable. The `# v7` comment keeps the human
(and Dependabot) able to tell which release the SHA is.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

PINNED = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*@[0-9a-f]{40}(?:\s+#\s*\S+)?$"
)
USES = re.compile(r"^\s*-?\s*uses:\s*(.+?)\s*$")


def _uses_lines():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            m = USES.match(line)
            if m:
                yield path.name, lineno, m.group(1)


def test_every_remote_action_is_pinned_to_a_sha():
    unpinned = []
    for name, lineno, ref in _uses_lines():
        # Local composite actions and docker images are not tag-resolved.
        if ref.startswith("./") or ref.startswith("docker://"):
            continue
        if not PINNED.match(ref):
            unpinned.append(f"{name}:{lineno}: {ref}")
    assert not unpinned, (
        "actions must be pinned to a 40-character commit SHA "
        "(owner/repo@<sha> # vN):\n" + "\n".join(unpinned)
    )


def test_the_check_itself_can_fail():
    """Guard the guard: a bare tag must be rejected by the pattern."""
    assert PINNED.match("actions/checkout@" + "a" * 40 + " # v7")
    assert not PINNED.match("actions/checkout@v7")
    assert not PINNED.match("actions/checkout@" + "a" * 12)


def test_workflows_are_found():
    assert list(WORKFLOWS.glob("*.yml")), "no workflow files found to check"
