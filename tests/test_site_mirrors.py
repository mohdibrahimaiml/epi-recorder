"""Every file the build copies ships from website/ to its mirrors unchanged.

The verifier fix (#233) changed `website/js/home-verify.js` but not the copies
the deploy actually serves (`site/`, `epi-official/`), so the live page kept
printing the old line. This compares the files the build copies verbatim and
fails when one of them drifts.

`site/` is compared in full, because it is the directory Cloudflare Pages
publishes: everything under `website/` must be there, byte for byte. Comparing
only `js/` and `css/` is what let `cases/index.html` keep loading jszip from
cdnjs in the mirrors for months while `website/` used the vendored copy.

`verify_portal/static/` is built from `website/` at startup
(`verify_portal.main._sync_website_static`), and its `js/` is not tracked, so it
is not checked here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "website"
MIRRORS = [
    (REPO / "site", "site"),
    (REPO / "epi-official", "epi-official"),
]
PATTERNS = ("js/*.js", "css/*.css")


def shipped_files(src: Path):
    """Same rules as scripts/sync_website.py: no dotfiles (except .nojekyll),
    and only README.md may ship as Markdown."""
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        if path.name.startswith(".") and path.name != ".nojekyll":
            continue
        if path.suffix.lower() == ".md" and path.name != "README.md":
            continue
        yield rel, path


def test_the_deploy_directory_matches_the_source():
    """`site/` is what is served. A stale copy is a stale site."""
    site = REPO / "site"
    drift = []
    checked = 0
    for rel, src in shipped_files(SOURCE):
        checked += 1
        target = site / rel
        if not target.is_file():
            drift.append(f"site/{rel.as_posix()}: missing")
        elif target.read_bytes() != src.read_bytes():
            drift.append(f"site/{rel.as_posix()}: differs from website/")
    assert checked > 100, f"only {checked} source files found; is website/ intact?"
    assert not drift, "run python scripts/sync_website.py:\n" + "\n".join(drift)


@pytest.mark.parametrize("mirror,name", MIRRORS, ids=[name for _path, name in MIRRORS])
def test_scripts_and_stylesheets_match_the_source(mirror: Path, name: str) -> None:
    drift = []
    for pattern in PATTERNS:
        for src in sorted(SOURCE.glob(pattern)):
            target = mirror / src.relative_to(SOURCE)
            if not target.is_file():
                drift.append(f"{name}/{src.relative_to(SOURCE)}: missing")
            elif target.read_bytes() != src.read_bytes():
                drift.append(f"{name}/{src.relative_to(SOURCE)}: differs from website/")
    assert not drift, "run python scripts/sync_website.py:\n" + "\n".join(drift)
