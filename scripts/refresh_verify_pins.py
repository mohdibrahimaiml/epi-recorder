#!/usr/bin/env python3
"""Re-pin the /verify command block to the keys this repository ships.

`make_decision_example.py` must mint fresh demo keys on every run (it needs the
private halves to seal), so the fingerprints printed on /verify go stale each
time the samples are re-sealed. `tests/test_verify_demo_commands.py` fails when
they drift; this script fixes the drift in one command.

It asks the real CLI what each shipped `.pub` file's fingerprint is, in an empty
HOME, so the numbers are exactly what a visitor would see, then rewrites
`website/verify/index.html`.

Usage:
    python scripts/refresh_verify_pins.py
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "website" / "assets" / "demo"
PAGE = ROOT / "website" / "verify" / "index.html"

# The three pins the page prints, in page order, with the CLI call that reveals
# each one. `keys trust` reports "Fingerprint:", `approvers add` reports
# "Key fingerprint:".
PINS = [
    ("demo-sealer", "Fingerprint", ["keys", "trust", "demo-sealer.pub", "--name", "demo-sealer"]),
    ("DEMO KEY", "Key fingerprint", ["approvers", "add", "demo-key.pub", "--name", "DEMO KEY"]),
    ("DEMO APPROVER", "Key fingerprint", ["approvers", "add", "demo-approver.pub", "--name", "DEMO APPROVER"]),
]

FINGERPRINT = re.compile(r"([0-9a-f]{4}(?:\s[0-9a-f]{4}){3})", re.I)


def _epi_command() -> list[str]:
    """The CLI to call: this checkout's, not whatever is on PATH."""
    exe = Path(sys.executable).with_name("epi.exe" if os.name == "nt" else "epi")
    if exe.exists():
        return [str(exe)]
    return [sys.executable, "-m", "epi_cli"]


def _run(argv: list[str], home: Path, env: dict) -> str:
    result = subprocess.run(argv, cwd=DEMO, capture_output=True, text=True, env=env)
    return result.stdout + result.stderr


def fingerprints() -> dict[str, str]:
    home = Path(tempfile.mkdtemp(prefix="epi-pin-"))
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), EPI_HOME=str(home / ".epi"))
    epi = _epi_command()
    found: dict[str, str] = {}
    try:
        for label, marker, args in PINS:
            output = _run([*epi, *args], home, env)
            match = FINGERPRINT.search(output.split(marker, 1)[-1]) if marker in output else FINGERPRINT.search(output)
            if not match:
                raise SystemExit(f"could not read the {label} fingerprint from:\n{output}")
            found[label] = match.group(1)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    return found


def main() -> int:
    found = fingerprints()
    text = PAGE.read_text(encoding="utf-8")

    # Replace by position: each pinned fingerprint appears on its own command
    # line, so match the line and swap only the quoted fingerprint.
    changed = 0
    for label, marker, args in PINS:
        command = args[2] if args[0] == "keys" else args[2]  # the .pub filename
        pattern = re.compile(rf"({re.escape(command)}.*?--fingerprint \")[0-9a-f ]+(\")", re.I)
        text, n = pattern.subn(lambda m: m.group(1) + found[label] + m.group(2), text)
        changed += n
        print(f"{label:<14} {found[label]}  ({n} line(s))")

    if not changed:
        print("No pinned fingerprints found on /verify — nothing rewritten.")
        return 1

    PAGE.write_text(text, encoding="utf-8")
    print(f"\nUpdated {PAGE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
