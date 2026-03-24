from __future__ import annotations

import importlib.util
import io
import tarfile
from pathlib import Path


def _load_audit_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "audit_sdist.py"
    spec = importlib.util.spec_from_file_location("audit_sdist_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_sdist(path: Path, members: list[str]) -> None:
    with tarfile.open(path, "w:gz") as tf:
        for member in members:
            data = b"placeholder"
            info = tarfile.TarInfo(member)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


def test_audit_sdist_accepts_expected_notebooks(tmp_path):
    module = _load_audit_module()
    sdist_path = tmp_path / "epi_recorder-2.8.10.tar.gz"
    _make_sdist(
        sdist_path,
        [
            "epi_recorder-2.8.10/README.md",
            "epi_recorder-2.8.10/colab_demo.ipynb",
            "epi_recorder-2.8.10/EPI NEXUA VENTURES.ipynb",
        ],
    )

    assert module.audit_sdist(sdist_path) == []


def test_audit_sdist_rejects_missing_required_notebook(tmp_path):
    module = _load_audit_module()
    sdist_path = tmp_path / "epi_recorder-2.8.10.tar.gz"
    _make_sdist(
        sdist_path,
        [
            "epi_recorder-2.8.10/README.md",
            "epi_recorder-2.8.10/colab_demo.ipynb",
        ],
    )

    issues = module.audit_sdist(sdist_path)
    assert "missing packaged notebook: EPI NEXUA VENTURES.ipynb" in issues


def test_audit_sdist_rejects_unexpected_notebooks_and_temp_artifacts(tmp_path):
    module = _load_audit_module()
    sdist_path = tmp_path / "epi_recorder-2.8.10.tar.gz"
    _make_sdist(
        sdist_path,
        [
            "epi_recorder-2.8.10/README.md",
            "epi_recorder-2.8.10/colab_demo.ipynb",
            "epi_recorder-2.8.10/EPI NEXUA VENTURES.ipynb",
            "epi_recorder-2.8.10/EPI_Investor_Demo_Stable_v2_8_5.ipynb",
            "epi_recorder-2.8.10/.tmp_nexua_demo_smoke/log.txt",
        ],
    )

    issues = module.audit_sdist(sdist_path)
    assert "unexpected packaged notebook: EPI_Investor_Demo_Stable_v2_8_5.ipynb" in issues
    assert "unexpected temporary artifact: epi_recorder-2.8.10/.tmp_nexua_demo_smoke/log.txt" in issues
