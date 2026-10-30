"""Fail if a committed .epi file carries host detail to a recipient.

A sealed artifact is handed to a counterparty, and ``environment.json`` is one
of its members. It must not name the builder's machine: no interpreter path, no
argv, no PIDs, no CPU model, and no USER / HOME / PWD / PYTHONPATH /
VIRTUAL_ENV values.

Usage:
    python scripts/check_artifact_privacy.py            # scan every committed .epi
    python scripts/check_artifact_privacy.py --json     # machine-readable

Exit code 1 when any file leaks, so it can be wired into CI.

``tests/goldens/`` is skipped on purpose: those files exist to prove that old
spec versions still verify, so their bytes are frozen evidence, not samples.
"""

from __future__ import annotations

import argparse
import io
import json
import pathlib
import subprocess
import sys
import zipfile

MARKER = b"\n<!-- EPI_ZIP_PAYLOAD_START -->\n"

PY_KEYS = ("executable", "argv", "pid", "ppid")
OS_KEYS = ("processor", "memory")
ENV_KEYS = ("PYTHONPATH", "HOME", "USER", "USERNAME", "LOGNAME", "PWD", "OLDPWD", "VIRTUAL_ENV")

SKIP_DIRS = ("tests/goldens/",)


def _payload(data: bytes) -> bytes:
    idx = data.find(MARKER)
    return data[idx + len(MARKER):] if idx >= 0 else data


def findings(path: pathlib.Path) -> list[str]:
    """Return the host-detail fields present in this artifact (empty = clean)."""
    try:
        data = path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(_payload(data))) as zf:
            if "environment.json" not in zf.namelist():
                return []
            env = json.loads(zf.read("environment.json"))
    except Exception as exc:  # noqa: BLE001 - a broken sample is its own problem
        return [f"<unreadable: {type(exc).__name__}: {exc}>"]

    if not isinstance(env, dict):
        return ["<environment.json is not an object>"]

    found: list[str] = []
    python_info = env.get("python") if isinstance(env.get("python"), dict) else {}
    os_info = env.get("os") if isinstance(env.get("os"), dict) else {}
    env_vars = env.get("environment_variables") if isinstance(env.get("environment_variables"), dict) else {}

    found += [f"python.{k}" for k in PY_KEYS if k in python_info]
    found += [f"os.{k}" for k in OS_KEYS if k in os_info]
    found += [f"env.{k}" for k in ENV_KEYS if k in env_vars]
    return found


def committed_epi_files() -> list[pathlib.Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.epi"], capture_output=True, text=True, check=True
    ).stdout
    files = []
    for rel in out.splitlines():
        rel = rel.strip()
        if not rel or any(rel.startswith(prefix) for prefix in SKIP_DIRS):
            continue
        files.append(pathlib.Path(rel))
    return files


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--path", action="append", default=[], help="scan a specific file instead of git ls-files")
    args = parser.parse_args(argv)

    files = [pathlib.Path(p) for p in args.path] or committed_epi_files()
    report = {str(p): findings(p) for p in files}
    leaking = {p: f for p, f in report.items() if f}

    if args.json:
        print(json.dumps({"scanned": len(files), "leaking": leaking}, indent=2))
    else:
        print(f"scanned {len(files)} committed .epi file(s)")
        if leaking:
            print(f"LEAKING: {len(leaking)}")
            for path, fields in sorted(leaking.items()):
                print(f"  {path}: {', '.join(fields)}")
        else:
            print("clean: no host detail in any artifact")

    return 1 if leaking else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
