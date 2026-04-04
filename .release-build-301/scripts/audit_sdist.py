"""
Audit built source distributions for expected packaged demo assets.

This keeps GitHub/source-release notebooks honest without forcing them into
runtime wheels. It also helps catch accidental inclusion of local temp files.
"""

from __future__ import annotations

import argparse
import sys
import tarfile
from pathlib import Path


REQUIRED_NOTEBOOKS = {
    "colab_demo.ipynb",
    "EPI NEXUA VENTURES.ipynb",
}


def audit_sdist(sdist_path: Path) -> list[str]:
    issues: list[str] = []

    with tarfile.open(sdist_path, "r:gz") as tf:
        member_names = [member.name for member in tf.getmembers() if member.isfile()]

    notebook_basenames = {
        Path(member_name).name
        for member_name in member_names
        if member_name.lower().endswith(".ipynb")
    }

    missing_notebooks = sorted(REQUIRED_NOTEBOOKS - notebook_basenames)
    unexpected_notebooks = sorted(notebook_basenames - REQUIRED_NOTEBOOKS)

    for notebook_name in missing_notebooks:
        issues.append(f"missing packaged notebook: {notebook_name}")

    for notebook_name in unexpected_notebooks:
        issues.append(f"unexpected packaged notebook: {notebook_name}")

    for member_name in member_names:
        path = Path(member_name)
        if any(part.startswith(".tmp") for part in path.parts):
            issues.append(f"unexpected temporary artifact: {member_name}")

    return issues


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit source distributions for expected demo assets.")
    parser.add_argument("sdists", nargs="+", help="One or more .tar.gz files to audit.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    failed = False

    for sdist_arg in args.sdists:
        sdist_path = Path(sdist_arg)
        if not sdist_path.exists():
            print(f"[FAIL] sdist not found: {sdist_path}")
            failed = True
            continue

        issues = audit_sdist(sdist_path)
        if issues:
            failed = True
            print(f"[FAIL] {sdist_path}")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print(f"[OK] {sdist_path}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
