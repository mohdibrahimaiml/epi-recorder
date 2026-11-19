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

# Never copy these into verify_portal/static. The portal must not answer /docs
# (tests/test_verify_portal.py asserts 404, because a docs page hands an
# unauthenticated caller a map of the API). epilabs.org/docs is served by
# Cloudflare Pages from site/, not by the legacy Render portal.
SKIP_UNDER_STATIC = {"docs"}


# Only README.md may ship as Markdown in the public outputs. Internal *.md
# files (e.g. outreach/sales templates) must never be copied to a deployed
# target, even if added under website/ by mistake.
PUBLIC_MD_ALLOWLIST = {"README.md"}


def _is_excluded_public_md(path: Path) -> bool:
    return path.suffix.lower() == ".md" and path.name not in PUBLIC_MD_ALLOWLIST


def _copy_tree(
    src: Path,
    dest: Path,
    *,
    preserve_top: set[str] | None = None,
    skip_top: set[str] | None = None,
) -> int:
    preserve_top = preserve_top or set()
    skip_top = skip_top or set()
    if not src.is_dir():
        raise SystemExit(f"Source missing: {src}")
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in src.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(src)
        if skip_top and rel.parts and rel.parts[0] in skip_top:
            continue
        # skip junk
        if path.name.startswith(".") and path.name not in {".nojekyll"}:
            if path.name == ".nojekyll":
                pass
            else:
                continue
        if _is_excluded_public_md(path):
            continue
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


def _purge_excluded_public_files() -> None:
    """Remove internal files that must never be publicly deployed.

    `website/outreach.md` (sales templates) was previously synced into the
    public targets. The copy step above no longer copies it, but syncs never
    delete, so remove the stale copies here.
    """
    for base in TARGETS:
        stale = base / "outreach.md"
        if stale.is_file():
            stale.unlink()
            print(f"Removed {stale.relative_to(ROOT)} (internal file, not for public output)")


def _purge_portal_private_pages() -> None:
    """Delete copies of pages the portal must not serve.

    A sync never deletes, so an earlier run that copied website/docs/ into
    verify_portal/static/ would keep answering /docs — the one path the portal
    test requires to be absent.
    """
    for base in TARGETS:
        if base.name != "static":
            continue
        stale = base / "docs"
        if stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)
            print(f"Removed {stale.relative_to(ROOT)} (portal must not serve /docs)")


def sync() -> None:
    if not SOURCE.is_dir():
        raise SystemExit(f"Canonical website/ not found at {SOURCE}")

    total = 0
    for dest in TARGETS:
        is_portal = dest.name == "static"
        preserve = PRESERVE_UNDER_STATIC if is_portal else set()
        skip = SKIP_UNDER_STATIC if is_portal else set()
        n = _copy_tree(SOURCE, dest, preserve_top=preserve, skip_top=skip)
        print(f"Synced {n} files -> {dest.relative_to(ROOT)}")
        total += n

    _purge_stale_pricing_dirs()
    _purge_excluded_public_files()
    _purge_portal_private_pages()

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
