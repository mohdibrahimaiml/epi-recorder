"""
Audit built wheel artifacts for unexpected packaged files.

This is intentionally conservative: it blocks obviously suspicious entries
that should never ship in runtime wheels, such as stray test modules,
temporary databases, or log files leaked from old build outputs.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path


EXPECTED_TOP_LEVEL = {
    "epi_analyzer",
    "epi_cli",
    "epi_core",
    "epi_gateway",
    "epi_postinstall.py",
    "epi_recorder",
    "epi_viewer_static",
    "web_viewer",
    "pytest_epi",
}

REQUIRED_RUNTIME_MEMBERS = {
    "epi_viewer_static/crypto.js",
    "web_viewer/index.html",
    "web_viewer/jszip.min.js",
    "web_viewer/app.js",
    "web_viewer/styles.css",
}

SUSPICIOUS_RUNTIME_BASENAME_PATTERNS = (
    re.compile(r"^test_.*\.py$", re.IGNORECASE),
    re.compile(r".*_temp\.db$", re.IGNORECASE),
    re.compile(r"^stdout\.log$", re.IGNORECASE),
    re.compile(r"^stderr\.log$", re.IGNORECASE),
    re.compile(r"^thumbs\.db$", re.IGNORECASE),
)


def _is_allowed_dist_info(top_level_name: str) -> bool:
    return top_level_name.endswith(".dist-info")


def _matches_suspicious_pattern(basename: str) -> bool:
    return any(pattern.match(basename) for pattern in SUSPICIOUS_RUNTIME_BASENAME_PATTERNS)


def audit_wheel(wheel_path: Path) -> list[str]:
    issues: list[str] = []

    with zipfile.ZipFile(wheel_path, "r") as zf:
        members = set(zf.namelist())
        for member_name in zf.namelist():
            normalized = member_name.rstrip("/")
            if not normalized:
                continue

            parts = normalized.split("/")
            top_level = parts[0]

            if top_level not in EXPECTED_TOP_LEVEL and not _is_allowed_dist_info(top_level):
                issues.append(f"unexpected top-level entry: {normalized}")
                continue

            basename = Path(normalized).name
            if _matches_suspicious_pattern(basename):
                issues.append(f"suspicious runtime file: {normalized}")

        for required in sorted(REQUIRED_RUNTIME_MEMBERS):
            if required not in members:
                issues.append(f"missing required runtime asset: {required}")

    return issues


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit wheel contents for packaging leaks.")
    parser.add_argument("wheels", nargs="+", help="One or more .whl files to audit.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    failed = False

    for wheel_arg in args.wheels:
        wheel_path = Path(wheel_arg)
        if not wheel_path.exists():
            print(f"[FAIL] wheel not found: {wheel_path}")
            failed = True
            continue

        issues = audit_wheel(wheel_path)
        if issues:
            failed = True
            print(f"[FAIL] {wheel_path}")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print(f"[OK] {wheel_path}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
