"""WP-SUPPLY-1: the PyPI publish workflow must stay correct.

Publishing 4.6.1+ works only if .github/workflows/publish-pypi.yml:
  - runs on release: published,
  - uses the "pypi" environment with id-token: write (Trusted Publishing),
  - builds in a clean checkout of the release tag (not the merge commit),
  - refuses a tag/version mismatch (v4.6.1 tag must build 4.6.1 files),
  - uploads via pypa/gh-action-pypi-publish (no token; attestations on).
If any of that regresses, a GitHub release silently never reaches PyPI.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "publish-pypi.yml"


def _load() -> dict:
    assert WORKFLOW.is_file(), "publish-pypi.yml missing: releases would never reach PyPI"
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # YAML 1.1 parses the `on:` key as boolean True.
    on = wf.get("on", wf.get(True, {}))
    wf["on"] = on
    return wf


def test_publish_workflow_exists_and_triggers_on_release():
    wf = _load()
    assert wf.get("on", {}).get("release", {}).get("types") == ["published"]


def test_publish_workflow_uses_trusted_publishing():
    wf = _load()
    jobs = wf.get("jobs", {})
    assert jobs, "no jobs in publish-pypi.yml"
    found_env = False
    for name, job in jobs.items():
        assert job.get("environment") == "pypi", f"job {name}: must use the pypi environment"
        found_env = True
        perms = job.get("permissions", {})
        assert perms.get("id-token") == "write", f"job {name}: needs id-token: write for OIDC"
    assert found_env


def test_publish_workflow_builds_tag_and_gates_version():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "github.event.release.tag_name" in text, "must check out the release tag"
    assert "pypa/gh-action-pypi-publish" in text, "must upload via Trusted Publishing action"
    assert "twine check" in text
    for token in ["tag_name", "pyproject", "exit 1"]:
        assert token in text, f"version/tag mismatch gate looks broken (missing {token!r})"


def test_releasing_doc_exists():
    doc = REPO / "docs" / "RELEASING.md"
    assert doc.is_file(), "docs/RELEASING.md missing"
    text = doc.read_text(encoding="utf-8")
    for token in ["publish-pypi", "Trusted Publishing", "v4.6.1", "Manual Deploy"]:
        assert token in text, f"RELEASING.md missing {token!r}"
