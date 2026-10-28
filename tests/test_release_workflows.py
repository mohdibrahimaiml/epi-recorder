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


def test_dispatch_can_target_an_already_published_tag():
    """A tag cut *before* the workflow was fixed can still get its artifacts.

    `workflow_dispatch` reads the workflow file from the ref you dispatch on, so
    dispatching `main` builds main, and dispatching the tag runs the tag's own
    (by then stale) file. Without an explicit `tag` input there is no way to
    build an already-published tag without re-tagging it — which is exactly how
    v4.7.0 ended up with no installer and no SBOM.
    """
    for path in (INSTALLER, SBOM):
        text = _text(path)
        assert re.search(r"workflow_dispatch:[^\n]*\n\s+inputs:", text), (
            f"{path.name} has no workflow_dispatch inputs, so an already-published "
            "tag cannot be built"
        )
        assert "tag:" in text, f"{path.name} has no `tag` input"
        assert "inputs.tag || github.ref" in text, (
            f"{path.name} does not check out the requested tag"
        )
        assert "inputs.tag != ''" in text, (
            f"{path.name} would skip its release-attach steps when dispatched for a tag"
        )


def test_release_attach_steps_name_the_release():
    """`action-gh-release` will not infer the release from a branch ref.

    It fails with "GitHub Releases requires a tag" — which is what happened on
    the first v4.7.0 backfill: the SBOM was built and uploaded as an artifact,
    then the attach step refused. Every attach step must name the release.
    """
    for path in (INSTALLER, SBOM):
        text = _text(path)
        steps = [s for s in text.split("- name: ") if "softprops/action-gh-release" in s]
        assert steps, f"{path.name} no longer attaches anything to the Release"
        for step in steps:
            assert "tag_name: ${{ inputs.tag || github.ref_name }}" in step, (
                f"{path.name}: a release-attach step has no tag_name, so it fails "
                "with 'GitHub Releases requires a tag' when dispatched for a tag"
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
