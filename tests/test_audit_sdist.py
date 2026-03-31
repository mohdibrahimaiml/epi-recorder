from __future__ import annotations

import importlib.util
import io
import tarfile
from pathlib import Path

from epi_core import __version__ as core_version


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
    prefix = f"epi_recorder-{core_version}"
    sdist_path = tmp_path / f"{prefix}.tar.gz"
    _make_sdist(
        sdist_path,
        [
            f"{prefix}/README.md",
            f"{prefix}/colab_demo.ipynb",
            f"{prefix}/EPI NEXUA VENTURES.ipynb",
        ],
    )

    assert module.audit_sdist(sdist_path) == []


def test_audit_sdist_rejects_missing_required_notebook(tmp_path):
    module = _load_audit_module()
    prefix = f"epi_recorder-{core_version}"
    sdist_path = tmp_path / f"{prefix}.tar.gz"
    _make_sdist(
        sdist_path,
        [
            f"{prefix}/README.md",
            f"{prefix}/colab_demo.ipynb",
        ],
    )

    issues = module.audit_sdist(sdist_path)
    assert "missing packaged notebook: EPI NEXUA VENTURES.ipynb" in issues


def test_audit_sdist_rejects_unexpected_notebooks_and_temp_artifacts(tmp_path):
    module = _load_audit_module()
    prefix = f"epi_recorder-{core_version}"
    sdist_path = tmp_path / f"{prefix}.tar.gz"
    _make_sdist(
        sdist_path,
        [
            f"{prefix}/README.md",
            f"{prefix}/colab_demo.ipynb",
            f"{prefix}/EPI NEXUA VENTURES.ipynb",
            f"{prefix}/EPI_Investor_Demo_Stable_v2_8_5.ipynb",
            f"{prefix}/.tmp_nexua_demo_smoke/log.txt",
        ],
    )

    issues = module.audit_sdist(sdist_path)
    assert "unexpected packaged notebook: EPI_Investor_Demo_Stable_v2_8_5.ipynb" in issues
    assert f"unexpected temporary artifact: {prefix}/.tmp_nexua_demo_smoke/log.txt" in issues
