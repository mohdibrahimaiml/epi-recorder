from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import re

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

        manifest_json = EPIContainer.read_member_text(output_path, "manifest.json")
        viewer_html = EPIContainer.read_member_text(output_path, "viewer.html")

        assert f'"spec_version":"{core_version}"' in manifest_json.replace(" ", "")
        assert f"EPI Case Viewer v{core_version}" in viewer_html


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


def test_windows_installer_version_matches_runtime_version():
    repo_root = Path(__file__).resolve().parent.parent
    setup_iss = repo_root / "installer" / "windows" / "setup.iss"
    text = setup_iss.read_text(encoding="utf-8")

    expected_line = f'#define MyAppVersion "{core_version}"'
    assert expected_line in text


def test_windows_installer_task_flags_use_supported_values():
    repo_root = Path(__file__).resolve().parent.parent
    setup_iss = repo_root / "installer" / "windows" / "setup.iss"
    text = setup_iss.read_text(encoding="utf-8")

    in_tasks = False
    invalid_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("["):
            in_tasks = line.lower() == "[tasks]"
            continue
        if not in_tasks or "Flags:" not in line:
            continue

        match = re.search(r"Flags:\s*(.+)$", line, re.IGNORECASE)
        if not match:
            continue

        flags = {token.strip().lower() for token in match.group(1).split()}
        if "checked" in flags:
            invalid_lines.append(raw_line)

    assert not invalid_lines, f"Unsupported Inno task flags found: {invalid_lines}"
