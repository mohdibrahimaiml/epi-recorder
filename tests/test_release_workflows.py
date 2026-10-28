"""The tag-push release artifacts must not rot between releases.

`.github/workflows/build-windows-installer.yml` and `.github/workflows/sbom.yml`
only run on a `v*.*.*` tag, so a broken step stays invisible until a release is
actually cut. Both were broken at the v4.7.0 tag:

  - the installer job died after 4s, in "Getting action download info", because
    the workflow asked for a floating `sigstore/gh-action-sigstore-python@v3`.
    Sigstore publishes no bare `v3` tag (its releases are v3.5.0, v3.4.0, ...),
    so the ref could not resolve and the .exe and its checksums never reached
    the GitHub Release;
  - the SBOM job died after 27s with `cyclonedx-py: error: unrecognized
    arguments: --format --output`, because cyclonedx-bom renamed those flags
    (`--of` / `-o` in the 4.x+ CLI). Nothing was attached either.

These assertions are static and offline on purpose: they catch exactly this
class of drift (an action ref that cannot resolve, a CLI invocation that no
longer exists) without a network call inside the test suite. Stdlib only, no
pyyaml, so this also runs where the release gate has no third-party deps.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"
INSTALLER = WORKFLOWS / "build-windows-installer.yml"
SBOM = WORKFLOWS / "sbom.yml"


def _text(path: Path) -> str:
    assert path.is_file(), f"{path.name} missing: release artifacts would never be built"
    return path.read_text(encoding="utf-8", errors="ignore")


def test_release_artifact_workflows_still_run_on_tags():
    for path in (INSTALLER, SBOM):
        text = _text(path)
        assert "tags:" in text and "v*.*.*" in text, (
            f"{path.name} no longer runs on a v*.*.* tag, so it could rot unnoticed"
        )


def test_sigstore_action_is_pinned_to_a_real_release():
    text = _text(INSTALLER)
    refs = re.findall(r"uses:\s*sigstore/gh-action-sigstore-python@(\S+)", text)
    assert refs, "the installer no longer Sigstore-signs its artifacts"

    for ref in refs:
        assert re.fullmatch(r"v\d+\.\d+\.\d+", ref), (
            f"sigstore/gh-action-sigstore-python@{ref} is not a release tag; "
            "sigstore publishes no floating major (no bare `v3`), so the ref "
            "cannot resolve and the job dies at action download"
        )


def test_sbom_workflow_uses_the_cyclonedx_py_flags_it_pins():
    text = _text(SBOM)
    invocation = next(
        (
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("cyclonedx-py")
        ),
        None,
    )
    assert invocation, "the SBOM workflow no longer invokes cyclonedx-py"

    assert "--of" in invocation and "-o " in invocation, (
        f"cyclonedx-py invocation looks wrong: {invocation!r}"
    )
    for removed in ("--format", "--output "):
        assert removed not in invocation, (
            f"{removed!r} was removed from the cyclonedx-py CLI; "
            "it fails with 'unrecognized arguments'"
        )

    assert "cyclonedx-bom>=7,<8" in text, (
        "pin the cyclonedx-bom CLI generation the invocation targets, so a "
        "renamed flag cannot break the next release silently"
    )
