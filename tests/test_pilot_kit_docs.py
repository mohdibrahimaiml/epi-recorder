"""The pilot kit's two documents must stay true to the demo that runs.

Every fenced command in docs/BANK-REVIEWER-BRIEF.md has to exist in
examples/pilot_kit/run_pilot_demo.py, so a doc cannot drift away from the code.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BRIEF = REPO / "docs" / "BANK-REVIEWER-BRIEF.md"
GUIDE = REPO / "docs" / "PILOT-GUIDE.md"
DEMO = REPO / "examples" / "pilot_kit" / "run_pilot_demo.py"
AGENT = REPO / "examples" / "pilot_kit" / "agent.py"

PLACEHOLDER = re.compile(r"[<>]")


def _tokens(command: str) -> list[str]:
    """Words of a command, quotes stripped, placeholders dropped."""
    return [
        token.strip("\"'")
        for token in command.split()[1:]
        if not PLACEHOLDER.search(token)
    ]


def _fenced_commands(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    blocks = re.findall(r"```(?:bash|sh)\n(.*?)```", text, re.S)
    commands: list[str] = []
    for block in blocks:
        for line in block.splitlines():
            stripped = re.sub(r"\s+#.*$", "", line.strip().strip())
            if stripped and not stripped.startswith("#"):
                commands.append(stripped)
    return commands


def test_every_brief_command_runs_in_the_demo():
    demo = DEMO.read_text(encoding="utf-8")
    commands = [c for c in _fenced_commands(BRIEF) if c.startswith("epi ")]
    assert len(commands) >= 3, commands
    for command in commands:
        missing = [t for t in _tokens(command) if t not in demo]
        assert not missing, f"{command!r}: {missing} not in run_pilot_demo.py"


def test_every_guide_command_runs_in_the_demo():
    """The vendor guide must show the commands the demo actually runs.

    This is what keeps step 3 honest: the guide cannot show a `keys generate`
    before `link`, or a PKCS#11 URI the demo does not use.
    """
    demo = DEMO.read_text(encoding="utf-8")
    commands = [c for c in _fenced_commands(GUIDE) if c.startswith("epi ")]
    assert len(commands) >= 2, commands
    for command in commands:
        missing = [t for t in _tokens(command) if t not in demo]
        assert not missing, f"{command!r}: {missing} not in run_pilot_demo.py"


def test_guide_never_generates_a_key_before_linking():
    """`link` refuses when a key file exists, so the order is the fix."""
    commands = [c for c in _fenced_commands(GUIDE) if c.startswith("epi ")]
    assert not any(c.startswith("epi keys generate") for c in commands)
    guide = GUIDE.read_text(encoding="utf-8")
    assert "object=" in guide and "module-path=" in guide
    assert "EPI_PKCS11_PIN" in guide


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


def test_agent_does_not_answer_its_own_approval_request():
    """The pilot must prove the honest flow, not the self-reported one.

    A recorded approval response is the very step human sign-off replaces: it
    made the demo pass a strict check the product would otherwise fail.
    """
    source = AGENT.read_text(encoding="utf-8")
    assert "agent.approval.response" not in source
    assert "session.approval_request(" in source


def test_the_demo_runs_offline():
    demo = DEMO.read_text(encoding="utf-8")
    assert '"EPI_NOTARIZE": "0"' in demo
