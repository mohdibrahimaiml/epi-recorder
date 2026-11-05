"""The README is also the PyPI long description. Keep its links honest.

Two failure modes this catches:

1. A doc moves or is deleted and the README keeps pointing at it. Every link is
   an absolute github.com/raw.githubusercontent URL (PyPI does not resolve
   relative links), so the test maps each one back to a file in the repo and
   checks it exists.
2. A hardcoded version badge. The PyPI badge is already dynamic; a second
   hardcoded one rots at the next release.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"

BLOB = "https://github.com/mohdibrahimaiml/epi-recorder/blob/main/"
TREE = "https://github.com/mohdibrahimaiml/epi-recorder/tree/main/"
RAW = "https://raw.githubusercontent.com/mohdibrahimaiml/epi-recorder/main/"

LINK = re.compile(r"\]\((?P<url>[^)\s]+)\)")
IMAGE = re.compile(r'<img[^>]+src="(?P<url>[^"]+)"')


def _text() -> str:
    return README.read_text(encoding="utf-8")


def _urls() -> list[str]:
    return [m.group("url") for m in LINK.finditer(_text())] + [
        m.group("url") for m in IMAGE.finditer(_text())
    ]


def _to_path(url: str) -> Path | None:
    if url.startswith(BLOB):
        return REPO / url[len(BLOB):]
    if url.startswith(TREE):
        return REPO / url[len(TREE):]
    if url.startswith(RAW):
        return REPO / url[len(RAW):]
    return None


def test_readme_exists_and_stays_readable():
    text = _text()
    assert text.startswith("<div"), "the hero logo block should stay first"
    lines = text.count("\n") + 1
    assert lines < 320, f"README is {lines} lines; it was 422 before the rewrite"


def test_every_repo_link_resolves():
    missing = []
    for url in _urls():
        path = _to_path(url)
        if path is not None and not path.exists():
            missing.append(url)
    assert not missing, "README links point at paths that do not exist: " + ", ".join(missing)


def test_no_relative_markdown_links_break_pypi():
    """PyPI does not resolve relative links, so they must all be absolute."""
    relative = [
        url
        for url in _urls()
        if not url.startswith(("http://", "https://", "#"))
    ]
    assert not relative, "relative links render as 404s on PyPI: " + ", ".join(relative)


def test_no_hardcoded_version_badge():
    text = _text()
    assert "badge/version-v" not in text, (
        "drop the hardcoded version badge; the PyPI badge is already dynamic"
    )
    assert "img.shields.io/pypi/v/epi-recorder" in text


def test_in_page_anchors_exist():
    text = _text()
    headings = re.findall(r"^#{1,4}\s+(.+)$", text, re.M)

    def slug(heading: str) -> str:
        value = heading.replace("`", "").lower()
        value = re.sub(r"[^a-z0-9\s-]", "", value)
        return re.sub(r"\s+", "-", value.strip())

    available = {slug(h) for h in headings}
    anchors = {url[1:] for url in _urls() if url.startswith("#") and len(url) > 1}
    missing = sorted(a for a in anchors if a not in available)
    assert not missing, f"anchors with no heading: {missing} (have {sorted(available)})"


def test_required_sections_survive():
    text = _text()
    for needle in (
        "## Who this is for",
        "## What a `.epi` file is",
        "## Verify a file you received",
        "## Open core",
        "## Docs",
        "## Contributing, security, support",
    ):
        assert needle in text, needle


def test_honest_limit_is_near_the_top():
    text = _text()
    position = text.find("What this proves, and what it does not")
    assert position != -1
    assert position < len(text) // 6, "the limit belongs in the first screen, not buried"


def test_extras_documented_actually_exist():
    """Every `epi-recorder[x]` named in the README must be a real extra."""
    import tomllib

    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    extras = set(project["project"].get("optional-dependencies", {}))
    named = set(re.findall(r"epi-recorder\[([a-z0-9-]+)\]", _text()))
    assert named, "the install section should name at least one extra"
    unknown = sorted(named - extras)
    assert not unknown, f"README documents extras that do not exist: {unknown}"
