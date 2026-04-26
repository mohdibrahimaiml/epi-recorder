import shutil
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app
from epi_core.container import (
    EPI_CONTAINER_FORMAT_ENVELOPE,
    EPI_CONTAINER_FORMAT_LEGACY,
    EPI_ENVELOPE_HEADER_SIZE,
    EPI_MIMETYPE,
    EPIContainer,
)
from epi_core.schemas import ManifestModel
from epi_core.workspace import create_recording_workspace


@pytest.fixture
def sample_workspace():
    workspace = create_recording_workspace("epi_envelope_test_")
    source = workspace / "source"
    source.mkdir()
    (source / "steps.jsonl").write_text(
        '{"index": 0, "kind": "session.start", "content": {}}\n',
        encoding="utf-8",
    )
    (source / "environment.json").write_text('{"runtime":"python"}', encoding="utf-8")
    try:
        yield workspace, source
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_pack_defaults_to_envelope(sample_workspace):
    workspace, source = sample_workspace
    output = workspace / "case.epi"
    EPIContainer.pack(source, ManifestModel(cli_command="test"), output)

    assert EPIContainer.detect_container_format(output) == EPI_CONTAINER_FORMAT_ENVELOPE
    assert output.read_bytes()[:4] == b"EPI1"
    assert EPIContainer.container_mimetype(output) == EPI_MIMETYPE


def test_unpack_and_manifest_work_for_envelope(sample_workspace):
    workspace, source = sample_workspace
    output = workspace / "case.epi"
    EPIContainer.pack(source, ManifestModel(cli_command="test"), output)

    manifest = EPIContainer.read_manifest(output)
    unpacked = EPIContainer.unpack(output)

    assert manifest.container_format == EPI_CONTAINER_FORMAT_ENVELOPE
    assert (unpacked / "steps.jsonl").exists()
    assert (unpacked / "manifest.json").exists()


def test_migrate_to_legacy_keeps_artifact_readable(sample_workspace):
    workspace, source = sample_workspace
    output = workspace / "case.epi"
    legacy = workspace / "case-legacy.epi"
    EPIContainer.pack(source, ManifestModel(cli_command="test"), output)

    EPIContainer.migrate(output, legacy, container_format=EPI_CONTAINER_FORMAT_LEGACY)

    assert EPIContainer.detect_container_format(legacy) == EPI_CONTAINER_FORMAT_LEGACY
    assert zipfile.is_zipfile(legacy) is True
    assert EPIContainer.count_steps(legacy) == 1


def test_rejects_unknown_envelope_version(sample_workspace):
    workspace, source = sample_workspace
    output = workspace / "case.epi"
    bad = workspace / "bad-version.epi"
    EPIContainer.pack(source, ManifestModel(cli_command="test"), output)

    data = bytearray(output.read_bytes())
    data[4] = 99
    bad.write_bytes(bytes(data))

    with pytest.raises(ValueError, match="Unsupported EPI envelope version"):
        EPIContainer.read_manifest(bad)


def test_rejects_payload_hash_mismatch_before_zip_open(sample_workspace):
    workspace, source = sample_workspace
    output = workspace / "case.epi"
    bad = workspace / "bad-hash.epi"
    EPIContainer.pack(source, ManifestModel(cli_command="test"), output)

    data = bytearray(output.read_bytes())
    data[EPI_ENVELOPE_HEADER_SIZE + 5] ^= 0x01
    bad.write_bytes(bytes(data))

    with pytest.raises(ValueError, match="payload hash mismatch"):
        EPIContainer.unpack(bad)


def test_migrate_cli_converts_between_envelope_and_legacy(sample_workspace):
    runner = CliRunner()
    workspace, source = sample_workspace
    output = workspace / "case.epi"
    legacy = workspace / "case-legacy.epi"
    roundtrip = workspace / "case-roundtrip.epi"
    EPIContainer.pack(source, ManifestModel(cli_command="test"), output)

    legacy_result = runner.invoke(
        app,
        ["migrate", str(output), "--out", str(legacy), "--legacy-zip"],
    )
    assert legacy_result.exit_code == 0
    assert EPIContainer.detect_container_format(legacy) == EPI_CONTAINER_FORMAT_LEGACY

    envelope_result = runner.invoke(
        app,
        ["migrate", str(legacy), "--out", str(roundtrip)],
    )
    assert envelope_result.exit_code == 0
    assert EPIContainer.detect_container_format(roundtrip) == EPI_CONTAINER_FORMAT_ENVELOPE


def _rewrite_viewer_only(artifact: Path, replacement_html: str, workspace: Path) -> None:
    unpack_dir = workspace / "stale-unpack"
    restaged_payload = workspace / "stale-restaged.zip"

    unpack_dir.mkdir()
    EPIContainer.unpack(artifact, unpack_dir)
    (unpack_dir / "viewer.html").write_text(replacement_html, encoding="utf-8")

    with zipfile.ZipFile(restaged_payload, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip", compress_type=zipfile.ZIP_STORED)
        for file_path in sorted(unpack_dir.rglob("*")):
            if not file_path.is_file():
                continue
            arc_name = str(file_path.relative_to(unpack_dir)).replace("\\", "/")
            if arc_name == "mimetype":
                continue
            zf.write(file_path, arc_name, compress_type=zipfile.ZIP_DEFLATED)

    EPIContainer.write_from_payload(
        restaged_payload,
        artifact,
        container_format=EPIContainer.detect_container_format(artifact),
    )


def test_refresh_viewer_regenerates_embedded_viewer_without_changing_manifest(sample_workspace):
    workspace, source = sample_workspace
    output = workspace / "case.epi"
    EPIContainer.pack(source, ManifestModel(cli_command="test"), output)

    manifest_before = EPIContainer.read_member_text(output, "manifest.json")
    _rewrite_viewer_only(output, "<html><body>stale viewer</body></html>", workspace)
    assert "stale viewer" in EPIContainer.read_member_text(output, "viewer.html")

    EPIContainer.refresh_viewer(output)

    refreshed_viewer = EPIContainer.read_member_text(output, "viewer.html")
    assert "stale viewer" not in refreshed_viewer
    assert "EPI Case Viewer" in refreshed_viewer
    assert EPIContainer.read_member_text(output, "manifest.json") == manifest_before
    assert EPIContainer.detect_container_format(output) == EPI_CONTAINER_FORMAT_ENVELOPE


def test_refresh_viewer_cli_updates_directory_in_place(sample_workspace):
    runner = CliRunner()
    workspace, source = sample_workspace
    output = workspace / "case.epi"
    EPIContainer.pack(source, ManifestModel(cli_command="test"), output)
    _rewrite_viewer_only(output, "<html><body>old viewer</body></html>", workspace)

    result = runner.invoke(app, ["refresh-viewer", str(workspace), "--recursive"])

    assert result.exit_code == 0
    assert "Refreshed embedded viewer" in result.stdout
    assert "old viewer" not in EPIContainer.read_member_text(output, "viewer.html")
