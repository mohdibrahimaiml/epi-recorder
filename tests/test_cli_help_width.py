"""Piped ``--help`` must not clip long option names.

Rich falls back to 80 columns when stdout is a pipe. At 80 the help table
rendered ``--require-human-approval`` as ``--require-human-appr…``, so the
documented check ``epi verify --help | grep require-human-approval`` found
nothing and the release's headline flag looked missing. ``cli_main`` widens
piped output; an interactive terminal keeps its own width.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# GitHub runners set GITHUB_ACTIONS, which makes typer force coloured output
# even into a pipe; a user's pipe has none of these.
_COLOUR_ENV = ("GITHUB_ACTIONS", "FORCE_COLOR", "PY_COLORS", "COLUMNS")


def _piped_help(*args: str, keep_colour_env: bool = False) -> str:
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    # Force the no-terminal fallback Rich uses when output is piped.
    for name in _COLOUR_ENV:
        if not (keep_colour_env and name != "COLUMNS"):
            env.pop(name, None)
    if keep_colour_env:
        env["GITHUB_ACTIONS"] = "true"
    proc = subprocess.run(
        [sys.executable, "-m", "epi_cli", *args],
        cwd=str(Path(__file__).resolve().parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return _ANSI.sub("", (proc.stdout or "") + (proc.stderr or ""))


@pytest.mark.parametrize(
    "args,flag",
    [
        (("verify", "--help"), "--require-human-approval"),
        (("verify", "--help"), "--require-timestamp"),
        (("verify", "--help"), "--witness-pubkey"),
    ],
)
def test_piped_help_renders_full_option_names(args, flag):
    assert flag in _piped_help(*args)


def test_piped_help_does_not_ellipsize_the_human_approval_flag():
    out = _piped_help("verify", "--help")
    # The clipped rendering was "--require-human-appr…".
    assert "--require-human-appr\u2026" not in out


def test_piped_help_keeps_the_flag_under_forced_colour():
    """On a CI runner the help is coloured; the flag must survive once colour is removed."""
    assert "--require-human-approval" in _piped_help("verify", "--help", keep_colour_env=True)
