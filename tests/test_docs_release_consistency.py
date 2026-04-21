from __future__ import annotations

from pathlib import Path

from epi_core import __version__ as core_version


REPO_ROOT = Path(__file__).resolve().parent.parent
CURRENT_PUBLIC_DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "AGT-IMPORT-QUICKSTART.md",
    REPO_ROOT / "docs" / "CLI.md",
    REPO_ROOT / "docs" / "CONNECT.md",
    REPO_ROOT / "docs" / "EPI-CODEBASE-WALKTHROUGH.md",
    REPO_ROOT / "docs" / "EPI-DOC-v4.0.1.md",
    REPO_ROOT / "docs" / "FRAMEWORK-INTEGRATIONS-5-MINUTES.md",
    REPO_ROOT / "docs" / "POLICY.md",
    REPO_ROOT / "docs" / "PYTEST-AGENT-REGRESSIONS.md",
    REPO_ROOT / "docs" / "SELF-HOSTED-RUNBOOK.md",
    REPO_ROOT / "docs" / "SHARE-A-FAILURE.md",
    REPO_ROOT / "docs" / "index.html",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_current_public_docs_point_to_runtime_release():
    expected = f"v{core_version}"

    assert expected in _read(REPO_ROOT / "README.md")
    assert expected in _read(REPO_ROOT / "docs" / "CLI.md")
    assert expected in _read(REPO_ROOT / "docs" / "AGT-IMPORT-QUICKSTART.md")
    assert expected in _read(REPO_ROOT / "docs" / "EPI-DOC-v4.0.1.md")
    assert f"EPI Recorder {expected}" in _read(REPO_ROOT / "docs" / "index.html")
    assert f"Specification v{core_version}" in _read(REPO_ROOT / "docs" / "EPI-SPEC.md")


def test_current_public_docs_have_no_stale_current_release_mentions():
    stale_markers = ("v3.0.3", "v3.0.2")

    offenders: list[str] = []
    for path in CURRENT_PUBLIC_DOCS:
        text = _read(path)
        if any(marker in text for marker in stale_markers):
            offenders.append(str(path))

    assert not offenders, f"Stale release markers found in current public docs: {offenders}"


def test_current_public_docs_describe_envelope_format():
    readme = _read(REPO_ROOT / "README.md")
    walkthrough = _read(REPO_ROOT / "docs" / "EPI-CODEBASE-WALKTHROUGH.md")
    spec = _read(REPO_ROOT / "docs" / "EPI-SPEC.md")

    assert "Wrap with EPI1 Envelope" in readme
    assert 'E -->|"ZIP"| G["agent.epi"]' not in readme
    assert "binary envelope with a" in walkthrough
    assert "ZIP container with a defined layout." not in walkthrough
    assert "EPI1 header" in spec


def test_current_flagship_doc_has_no_mojibake():
    text = _read(REPO_ROOT / "docs" / "EPI-DOC-v4.0.1.md")
    mojibake_markers = (
        "\u00e2\u20ac\u0153",
        "\u00e2\u20ac",
        "\u00e2\u20ac\u2122",
        "\ufffd",
    )

    assert not any(marker in text for marker in mojibake_markers)
