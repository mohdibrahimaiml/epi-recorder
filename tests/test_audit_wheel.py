from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path


def _load_audit_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "audit_wheel.py"
    spec = importlib.util.spec_from_file_location("audit_wheel_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_wheel(path: Path, members: list[str]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for member in members:
            zf.writestr(member, b"placeholder")


def test_audit_wheel_accepts_expected_runtime_entries(tmp_path):
    module = _load_audit_module()
    wheel_path = tmp_path / "epi_recorder-2.8.6-py3-none-any.whl"
    _make_wheel(
        wheel_path,
        [
            "epi_recorder/__init__.py",
            "epi_recorder/api.py",
            "epi_core/__init__.py",
            "epi_cli/main.py",
            "epi_viewer_static/index.html",
            "pytest_epi/plugin.py",
            "epi_postinstall.py",
            "epi_recorder-2.8.6.dist-info/METADATA",
        ],
    )

    assert module.audit_wheel(wheel_path) == []


def test_audit_wheel_rejects_unexpected_top_level_entries(tmp_path):
    module = _load_audit_module()
    wheel_path = tmp_path / "epi_recorder-2.8.6-py3-none-any.whl"
    _make_wheel(
        wheel_path,
        [
            "epi_recorder/__init__.py",
            "junk.txt",
            "epi_recorder-2.8.6.dist-info/METADATA",
        ],
    )

    issues = module.audit_wheel(wheel_path)
    assert "unexpected top-level entry: junk.txt" in issues


def test_audit_wheel_rejects_suspicious_runtime_files(tmp_path):
    module = _load_audit_module()
    wheel_path = tmp_path / "epi_recorder-2.8.6-py3-none-any.whl"
    _make_wheel(
        wheel_path,
        [
            "epi_recorder/__init__.py",
            "epi_recorder/test_import.py",
            "epi_cli/stdout.log",
            "epi_recorder-2.8.6.dist-info/METADATA",
        ],
    )

    issues = module.audit_wheel(wheel_path)
    assert "suspicious runtime file: epi_recorder/test_import.py" in issues
    assert "suspicious runtime file: epi_cli/stdout.log" in issues
