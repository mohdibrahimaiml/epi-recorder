"""Item 7: limitations doc current, strict easy to find."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _current_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]


def test_limitations_pypi_version_matches_pyproject():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = pyproject["project"]["version"]
    text = (ROOT / "docs" / "KNOWN_LIMITATIONS.md").read_text(encoding="utf-8")
    # The release line tracks pyproject; the published-on-PyPI stamp may be one
    # release behind while a prepared release waits for its upload.
    assert f"Current release line: **{version}**" in text


def test_published_version_is_never_claimed_before_its_upload():
    """A prepared release must not be described as already on PyPI.

    The release line comes from pyproject. When it differs from the version the
    page names as published, the page must say the upload is pending; when they
    match, it must not still read as unpublished.
    """
    version = _current_version()
    limitations = (ROOT / "docs" / "KNOWN_LIMITATIONS.md").read_text(encoding="utf-8")
    match = re.search(
        r"published on PyPI: \*\*(\d+\.\d+\.\d+)\*\*", limitations, re.I
    )
    assert match, "KNOWN_LIMITATIONS must name the published PyPI version"
    published = match.group(1)

    if published == version:
        for rel in ("docs/RELEASING.md", "docs/KNOWN_LIMITATIONS.md", "README.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            for phrase in (
                "not yet published",
                "Until it is published",
                f"{version} is prepared",
                "prepared and version-bumped",
            ):
                assert phrase not in text, f"{rel} still reads as unpublished: {phrase!r}"
    else:
        assert "pending" in limitations.lower(), (
            f"KNOWN_LIMITATIONS says {published} is published while pyproject is "
            f"{version}, so it must say the {version} upload is pending"
        )


def test_limitations_names_sprint_gaps():
    text = (ROOT / "docs" / "KNOWN_LIMITATIONS.md").read_text(encoding="utf-8")
    for phrase in [
        "epi verify run.epi --policy strict",
        "async-enqueue",
        "501",
        "controls_failed",
        "content_truncated",
        "presence-only",
    ]:
        assert phrase in text


def test_strict_easy_to_find():
    src = (ROOT / "epi_cli" / "verify.py").read_text(encoding="utf-8")
    assert "--policy strict" in src or "strict (claims" in src
    contract = (ROOT / "docs" / "VERIFICATION_CONTRACT.md").read_text(encoding="utf-8")
    assert "--policy strict" in contract
