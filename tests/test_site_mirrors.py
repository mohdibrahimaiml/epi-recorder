"""Every script and stylesheet ships from website/ to its mirrors unchanged.

The verifier fix (#233) changed `website/js/home-verify.js` but not the copies
the deploy actually serves (`site/`, `epi-official/`), so the live page kept
printing the old line. This compares the files the build copies verbatim and
fails when one of them drifts.

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
