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
        try:
            shutil.copy2(path, out)
        except OSError as exc:
            # Windows: some hosts raise errno 22 on copy2 metadata (ADS/locks).
            if getattr(exc, "errno", None) != 22:
                raise
            shutil.copyfile(path, out)
        count += 1
    return count


def _purge_stale_pricing_dirs() -> None:
    """Remove legacy pricing/ directories that override flat pricing.html on CF Pages.

    Old deploys used pricing/index.html (Starter/Pro monthly SKUs). If that
    directory remains next to pricing.html, directory routes can win and show
    vaporware tiers while homepage links to /pricing for the sprint.
    """
    for base in TARGETS:
        stale = base / "pricing"
        if stale.is_dir() and not (stale / "index.html").exists():
            # empty dir leftover
            shutil.rmtree(stale, ignore_errors=True)
            print(f"Removed empty stale {stale.relative_to(ROOT)}")
        elif stale.is_dir():
            # Always remove directory form — canonical is pricing.html only
            shutil.rmtree(stale, ignore_errors=True)
            print(f"Removed stale directory {stale.relative_to(ROOT)} (use pricing.html)")
    # Also purge under SOURCE if ever created by mistake
    src_stale = SOURCE / "pricing"
    if src_stale.is_dir():
        shutil.rmtree(src_stale, ignore_errors=True)
        print("Removed website/pricing/ directory (canonical is website/pricing.html)")


def sync() -> None:
    if not SOURCE.is_dir():
        raise SystemExit(f"Canonical website/ not found at {SOURCE}")

    total = 0
    for dest in TARGETS:
        preserve = PRESERVE_UNDER_STATIC if dest.name == "static" else set()
        n = _copy_tree(SOURCE, dest, preserve_top=preserve)
        print(f"Synced {n} files -> {dest.relative_to(ROOT)}")
        total += n

    _purge_stale_pricing_dirs()

    # Sync .well-known canonical to root and assets mirrors (drift fixed P3)
    for mirror in [ROOT / ".well-known", ROOT / "assets" / "well-known"]:
        src_well = SOURCE / ".well-known"
        if src_well.is_dir():
            for p in src_well.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(src_well)
                    out = mirror / rel
                    out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, out)
            print(f"Synced .well-known -> {mirror.relative_to(ROOT)}")

    # Ensure portal-only dirs exist
    static = ROOT / "verify_portal" / "static"
    (static / "auth").mkdir(parents=True, exist_ok=True)
    (static / "admin").mkdir(parents=True, exist_ok=True)
    print(f"Done. {total} file copies total. Source of truth: website/")


if __name__ == "__main__":
    sync()
    sys.exit(0)
