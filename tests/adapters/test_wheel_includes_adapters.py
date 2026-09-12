"""Packaging: adapters must ship in the built wheel (not only editable installs)."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


from epi_core import __version__ as core_version

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.slow
def test_built_wheel_contains_adapters_package(tmp_path: Path):
    """`python -m build` wheel must include epi_recorder/adapters/*.py."""
    dist = ROOT / "dist"
    # Prefer an already-built wheel from this tree if present
    wheels = sorted(dist.glob(f"epi_recorder-{core_version}*.whl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not wheels:
        pytest.skip("No wheel in dist/; run `python -m build` first or full packaging CI")

    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    assert any(n.endswith("epi_recorder/adapters/__init__.py") for n in names), names[:20]
    assert any(n.endswith("epi_recorder/adapters/langchain.py") for n in names)


def test_adapters_importable_from_installed_package():
    """Sanity: current environment can import the canonical handler."""
    from epi_recorder.adapters.langchain import EpiCallbackHandler

    assert EpiCallbackHandler is not None
