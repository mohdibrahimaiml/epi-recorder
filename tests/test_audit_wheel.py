from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

from epi_core import __version__ as core_version


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
    wheel_path = tmp_path / f"epi_recorder-{core_version}-py3-none-any.whl"
    _make_wheel(
        wheel_path,
        [
            "epi_recorder/__init__.py",
            "epi_recorder/api.py",
            "epi_core/__init__.py",
            "epi_cli/main.py",
            "epi_gateway/main.py",
            "epi_viewer_static/crypto.js",
            "web_viewer/index.html",
            "web_viewer/jszip.min.js",
            "web_viewer/app.js",
            "web_viewer/styles.css",
            "pytest_epi/plugin.py",
            "epi_postinstall.py",
            f"epi_recorder-{core_version}.dist-info/METADATA",
        ],
    )

    assert module.audit_wheel(wheel_path) == []


def test_audit_wheel_rejects_unexpected_top_level_entries(tmp_path):
    module = _load_audit_module()
    wheel_path = tmp_path / f"epi_recorder-{core_version}-py3-none-any.whl"
    _make_wheel(
        wheel_path,
        [
            "epi_recorder/__init__.py",
            "junk.txt",
            f"epi_recorder-{core_version}.dist-info/METADATA",
        ],
    )

    issues = module.audit_wheel(wheel_path)
    assert "unexpected top-level entry: junk.txt" in issues


def test_audit_wheel_rejects_suspicious_runtime_files(tmp_path):
    module = _load_audit_module()
    wheel_path = tmp_path / f"epi_recorder-{core_version}-py3-none-any.whl"
    _make_wheel(
        wheel_path,
        [
            "epi_recorder/__init__.py",
            "epi_recorder/test_import.py",
            "epi_cli/stdout.log",
            f"epi_recorder-{core_version}.dist-info/METADATA",
        ],
    )

    issues = module.audit_wheel(wheel_path)
    assert "suspicious runtime file: epi_recorder/test_import.py" in issues
    assert "suspicious runtime file: epi_cli/stdout.log" in issues


def test_audit_wheel_rejects_missing_viewer_assets(tmp_path):
    module = _load_audit_module()
    wheel_path = tmp_path / f"epi_recorder-{core_version}-py3-none-any.whl"
    _make_wheel(
        wheel_path,
        [
            "epi_recorder/__init__.py",
            "epi_cli/main.py",
            "epi_viewer_static/crypto.js",
            f"epi_recorder-{core_version}.dist-info/METADATA",
        ],
    )

    issues = module.audit_wheel(wheel_path)
    assert "missing required runtime asset: web_viewer/index.html" in issues
    assert "missing required runtime asset: web_viewer/jszip.min.js" in issues
    assert "missing required runtime asset: web_viewer/app.js" in issues
    assert "missing required runtime asset: web_viewer/styles.css" in issues
