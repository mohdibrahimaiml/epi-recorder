"""Every committed sample is handed to a counterparty; none may name the builder.

`scripts/check_artifact_privacy.py` is the gate. This test runs it on every
platform the suite covers, so a leaking sample fails a normal test run and not
just the dedicated CI job.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPO))

from scripts.check_artifact_privacy import committed_epi_files, findings  # noqa: E402


def test_no_committed_sample_carries_host_detail():
    leaking = {}
    for path in committed_epi_files():
        found = findings(path)
        if found:
            leaking[str(path)] = found
    assert not leaking, (
        "sealed samples leak the builder's machine to whoever downloads them; "
        "re-seal with: python scripts/reseal_sample_privacy.py\n"
        + "\n".join(f"  {name}: {', '.join(fields)}" for name, fields in sorted(leaking.items()))
    )


def test_gate_exits_zero_on_the_repo():
    """The command itself must be safe to wire into CI."""
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_artifact_privacy.py")],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_gate_reports_a_leaking_artifact(tmp_path):
    """The gate must fail closed: a crafted artifact with host detail, not a skip."""
    import io
    import json
    import zipfile

    from scripts.check_artifact_privacy import findings

    epi = tmp_path / "leaky.epi"
    env = {
        "python": {"executable": "/usr/bin/python3", "pid": 1},
        "os": {"processor": "x86"},
        "environment_variables": {"USER": "someone"},
    }
    with zipfile.ZipFile(epi, "w") as zf:
        zf.writestr("environment.json", json.dumps(env))
        zf.writestr("steps.jsonl", "")
    assert findings(epi) == [
        "python.executable",
        "python.pid",
        "os.processor",
        "env.USER",
    ]
