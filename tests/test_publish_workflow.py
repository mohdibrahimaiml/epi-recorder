"""WP-SUPPLY-1: the PyPI publish workflow must stay correct.

Publishing 4.6.2+ works only if .github/workflows/publish-pypi.yml:
  - runs on release: published,
  - uses the "pypi" environment with id-token: write (Trusted Publishing),
  - builds in a clean checkout of the release tag (not the merge commit),
  - refuses a tag/version mismatch (v4.6.2 tag must build 4.6.2 files),
  - uploads via pypa/gh-action-pypi-publish (no token; attestations on).
If any of that regresses, a GitHub release silently never reaches PyPI.

Deliberately stdlib-only (no pyyaml): this test also runs inside the
Windows-installer release gate, whose env lacks pyyaml — an import error
there once blocked the .exe. A tiny section reader is enough for this
machine-written file.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "publish-pypi.yml"


def _text() -> str:
    assert WORKFLOW.is_file(), "publish-pypi.yml missing: releases would never reach PyPI"
    return WORKFLOW.read_text(encoding="utf-8", errors="ignore")


def _section(text: str, header: str) -> str:
    """Return the indented block under a top-level `header:` line."""
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == header)
    base = len(lines[start]) - len(lines[start].lstrip())
    out = []
    for line in lines[start + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= base:
            break
        out.append(line)
    return "\n".join(out)


def test_publish_workflow_exists_and_triggers_on_release():
    text = _text()
    on = _section(text, "on:")
    assert "release:" in on
    assert "published" in on


def test_publish_workflow_uses_trusted_publishing():
    text = _text()
    assert "environment: pypi" in text
    assert "id-token: write" in text


def test_publish_workflow_builds_tag_and_gates_version():
    text = _text()
    assert "github.event.release.tag_name" in text, "must check out the release tag"
    assert "pypa/gh-action-pypi-publish" in text, "must upload via Trusted Publishing action"
    assert "twine check" in text
    for token in ["tag_name", "pyproject", "exit 1"]:
        assert token in text, f"version/tag mismatch gate looks broken (missing {token!r})"


def _package_version() -> str:
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
    for line in pyproject.splitlines():
        if line.startswith("version"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise AssertionError("pyproject.toml has no version")


def test_releasing_doc_exists():
    doc = REPO / "docs" / "RELEASING.md"
    assert doc.is_file(), "docs/RELEASING.md missing"
    text = doc.read_text(encoding="utf-8", errors="ignore")
    example_tag = f"v{_package_version()}"
    for token in ["publish-pypi", "Trusted Publishing", example_tag, "Manual Deploy"]:
        assert token in text, f"RELEASING.md missing {token!r}"
