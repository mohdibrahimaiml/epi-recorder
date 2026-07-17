#!/usr/bin/env python3
"""Sync the single website source of truth into deploy/runtime targets.

Canonical source:  website/
Targets:
  - verify_portal/static/  (Render / FastAPI static + API-served pages)
  - epi-official/          (legacy name; kept in sync so old docs still work)

Portal-only paths under verify_portal/static that are NOT overwritten if missing
from website: auth/, admin/ (and any other extra server-only assets).

Usage:
  python scripts/sync_website.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "website"
TARGETS = [
    ROOT / "verify_portal" / "static",
    ROOT / "epi-official",
    # Cloudflare Pages dashboard is configured with output directory "site"
    # (no build command). Keep this as a generated mirror of website/.
    ROOT / "site",
]

# Never delete these under verify_portal/static (portal-only)
PRESERVE_UNDER_STATIC = {
    "auth",
    "admin",
    "render.yaml",  # if present
}


def _copy_tree(src: Path, dest: Path, *, preserve_top: set[str] | None = None) -> int:
    preserve_top = preserve_top or set()
    if not src.is_dir():
        raise SystemExit(f"Source missing: {src}")
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in src.rglob("*"):
        if path.is_dir():
            continue
        # skip junk
        if path.name.startswith(".") and path.name not in {".nojekyll"}:
            if path.name == ".nojekyll":
                pass
            else:
                continue
        rel = path.relative_to(src)
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
        count += 1
    return count


def sync() -> None:
    if not SOURCE.is_dir():
        raise SystemExit(f"Canonical website/ not found at {SOURCE}")

    total = 0
    for dest in TARGETS:
        preserve = PRESERVE_UNDER_STATIC if dest.name == "static" else set()
        n = _copy_tree(SOURCE, dest, preserve_top=preserve)
        print(f"Synced {n} files → {dest.relative_to(ROOT)}")
        total += n

    # Ensure portal-only dirs exist
    static = ROOT / "verify_portal" / "static"
    (static / "auth").mkdir(parents=True, exist_ok=True)
    (static / "admin").mkdir(parents=True, exist_ok=True)
    print(f"Done. {total} file copies total. Source of truth: website/")


if __name__ == "__main__":
    sync()
    sys.exit(0)
