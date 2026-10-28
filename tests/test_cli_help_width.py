"""Piped ``--help`` must not clip long option names.

Rich falls back to 80 columns when stdout is a pipe. At 80 the help table
rendered ``--require-human-approval`` as ``--require-human-appr…``, so the
documented check ``epi verify --help | grep require-human-approval`` found
nothing and the release's headline flag looked missing. ``cli_main`` widens
piped output; an interactive terminal keeps its own width.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _piped_help(*args: str) -> str:
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    # Force the no-terminal fallback Rich uses when output is piped.
    env.pop("COLUMNS", None)
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
    return (proc.stdout or "") + (proc.stderr or "")


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
