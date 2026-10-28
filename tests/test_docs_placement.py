"""Docs placement: `docs/` is published, so nothing internal may live in it.

`docs/` is served as a website (`spec.epilabs.org`) and every file in it is
world-readable. Internal material — founder ops, capacity and pricing math,
execution plans, agent prompts, internal design notes — lives in the repo-root
`internal/` tree instead, and no public doc may link into it.

This test exists because that boundary was only a convention and it was being
violated: the enterprise briefing, the docs map, ARCHITECTURE.md, several ADRs,
CLOUD/DATA-RETENTION/WITNESS/ROADMAP and SUPPORT.md all linked into `internal/`,
a self-declared internal design note sat in the public docs index, and the
bank-readiness execution plan was being served as a public web page at
`https://spec.epilabs.org/internal/BANK-READINESS-EXECUTION-PLAN.md`.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INTERNAL = REPO / "internal"

_MD_LINK = re.compile(r"\]\(([^)\s]+)\)")
_HTML_LINK = re.compile(r'href="([^"]+)"')
_SKIP = ("http://", "https://", "mailto:", "data:", "#")


def _public_docs() -> list[Path]:
    """Everything a visitor can read: the repo front page, the published docs
    tree, and the website."""
    candidates = [
        *REPO.glob("*.md"),
        *REPO.glob("docs/**/*.md"),
        *REPO.glob("docs/**/*.html"),
        *REPO.glob("website/**/*.html"),
    ]
    return sorted(path for path in candidates if path.is_file())


def _targets(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    found = _MD_LINK.findall(text) + _HTML_LINK.findall(text)
    return [
        item
        for item in found
        if item and not item.startswith(_SKIP) and "{{" not in item
    ]


def _path_part(target: str) -> str:
    return target.split("#", 1)[0].split("?", 1)[0]


def test_no_internal_material_sits_under_the_published_docs_tree():
    assert not (REPO / "docs" / "internal").exists(), (
        "docs/internal/ is served publicly at spec.epilabs.org — internal docs "
        "belong in the repo-root internal/ tree"
    )
    assert not (REPO / "docs" / "design" / "org-trust-bundle.md").exists(), (
        "the org trust bundle design note is internal"
    )

    assert (INTERNAL / "design" / "org-trust-bundle.md").is_file(), (
        "internal/design/org-trust-bundle.md is missing (code cites it as the spec)"
    )


def test_private_planning_docs_are_not_in_this_public_repo():
    # The repository is public, so planning, operations and assessment docs
    # live in a private repository instead.
    leaked = [
        name
        for name in (
            "BANK-READINESS-ASSESSMENT.md",
            "BANK-READINESS-EXECUTION-PLAN.md",
            "cloud-ops.md",
            "scope.md",
            "swallow-audit.md",
            "prompts",
        )
        if (INTERNAL / name).exists()
    ]
    assert not leaked, f"private docs are back in the public repo: internal/{leaked}"


def test_no_public_doc_links_into_the_internal_tree():
    offenders: list[str] = []
    for path in _public_docs():
        for target in _targets(path):
            target_path = _path_part(target)
            if not target_path:
                continue
            resolved = (path.parent / target_path).resolve()
            if resolved == INTERNAL or INTERNAL in resolved.parents:
                offenders.append(f"{path.relative_to(REPO)} -> {target}")

    assert not offenders, (
        "Public docs must not link into internal/ (docs/ is published as a "
        f"website): {offenders}"
    )


def test_the_public_docs_index_has_no_dead_links():
    index = REPO / "docs" / "README.md"
    missing = [
        target
        for target in _targets(index)
        if _path_part(target) and not (index.parent / _path_part(target)).resolve().exists()
    ]
    assert not missing, f"docs/README.md links to files that do not exist: {missing}"


def test_the_internal_index_accounts_for_every_internal_doc():
    listing = (INTERNAL / "README.md").read_text(encoding="utf-8")
    unlisted = []
    for path in sorted(INTERNAL.rglob("*.md")):
        if path.name == "README.md":
            continue
        relative = path.relative_to(INTERNAL).as_posix()
        if path.name in listing or f"{relative.split('/')[0]}/" in listing:
            continue
        unlisted.append(relative)
    assert not unlisted, f"internal/README.md does not mention: {unlisted}"
