"""Item 7: limitations doc current, strict easy to find."""

from pathlib import Path
import inspect
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def _current_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]


def test_limitations_pypi_version_matches_pyproject():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = pyproject["project"]["version"]
    text = (ROOT / "docs" / "KNOWN_LIMITATIONS.md").read_text(encoding="utf-8")
    # 4.6.3 is prepared in-tree but may not be on PyPI yet. The release-line
    # stamp must match pyproject; the published-on-PyPI stamp is separate.
    assert f"Current release line: **{version}**" in text


def test_published_version_is_not_still_called_unpublished():
    """A version that is on PyPI must not be described as pending anywhere.

    4.7.0 shipped through Trusted Publishing on 28 Oct 2026, but README-adjacent
    docs kept saying it was "prepared, not yet published" — so a reader could not
    tell whether `pip install epi-recorder` would get the attested release.
    """
    version = _current_version()
    stale = (
        "not yet published",
        "Until it is published",
        f"{version} is prepared",
        "prepared and version-bumped",
    )
    for rel in ("docs/RELEASING.md", "docs/KNOWN_LIMITATIONS.md", "README.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for phrase in stale:
            assert phrase not in text, f"{rel} still reads as unpublished: {phrase!r}"

    limitations = (ROOT / "docs" / "KNOWN_LIMITATIONS.md").read_text(encoding="utf-8")
    assert re.search(
        rf"published on PyPI: \*\*{re.escape(version)}\*\*", limitations, re.I
    ), f"KNOWN_LIMITATIONS must name {version} as the published version"


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
