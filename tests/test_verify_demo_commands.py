"""The commands printed on /verify must work against the files we ship.

A visitor copies that block, runs it on the downloaded files, and decides
whether to trust EPI. If the demo keys are regenerated, the witness log
re-sealed, or the artifacts re-sealed without each other, the page still looks
fine and the command fails with "NOT THE VERSION REPORTED TO YOU". This test
runs the block exactly as written, in an empty home, so the page and the files
cannot drift again.
"""

from __future__ import annotations

import html
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERIFY_PAGE = REPO / "website" / "verify" / "index.html"
DEMO_DIR = REPO / "website" / "assets" / "demo"


def _commands() -> list[list[str]]:
    text = VERIFY_PAGE.read_text(encoding="utf-8")
    match = re.search(
        r"<pre[^>]*>\s*(epi keys trust demo-sealer\.pub.*?)</pre>",
        text,
        re.S,
    )
    assert match, "the /verify page no longer shows the demo command block"
    block = html.unescape(match.group(1))
    block = block.replace("\\\n", " ")
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    commands = [shlex.split(line) for line in lines]
    # The page writes `epi ...`; the test runs the same commands through the
    # module so it does not depend on a console script being on PATH.
    return [cmd[1:] if cmd and cmd[0] == "epi" else cmd for cmd in commands]


def _demo_fingerprints() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in (DEMO_DIR / "demo-keys.txt").read_text(encoding="utf-8").splitlines():
        name, _, fingerprint = line.partition("  ")
        if name and fingerprint:
            pins[name.strip()] = fingerprint.strip()
    return pins


def test_the_page_pins_match_the_keys_it_ships():
    pins = _demo_fingerprints()
    text = " ".join(" ".join(cmd) for cmd in _commands())
    for name, fingerprint in pins.items():
        assert fingerprint in text, f"/verify does not pin {name} at {fingerprint}"


def test_the_page_commands_pass_in_a_clean_home(tmp_path):
    work = tmp_path / "demo"
    shutil.copytree(DEMO_DIR, work, ignore=shutil.ignore_patterns("__pycache__"))
    home = tmp_path / "home"
    for name in ("keys", "trusted_keys", "trusted_approvers", "approver_keys"):
        (home / name).mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "EPI_HOME": str(home),
            "EPI_KEYS_DIR": str(home / "keys"),
            "EPI_TRUSTED_KEYS_DIR": str(home / "trusted_keys"),
            "EPI_TRUSTED_APPROVERS_DIR": str(home / "trusted_approvers"),
            "EPI_APPROVER_KEYS_DIR": str(home / "approver_keys"),
            "EPI_TELEMETRY": "0",
            "EPI_NOTARIZE": "0",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    for key in ("EPI_WITNESS_URL", "EPI_WITNESS_SECRET", "EPI_CLOUD_API_KEY"):
        env.pop(key, None)

    output = ""
    for command in _commands():
        result = subprocess.run(
            [sys.executable, "-m", "epi_cli", *command],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        output += result.stdout + result.stderr
        assert result.returncode == 0, (
            f"page command failed: epi {' '.join(command)}\n{output[-4000:]}"
        )

    assert "DECISION: PASS" in output, output[-4000:]
    assert re.search(r"Release:\s+claims-policy 1\.4\s+MATCHES", output), output[-4000:]
    assert "APPROVED BEFORE ACTION" in output, output[-4000:]
    # The failure this test exists for must not be possible to ship silently.
    assert "NOT THE VERSION REPORTED TO YOU" not in output
