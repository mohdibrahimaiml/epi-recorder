from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from epi_core import __version__ as core_version
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_recorder import __version__ as recorder_version
from epi_cli import __version__ as cli_version


def test_runtime_versions_are_consistent():
    assert core_version == recorder_version == cli_version
    assert ManifestModel().spec_version == core_version


def test_runtime_code_has_no_hardcoded_current_release_literal():
    repo_root = Path(__file__).resolve().parent.parent
    runtime_dirs = [
        repo_root / "epi_core",
        repo_root / "epi_cli",
        repo_root / "epi_recorder",
    ]
    allowed_files = {
        repo_root / "epi_core" / "_version.py",
    }

    offenders: list[str] = []
    for runtime_dir in runtime_dirs:
        for path in runtime_dir.rglob("*.py"):
            if path in allowed_files:
                continue
            text = path.read_text(encoding="utf-8")
            if core_version in text:
                offenders.append(str(path))

    assert not offenders, f"Hardcoded current release literal found in runtime code: {offenders}"


def test_generated_viewer_and_manifest_match_runtime_version():
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "steps.jsonl").write_text("", encoding="utf-8")

        output_path = tmp_path / "artifact.epi"
        manifest = ManifestModel(cli_command="test command")

        EPIContainer.pack(source_dir, manifest, output_path)

        with zipfile.ZipFile(output_path) as zf:
            manifest_json = zf.read("manifest.json").decode("utf-8")
            viewer_html = zf.read("viewer.html").decode("utf-8")

        assert f'"spec_version":"{core_version}"' in manifest_json.replace(" ", "")
        assert f"EPI Viewer v{core_version}" in viewer_html


def test_version_resolution_is_stable_outside_repo_cwd():
    with TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [sys.executable, "-c", "from epi_core._version import get_version; print(get_version())"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode == 0
    assert result.stdout.strip() == core_version
