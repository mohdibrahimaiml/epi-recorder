"""WP-FIX-2: the site version has one source (pyproject.toml).

The footer/banner stamps across website/ must equal the package version, and
the stale release marker must be gone. pyproject.toml is the source of truth;
this test fails the moment they drift (deliberately NOT build-time tokens:
GitHub Pages serves website/ raw, so literals must be right in the source).
"""

from __future__ import annotations

import pathlib
import re
import tomllib

REPO = pathlib.Path(__file__).resolve().parents[1]
WEBSITE = REPO / "website"

STALE_MARKERS = ("v4.5.0",)

# Release stamps and the exact shape each one takes on the pages.
STAMP_PATTERNS = (
    r"MIT License · v\d+\.\d+\.\d+",
    r"v\d+\.\d+\.\d+ on PyPI",
    r"v\d+\.\d+\.\d+ · envelope-v2",
)


def _version() -> str:
    with (REPO / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def test_security_contact_matches():
    """One contact address: SECURITY.md must match security.txt."""
    import re

    sec = (REPO / "SECURITY.md").read_text(encoding="utf-8", errors="ignore")
    txt = (WEBSITE / ".well-known" / "security.txt").read_text(
        encoding="utf-8", errors="ignore"
    )
    m = re.search(r"Contact:\s*mailto:(\S+)", txt)
    assert m, "security.txt has no Contact"
    assert m.group(1) in sec, "SECURITY.md contact differs from security.txt"
    assert "business days" in sec
    for banned in ("zero-knowledge", "Zero-knowledge", "same as Signal"):
        assert banned not in sec


def test_no_stale_version_markers():
    offenders = []
    for path in sorted(WEBSITE.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in STALE_MARKERS:
            if marker in text:
                offenders.append(f"{path.relative_to(WEBSITE)}: {marker}")
    assert not offenders, "stale version markers:\n" + "\n".join(offenders)


def test_release_stamps_match_pyproject():
    version = _version()
    bad = []
    for path in sorted(WEBSITE.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in STAMP_PATTERNS:
            for m in re.findall(pattern, text):
                if version not in m:
                    bad.append(f"{path.relative_to(WEBSITE)}: {m}")
    assert bad == [], "release stamps disagree with pyproject.toml"
    # And at least one stamp of each shape exists (test guards real copy).
    joined = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in WEBSITE.rglob("*.html")
    )
    for pattern in STAMP_PATTERNS:
        assert re.search(pattern, joined), f"no instances of {pattern}"
