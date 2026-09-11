#!/usr/bin/env python3
"""Install release-gate dependencies WITHOUT installing the package itself.

Single source of truth: ``pyproject.toml`` (project.dependencies + the
``test`` extra). A hardcoded copy of these pins used to live in
``.github/workflows/release-gate.yml`` and silently drifted behind
(``cryptography<44``, ``typer<0.26``, ``rich<14`` long after the repo moved
on), so CI tested against older libraries than the code targets.

Browser pair (playwright/pytest-playwright) is excluded: the gate deselects
browser tests (``-m "not browser"``).

Usage:
    python scripts/ci-install-deps.py [--print-only]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Skipped: gate runs `pytest -m "not browser"`, so these are dead weight
# (playwright downloads whole browsers on install).
SKIP_PREFIXES = ("playwright", "pytest-playwright")


def resolve_requirements(repo_root: Path) -> list[str]:
    import tomllib

    data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    reqs: list[str] = list(data["project"]["dependencies"])
    test_extra: list[str] = data["project"]["optional-dependencies"]["test"]
    reqs.extend(r for r in test_extra if not r.startswith(SKIP_PREFIXES))
    return reqs


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    reqs = resolve_requirements(repo_root)
    if "--print-only" in argv:
        print("\n".join(reqs))
        return 0
    subprocess.run([sys.executable, "-m", "pip", "install", *reqs], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
