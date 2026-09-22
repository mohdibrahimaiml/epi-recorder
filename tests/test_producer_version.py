"""Seal-time producer version: viewer must show what sealed the file.

Regression test for the hardcoded viewer header bug: the header showed
"EPI Artifact Viewer v4.4.6" (the verifier's installed version) even when
the artifact was sealed by 4.4.1. The seal-time package version is now
stamped into manifest.producer_version at pack time, and viewer generation
uses the stored value.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import epi_recorder
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.serialize import MANIFEST_OMIT_NONE_FROM_HASH


def _pack_minimal(tmp: Path, manifest: ManifestModel, name: str = "artifact.epi") -> Path:
    source_dir = tmp / f"src_{name.replace('.', '_')}"
    source_dir.mkdir(exist_ok=True)
    (source_dir / "steps.jsonl").write_text("", encoding="utf-8")
    out = tmp / name
    EPIContainer.pack(source_dir, manifest, out)
    return out


def test_sealed_manifest_producer_version_matches_package():
    with TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        out = _pack_minimal(tmp, ManifestModel(cli_command="test seal"))
        raw = json.loads(EPIContainer.read_member_text(out, "manifest.json"))
        assert raw["producer_version"] == epi_recorder.__version__
        assert raw["spec_version"] == epi_recorder.__version__


def test_new_producer_version_defaults_to_none_and_is_omitted_from_hash():
    # Old artifacts load with producer_version=None so their signatures keep
    # verifying; None values must be omitted from the preimage.
    assert ManifestModel.model_fields["producer_version"].default is None
    assert "producer_version" in MANIFEST_OMIT_NONE_FROM_HASH


def test_baked_viewer_header_uses_seal_version_not_verifier_version():
    with TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        out = _pack_minimal(tmp, ManifestModel(cli_command="test seal"))
        viewer_html = EPIContainer.read_member_text(out, "viewer.html")
        assert f"EPI Artifact Viewer v{epi_recorder.__version__}" in viewer_html
        assert "__EPI_VERSION__" not in viewer_html


def test_regenerated_viewer_uses_stored_version_for_old_artifact():
    """Simulate a 4.4.1 artifact opened with a newer verifier installed."""
    with TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        # An artifact sealed by 4.4.1: both fields read 4.4.1. pack() must
        # preserve the explicit seal version, not overwrite it.
        manifest = ManifestModel(cli_command="test old seal")
        manifest.spec_version = "4.4.1"
        manifest.producer_version = "4.4.1"
        out = _pack_minimal(tmp, manifest, name="old.epi")

        stored = EPIContainer.read_manifest(out)
        assert stored.spec_version == "4.4.1"
        assert (stored.producer_version or stored.spec_version) == "4.4.1"

        # A pre-producer_version artifact loads with producer_version=None;
        # the viewer must still fall back to spec_version.
        legacy = ManifestModel.model_validate(
            {k: v for k, v in stored.model_dump(mode="json").items() if k != "producer_version"}
        )
        assert legacy.producer_version is None
        html_legacy = EPIContainer._create_embedded_viewer(tmp, legacy)
        assert "EPI Artifact Viewer v4.4.1" in html_legacy

        # Regenerate the viewer the way `epi view` / `epi export-html` does
        # and confirm the header reports the seal version, not the installed one.
        unpack_dir = tmp / "unpacked"
        unpack_dir.mkdir()
        EPIContainer.unpack(out, unpack_dir)
        from epi_cli.view import _create_decision_ops_viewer

        html = _create_decision_ops_viewer(unpack_dir, out)
        assert "EPI Artifact Viewer v4.4.1" in html
        if epi_recorder.__version__ != "4.4.1":
            assert f"EPI Artifact Viewer v{epi_recorder.__version__}" not in html


def test_viewer_template_labels_spec_and_producer_separately():
    repo_root = Path(__file__).resolve().parent.parent
    template = (repo_root / "web_viewer" / "index.html").read_text(encoding="utf-8")
    assert 'id="meta-spec"' in template
    assert 'id="meta-producer"' in template
    app_js = (repo_root / "web_viewer" / "app.js").read_text(encoding="utf-8")
    assert "m.producer_version" in app_js
