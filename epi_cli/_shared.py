"""
EPI CLI Shared Utilities - Common helpers used by record.py and run.py.

Centralised here to avoid duplication and ensure bug fixes apply everywhere.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import List


def ensure_python_command(cmd: List[str]) -> List[str]:
    """
    Prepend the current Python executable if the first arg is a .py file.
    If the user already typed 'python script.py', leave it as-is.
    """
    if not cmd:
        return cmd
    if cmd[0].lower().endswith(".py"):
        return [sys.executable] + cmd
    return cmd


def build_env_for_child(steps_dir: Path, enable_redaction: bool) -> dict:
    """
    Build the environment for the child recording process.

    Injects EPI_RECORD, EPI_STEPS_DIR, and EPI_REDACT, then prepends a
    temporary bootstrap directory containing sitecustomize.py so that
    epi_recorder patches LLM libraries before the user script runs.
    """
    env = os.environ.copy()

    env["EPI_RECORD"] = "1"
    env["EPI_STEPS_DIR"] = str(steps_dir)
    env["EPI_REDACT"] = "1" if enable_redaction else "0"

    # Temporary sitecustomize.py bootstrap
    bootstrap_dir = Path(tempfile.mkdtemp(prefix="epi_bootstrap_"))
    (bootstrap_dir / "sitecustomize.py").write_text(
        "from epi_recorder.bootstrap import initialize_recording\n",
        encoding="utf-8",
    )

    project_root = Path(__file__).resolve().parent.parent
    existing = env.get("PYTHONPATH", "")
    sep = os.pathsep
    env["PYTHONPATH"] = (
        f"{bootstrap_dir}{sep}{project_root}{sep + existing if existing else ''}"
    )

    return env
