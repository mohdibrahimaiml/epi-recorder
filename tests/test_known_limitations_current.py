"""Item 7: limitations doc current, strict easy to find."""

from pathlib import Path
import inspect
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_limitations_pypi_version_matches_pyproject():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = pyproject["project"]["version"]
    text = (ROOT / "docs" / "KNOWN_LIMITATIONS.md").read_text(encoding="utf-8")
    assert f"Current published line: **{version}**" in text


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
