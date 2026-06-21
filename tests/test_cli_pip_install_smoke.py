"""
Smoke tests that simulate a clean `pip install epi-recorder` user.

These tests make sure every CLI command at least prints --help and that
commands depending on optional extras or hosted services produce friendly,
actionable error messages instead of raw tracebacks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_EPI = REPO_ROOT / "epi-official" / "assets" / "sample.epi"
UNREACHABLE_URL = "http://127.0.0.1:1"


@pytest.fixture(scope="session")
def fresh_venv() -> tuple[Path, Path]:
    """
    Build a wheel from the current repo, create a fresh venv, install the wheel,
    and return (python_executable, epi_home).
    """
    dist_dir = REPO_ROOT / "dist"
    dist_dir.mkdir(exist_ok=True)
    # Remove stale wheels so we do not pick up an old build.
    for stale in dist_dir.glob("epi_recorder-*.whl"):
        stale.unlink()
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(dist_dir.glob("epi_recorder-*.whl"))
    assert wheels, "No wheel produced"
    wheel = wheels[0]

    tmp = tempfile.TemporaryDirectory()
    venv_dir = Path(tmp.name) / "venv"
    venv.create(venv_dir, with_pip=True)
    bin_dir = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
    python = bin_dir / "python"
    pip = bin_dir / "pip"

    subprocess.run(
        [str(pip), "install", str(wheel)],
        check=True,
        capture_output=True,
        text=True,
    )

    epi_home = Path(tmp.name) / "epi-home"
    epi_home.mkdir(parents=True, exist_ok=True)

    yield python, epi_home

    tmp.cleanup()


def _run_in_fresh_venv(
    fresh_venv: tuple[Path, Path],
    args: list[str],
    env_vars: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run `epi <args>` in the session-scoped fresh venv."""
    python, epi_home = fresh_venv
    env = os.environ.copy()
    env["EPI_HOME"] = str(epi_home)
    env["HOME"] = str(epi_home.parent / "home")
    env["USERPROFILE"] = str(epi_home.parent / "home")
    env.pop("EPI_KEYS_DIR", None)
    env.pop("EPI_TRUSTED_KEYS_DIR", None)
    if env_vars:
        env.update(env_vars)

    return subprocess.run(
        [str(python), "-m", "epi_cli.main", *args],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )


def _collect_command_names() -> list[list[str]]:
    """Return argument lists for every top-level command and group help."""
    from epi_cli.main import app

    cases: list[list[str]] = [["--help"]]
    for cmd in app.registered_commands:
        if cmd.name:
            cases.append([cmd.name, "--help"])
    for group in app.registered_groups:
        if group.name:
            cases.append([group.name, "--help"])
    return cases


@pytest.mark.slow
@pytest.mark.parametrize("args", _collect_command_names(), ids=lambda a: " ".join(a))
def test_fresh_venv_help_for_every_command(fresh_venv: tuple[Path, Path], args: list[str]) -> None:
    """After a plain pip install, `epi <command> --help` works for every command."""
    result = _run_in_fresh_venv(fresh_venv, args)
    assert result.returncode == 0, (
        f"epi {' '.join(args)} failed in fresh venv.\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "Usage:" in (result.stdout + result.stderr)


@pytest.mark.slow
def test_fresh_venv_gateway_serve_shows_missing_extra(fresh_venv: tuple[Path, Path]) -> None:
    """`epi gateway serve` on a base install prints a friendly missing-extra error."""
    result = _run_in_fresh_venv(fresh_venv, ["gateway", "serve"])
    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "gateway" in combined.lower()
    assert "extra" in combined.lower()
    assert "pip install epi-recorder[gateway]" in combined


@pytest.mark.slow
def test_fresh_venv_connect_open_shows_missing_extra(fresh_venv: tuple[Path, Path]) -> None:
    """`epi connect open` on a base install prints a friendly missing-extra error."""
    result = _run_in_fresh_venv(fresh_venv, ["connect", "open", "--no-browser"])
    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "gateway" in combined.lower()
    assert "extra" in combined.lower()
    assert "pip install epi-recorder[gateway]" in combined


@pytest.mark.slow
def test_fresh_venv_demo_shows_missing_extra(fresh_venv: tuple[Path, Path]) -> None:
    """`epi demo` on a base install prints a friendly missing-extra error."""
    result = _run_in_fresh_venv(fresh_venv, ["demo", "--no-browser"])
    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "gateway" in combined.lower()
    assert "extra" in combined.lower()
    assert "pip install epi-recorder[gateway]" in combined


@pytest.mark.slow
def test_fresh_venv_share_offline_fallback_works(fresh_venv: tuple[Path, Path]) -> None:
    """`epi share` saves to a local directory when EPI_SHARE_OFFLINE is set."""
    python, epi_home = fresh_venv
    artifact = epi_home / "share_test.epi"
    share_dir = epi_home / "offline-shares"
    # Create a small signed recording using the fresh venv's own default key.
    record_result = _run_in_fresh_venv(
        fresh_venv,
        ["record", "--out", str(artifact), "--", str(python), "-c", "print('hello')"],
    )
    assert record_result.returncode == 0, (
        "Could not create test artifact.\n"
        f"STDOUT:\n{record_result.stdout}\nSTDERR:\n{record_result.stderr}"
    )

    result = _run_in_fresh_venv(
        fresh_venv,
        ["share", str(artifact), "--no-open"],
        env_vars={
            "EPI_SHARE_API_URL": UNREACHABLE_URL,
            "EPI_SHARE_OFFLINE": str(share_dir),
        },
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"offline share failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "offline share directory" in combined.lower()
    assert any(share_dir.glob("*.epi")), "Expected an .epi file in the offline share directory"
    assert any(share_dir.glob("*.epi.share.json")), "Expected a sidecar JSON file"


@pytest.mark.slow
def test_fresh_venv_auth_login_local_fallback_works(fresh_venv: tuple[Path, Path]) -> None:
    """`epi auth login --local` creates a local dev session without contacting the cloud portal."""
    python, epi_home = fresh_venv
    result = _run_in_fresh_venv(
        fresh_venv,
        ["auth", "login", "--local"],
        env_vars={"EPI_TELEMETRY_URL": f"{UNREACHABLE_URL}/api/telemetry/events"},
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"auth login --local failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "local development session" in combined.lower()
    assert (epi_home / "auth.json").exists()


@pytest.mark.slow
def test_fresh_venv_telemetry_dashboard_shows_service_unavailable(
    fresh_venv: tuple[Path, Path],
) -> None:
    """`epi telemetry dashboard` fails gracefully when the dashboard is unreachable."""
    result = _run_in_fresh_venv(
        fresh_venv,
        ["telemetry", "dashboard"],
        env_vars={"EPI_TELEMETRY_DASHBOARD_URL": UNREACHABLE_URL},
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "cannot reach" in combined.lower()


@pytest.mark.slow
def test_fresh_venv_telemetry_test_warns_when_offline(fresh_venv: tuple[Path, Path]) -> None:
    """`epi telemetry test` warns but does not fail when the telemetry endpoint is unreachable."""
    result = _run_in_fresh_venv(
        fresh_venv,
        ["telemetry", "test"],
        env_vars={"EPI_TELEMETRY_URL": f"{UNREACHABLE_URL}/api/telemetry/events"},
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"telemetry test offline failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "test event was not sent" in combined.lower()


@pytest.mark.slow
def test_fresh_venv_telemetry_enable_offline_works(fresh_venv: tuple[Path, Path]) -> None:
    """`epi telemetry enable` works offline when not joining the pilot."""
    result = _run_in_fresh_venv(
        fresh_venv,
        ["telemetry", "enable", "--no-pilot-prompt"],
        env_vars={"EPI_TELEMETRY_URL": f"{UNREACHABLE_URL}/api/telemetry/events"},
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"telemetry enable offline failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "telemetry enabled" in combined.lower()


@pytest.mark.slow
def test_fresh_venv_telemetry_enable_join_pilot_works_offline(
    fresh_venv: tuple[Path, Path],
) -> None:
    """`epi telemetry enable --join-pilot` saves the signup locally when offline."""
    result = _run_in_fresh_venv(
        fresh_venv,
        [
            "telemetry", "enable", "--join-pilot",
            "--email", "test@example.com",
            "--org", "example",
            "--role", "developer",
            "--use-case", "other",
            "--link-telemetry",
            "--consent-to-contact",
        ],
        env_vars={"EPI_PILOT_SIGNUP_URL": f"{UNREACHABLE_URL}/api/telemetry/pilot-signups"},
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        "telemetry enable --join-pilot offline failed.\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "saved locally" in combined.lower()


@pytest.mark.slow
def test_fresh_venv_join_pilot_works_offline(fresh_venv: tuple[Path, Path]) -> None:
    """`epi join-pilot` saves the signup locally when the service is unreachable."""
    result = _run_in_fresh_venv(
        fresh_venv,
        [
            "join-pilot",
            "--email", "test@example.com",
            "--name", "Test User",
            "--org", "example",
            "--role", "developer",
            "--use-case", "other",
            "--consent-to-contact",
        ],
        env_vars={"EPI_PILOT_SIGNUP_URL": f"{UNREACHABLE_URL}/api/telemetry/pilot-signups"},
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"join-pilot offline failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "saved locally" in combined.lower()


@pytest.mark.slow
def test_fresh_venv_scitt_register_local_works(fresh_venv: tuple[Path, Path]) -> None:
    """`epi scitt register --local` works offline on a signed artifact."""
    python, epi_home = fresh_venv
    artifact = epi_home / "scitt_register.epi"
    record_result = _run_in_fresh_venv(
        fresh_venv,
        ["record", "--out", str(artifact), "--", str(python), "-c", "print('hello')"],
    )
    assert record_result.returncode == 0, (
        "Could not create test artifact.\n"
        f"STDOUT:\n{record_result.stdout}\nSTDERR:\n{record_result.stderr}"
    )

    result = _run_in_fresh_venv(
        fresh_venv,
        ["scitt", "register", "--local", str(artifact)],
        env_vars={"EPI_SCITT_URL": UNREACHABLE_URL},
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"scitt register --local failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "local scitt registration complete" in combined.lower()
    with zipfile.ZipFile(artifact) as zf:
        assert "artifacts/scitt/statement.cbor" in zf.namelist()
        assert "artifacts/scitt/receipt.cbor" in zf.namelist()


@pytest.mark.slow
def test_fresh_venv_scitt_anchor_local_works(fresh_venv: tuple[Path, Path]) -> None:
    """`epi scitt anchor --local` works offline on a signed artifact."""
    python, epi_home = fresh_venv
    artifact = epi_home / "scitt_anchor.epi"
    record_result = _run_in_fresh_venv(
        fresh_venv,
        ["record", "--out", str(artifact), "--", str(python), "-c", "print('hello')"],
    )
    assert record_result.returncode == 0, (
        "Could not create test artifact.\n"
        f"STDOUT:\n{record_result.stdout}\nSTDERR:\n{record_result.stderr}"
    )

    result = _run_in_fresh_venv(
        fresh_venv,
        ["scitt", "anchor", "--local", str(artifact)],
        env_vars={"EPI_SCITT_URL": UNREACHABLE_URL},
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"scitt anchor --local failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "local scitt registration complete" in combined.lower()
    with zipfile.ZipFile(artifact) as zf:
        assert "artifacts/scitt/statement.cbor" in zf.namelist()
        assert "artifacts/scitt/receipt.cbor" in zf.namelist()


@pytest.mark.slow
def test_fresh_venv_scitt_local_verify_reaches_medium_trust(fresh_venv: tuple[Path, Path]) -> None:
    """A local SCITT receipt verifies offline and reaches at least MEDIUM trust."""
    python, epi_home = fresh_venv
    artifact = epi_home / "scitt_local_medium.epi"
    record_result = _run_in_fresh_venv(
        fresh_venv,
        ["record", "--out", str(artifact), "--", str(python), "-c", "print('hello')"],
    )
    assert record_result.returncode == 0, (
        "Could not create test artifact.\n"
        f"STDOUT:\n{record_result.stdout}\nSTDERR:\n{record_result.stderr}"
    )

    register_result = _run_in_fresh_venv(
        fresh_venv,
        ["scitt", "register", "--local", str(artifact)],
        env_vars={"EPI_SCITT_URL": UNREACHABLE_URL},
    )
    assert register_result.returncode == 0, (
        "Could not anchor artifact locally.\n"
        f"STDOUT:\n{register_result.stdout}\nSTDERR:\n{register_result.stderr}"
    )

    verify_result = _run_in_fresh_venv(
        fresh_venv,
        ["verify", "--json", str(artifact)],
        env_vars={"EPI_SCITT_URL": UNREACHABLE_URL},
    )
    assert verify_result.returncode == 0, (
        "Verify failed for local SCITT artifact.\n"
        f"STDOUT:\n{verify_result.stdout}\nSTDERR:\n{verify_result.stderr}"
    )
    report = json.loads(verify_result.stdout.strip())
    assert report["integrity_ok"] is True
    assert report["signature_valid"] is True
    assert report["trust_level"] in ("MEDIUM", "HIGH"), (
        f"Expected MEDIUM or HIGH trust, got {report['trust_level']}"
    )

    facts = report.get("facts") or report
    assert facts.get("transparency_ok") is True, "Local SCITT receipt did not verify transparently"
