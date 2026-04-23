from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers.artifacts import make_decision_epi


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(args: list[str], *, cwd: Path, epi_home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["EPI_HOME"] = str(epi_home)
    env["HOME"] = str(epi_home)
    env["USERPROFILE"] = str(epi_home)
    # Ensure isolation from host environment
    env.pop("EPI_KEYS_DIR", None)
    env.pop("EPI_TRUSTED_KEYS_DIR", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "epi_cli.main", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--help"], "Usage"),
        (["help"], "Portable repro artifacts"),
        (["version"], "EPI"),
        (["keys", "list"], "EPI"),
        (["ls"], "recordings"),
        (["integrate", "pytest", "--dry-run"], "DRY-RUN"),
        (["telemetry", "status"], "Enabled: no"),
    ],
)
def test_read_only_cli_commands_do_not_mutate_repo(tmp_path: Path, args: list[str], expected: str):
    result = _run_cli(args, cwd=tmp_path, epi_home=tmp_path / "epi-home")

    assert result.returncode == 0, result.stdout + result.stderr
    assert expected.lower() in (result.stdout + result.stderr).lower()
    assert not (REPO_ROOT / "cli_test_minimal.py").exists()
    assert not (REPO_ROOT / "cli_test_record.py").exists()


def test_keys_generate_and_export_are_isolated_to_epi_home(tmp_path: Path):
    epi_home = tmp_path / "epi-home"

    generated = _run_cli(
        ["keys", "generate", "--name", "test-key"],
        cwd=tmp_path,
        epi_home=epi_home,
    )
    exported = _run_cli(
        ["keys", "export", "--name", "test-key"],
        cwd=tmp_path,
        epi_home=epi_home,
    )

    assert generated.returncode == 0, generated.stdout + generated.stderr
    assert exported.returncode == 0, exported.stdout + exported.stderr
    assert (epi_home / ".epi" / "keys" / "test-key.key").exists()
    assert (epi_home / ".epi" / "keys" / "test-key.pub").exists()


def test_verify_view_and_export_summary_use_explicit_artifact(tmp_path: Path):
    artifact, _ = make_decision_epi(tmp_path, signed=True)
    extract_dir = tmp_path / "extracted"
    summary_path = tmp_path / "summary.html"
    epi_home = tmp_path / "epi-home"

    verify = _run_cli(["verify", str(artifact)], cwd=tmp_path, epi_home=epi_home)
    view = _run_cli(
        ["view", str(artifact), "--extract", str(extract_dir)],
        cwd=tmp_path,
        epi_home=epi_home,
    )
    summary = _run_cli(
        ["export-summary", "summary", str(artifact), "--out", str(summary_path)],
        cwd=tmp_path,
        epi_home=epi_home,
    )

    assert verify.returncode == 0, verify.stdout + verify.stderr
    assert view.returncode == 0, view.stdout + view.stderr
    assert summary.returncode == 0, summary.stdout + summary.stderr
    assert (extract_dir / "viewer.html").exists()
    assert "EPI Decision Record" in summary_path.read_text(encoding="utf-8")


def test_run_command_records_script_without_opening_browser(tmp_path: Path):
    script = tmp_path / "run_script.py"
    script.write_text("print('CLI run smoke')\n", encoding="utf-8")

    result = _run_cli(
        ["run", str(script), "--no-verify", "--no-open"],
        cwd=tmp_path,
        epi_home=tmp_path / "epi-home",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert list((tmp_path / "epi-recordings").glob("run_script_*.epi"))


def test_record_command_writes_requested_artifact(tmp_path: Path):
    script = tmp_path / "record_script.py"
    script.write_text("print('CLI record smoke')\n", encoding="utf-8")
    output_path = tmp_path / "record_output.epi"

    result = _run_cli(
        ["record", "--out", str(output_path), "--", str(script)],
        cwd=tmp_path,
        epi_home=tmp_path / "epi-home",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert output_path.exists()
