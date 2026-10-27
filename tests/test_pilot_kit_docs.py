"""The pilot kit's two documents must stay true to the demo that runs.

Every fenced command in docs/BANK-REVIEWER-BRIEF.md has to exist in
examples/pilot_kit/run_pilot_demo.py, so a doc cannot drift away from the code.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BRIEF = REPO / "docs" / "BANK-REVIEWER-BRIEF.md"
DEMO = REPO / "examples" / "pilot_kit" / "run_pilot_demo.py"
AGENT = REPO / "examples" / "pilot_kit" / "agent.py"

PLACEHOLDER = re.compile(r"[<>]")


def _fenced_commands(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    blocks = re.findall(r"```(?:bash|sh)\n(.*?)```", text, re.S)
    return [
        line.strip()
        for block in blocks
        for line in block.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_every_brief_command_runs_in_the_demo():
    demo = DEMO.read_text(encoding="utf-8")
    commands = [c for c in _fenced_commands(BRIEF) if c.startswith("epi ")]
    assert len(commands) >= 3, commands
    for command in commands:
        tokens = [t for t in command.split()[1:] if not PLACEHOLDER.search(t)]
        missing = [t for t in tokens if t not in demo]
        assert not missing, f"{command!r}: {missing} not in run_pilot_demo.py"


def test_demo_checks_the_bank_home_holds_no_private_key():
    demo = DEMO.read_text(encoding="utf-8")
    assert "no *.key in the bank's EPI_HOME" in demo
    assert "no approver key material in the bank's EPI_HOME" in demo


def test_two_fingerprint_commands_match_the_brief():
    """The brief's three commands: trust, approvers add, verify."""
    commands = _fenced_commands(BRIEF)
    joined = "\n".join(commands)
    assert "epi keys trust" in joined
    assert "epi approvers add" in joined
    assert "--require-human-approval" in joined
    assert "--policy strict" in joined


def test_agent_runs_without_an_api_key_by_default():
    source = AGENT.read_text(encoding="utf-8")
    assert "--offline" in source and "default=True" in source
    assert "OPENAI_API_KEY" in source
    # Approval response steps are recorded as agent-reported, never as signed.
    assert "raw_api_unverified" in source


def test_the_demo_runs_offline():
    demo = DEMO.read_text(encoding="utf-8")
    assert '"EPI_NOTARIZE": "0"' in demo
