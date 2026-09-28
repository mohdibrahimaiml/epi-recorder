"""Single-source sync for the browser viewer JS mirrors.

Canonical source: web_viewer/app.js
Mirrors (deployed sites): site/viewer/app.js, website/viewer/app.js

The packed/embedded viewer already reads only the canonical copy
(epi_core.viewer_assets.load_viewer_assets); these mirrors exist for the
hosted sites and must stay byte-identical. Run after any web_viewer change:

    python scripts/sync_viewer_mirrors.py        # copy canonical -> mirrors
    python scripts/sync_viewer_mirrors.py --check  # CI: fail if diverged
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CANONICAL = REPO / "web_viewer" / "app.js"
MIRRORS = [REPO / "site" / "viewer" / "app.js", REPO / "website" / "viewer" / "app.js"]


def check() -> list[str]:
    canonical = CANONICAL.read_text(encoding="utf-8")
    return [str(m) for m in MIRRORS if m.read_text(encoding="utf-8") != canonical]


def sync() -> list[str]:
    canonical = CANONICAL.read_bytes()
    updated = []
    for mirror in MIRRORS:
        if not mirror.exists() or mirror.read_bytes() != canonical:
            mirror.parent.mkdir(parents=True, exist_ok=True)
            mirror.write_bytes(canonical)
            updated.append(str(mirror))
    return updated


def main(argv: list[str]) -> int:
    if "--check" in argv:
        diverged = check()
        if diverged:
            print("Viewer mirrors diverged from web_viewer/app.js:")
            for path in diverged:
                print(f"  - {path}")
            print("Run: python scripts/sync_viewer_mirrors.py")
            return 1
        print("Viewer mirrors in sync.")
        return 0
    updated = sync()
    if updated:
        print("Synced viewer mirrors:")
        for path in updated:
            print(f"  - {path}")
    else:
        print("Viewer mirrors already in sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
