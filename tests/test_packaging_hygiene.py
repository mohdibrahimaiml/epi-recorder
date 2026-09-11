
from pathlib import Path

from setup import _clear_stale_build_outputs


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_clear_stale_build_outputs_removes_stale_package_files(tmp_path):
    build_lib = tmp_path / "build" / "lib"
    package_dir = build_lib / "epi_recorder"
    package_dir.mkdir(parents=True)
    stale_file = package_dir / "test_script.py"
    stale_file.write_text("print('stale')\n", encoding="utf-8")

    viewer_dir = build_lib / "epi_viewer_static"
    viewer_dir.mkdir(parents=True)
    stale_viewer = viewer_dir / "stale.js"
    stale_viewer.write_text("console.log('stale');\n", encoding="utf-8")

    stale_module = build_lib / "epi_postinstall.py"
    stale_module.write_text("print('stale module')\n", encoding="utf-8")

    _clear_stale_build_outputs(str(build_lib))

    assert not stale_file.exists()
    assert not stale_viewer.exists()
    assert not stale_module.exists()
    assert not package_dir.exists()
    assert not viewer_dir.exists()


def test_clear_stale_build_outputs_is_safe_for_missing_build_dir(tmp_path):
    missing = tmp_path / "missing-build-lib"
    _clear_stale_build_outputs(str(missing))
    assert not missing.exists()


def test_release_gate_deps_come_from_pyproject_not_hardcoded_pins():
    """release-gate.yml must not hardcode dependency pins.

    A stale inline copy (cryptography<44, typer<0.26, rich<14) once made CI
    test older libraries than the code targets. Pins live in pyproject.toml;
    CI installs them via scripts/ci-install-deps.py.
    """
    import re

    workflow = (REPO_ROOT / ".github" / "workflows" / "release-gate.yml").read_text(
        encoding="utf-8"
    )
    assert "scripts/ci-install-deps.py" in workflow
    # No versioned package spec may appear inline (tool upgrades excepted).
    # Tokens must start with a letter so versions like "3.11" don't match.
    for token in re.findall(r'"[a-zA-Z][a-zA-Z0-9_.-]*(?:[<>=!]=?[^"\s]*)?"', workflow):
        name = re.split(r"[<>=!]", token.strip('"'))[0].lower()
        assert name in {"pip", "setuptools", "wheel", "build", "twine"}, (
            f"Hardcoded dependency pin in release-gate.yml: {token} — "
            "declare it in pyproject.toml instead"
        )


def test_ci_install_deps_resolves_repo_ceilings():
    """scripts/ci-install-deps.py must emit pyproject's current ceilings."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/ci-install-deps.py", "--print-only"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    resolved = proc.stdout
    assert "cryptography>=41.0.0,<51" in resolved
    assert "typer>=0.16.0,<0.28.0" in resolved
    assert "rich>=13.0.0,<16" in resolved
    assert "playwright" not in resolved  # gate deselects browser tests
