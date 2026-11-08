"""A seal killed between allocate and commit must leave a visible gap.

The pre-launch test killed a process inside ``with record():`` before signing;
no number had been allocated, so the audit was correct to stay contiguous. This
test kills *after* allocation (test-only hook) and proves the reservation is
reaped as a burn or reported as missing — never silently reused.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _wait_for_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"witness server did not start on port {port}")


def _seal(path: Path, goal: str) -> str:
    return (
        "from epi_recorder import record\n"
        f"with record(r'{path}', goal={goal!r}, with_viewer=False) as epi:\n"
        "    epi.log_step('custom.test', {'n': 1})\n"
    )


@pytest.mark.skipif(not hasattr(os, "_exit"), reason="needs os._exit")
def test_crash_after_allocate_shows_a_burn_or_gap(tmp_path: Path) -> None:
    home = tmp_path / "home"
    keys = home / "keys"
    ledger = home / "seal_ledger"
    keys.mkdir(parents=True)
    ledger.mkdir(parents=True)
    port = _free_port()
    secret = "burn-test-secret"
    log = tmp_path / "received.jsonl"
    env = os.environ.copy()
    env.update(
        {
            "EPI_HOME": str(home),
            "EPI_KEYS_DIR": str(keys),
            "EPI_SEAL_LEDGER_DIR": str(ledger),
            "EPI_WITNESS_URL": f"http://127.0.0.1:{port}/",
            "EPI_WITNESS_SECRET": secret,
            "EPI_NOTARIZE": "0",
            "EPI_QUIET": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    subprocess.run(
        [sys.executable, "-m", "epi_cli", "keys", "generate", "--name", "default"],
        env=env,
        check=True,
        capture_output=True,
    )
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "epi_cli",
            "witness",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--out",
            str(log),
            "--secret",
            secret,
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(port)

        crashed = subprocess.run(
            [sys.executable, "-c", _seal(tmp_path / "crashed.epi", "crash")],
            env={**env, "EPI_TEST_CRASH_AFTER_SEAL_ALLOCATE": "1"},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert crashed.returncode == 99, crashed.stderr[-1000:]

        state_path = next(ledger.glob("*.json"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert "1" in state.get("pending", {}), state

        after = subprocess.run(
            [sys.executable, "-c", _seal(tmp_path / "after.epi", "after")],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert after.returncode == 0, after.stderr[-2000:]

        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state.get("pending") == {}, state
        assert any(int(b.get("seq", 0)) == 1 for b in state.get("burns", [])), state

        heartbeat = subprocess.run(
            [sys.executable, "-m", "epi_cli", "witness", "heartbeat", "--key", "default"],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert heartbeat.returncode == 0, heartbeat.stderr[-1000:]

        audit = subprocess.run(
            [sys.executable, "-m", "epi_cli", "witness", "audit", str(log), "--json"],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert audit.returncode == 0, audit.stderr[-1000:]
        report = json.loads(audit.stdout[audit.stdout.index("{") :])
        assert report["chains"], report
        chain = report["chains"][0]
        assert chain["contiguous"] is False, chain
        assert 1 in chain.get("burned", []) or 1 in chain.get("missing", []), chain
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except Exception:
            server.kill()
