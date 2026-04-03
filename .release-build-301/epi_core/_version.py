"""
Shared runtime version resolution for EPI packages.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
import tomllib


PACKAGE_NAME = "epi-recorder"


@lru_cache(maxsize=1)
def get_version() -> str:
    """
    Resolve the project version with stable precedence:
    1) Local repo pyproject (when running from a source checkout)
    2) Installed package metadata
    """
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    if pyproject_path.exists():
        with pyproject_path.open("rb") as fh:
            data = tomllib.load(fh)
        return data["project"]["version"]

    try:
        return package_version(PACKAGE_NAME)
    except PackageNotFoundError:
        pass

    raise RuntimeError("Unable to resolve EPI version from package metadata or pyproject.toml")
