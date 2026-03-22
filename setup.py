"""
Minimal setup.py for backwards compatibility.
All project configuration is in pyproject.toml.

Note: pip install uses pyproject.toml + wheel builds — setup.py install
is not called by modern pip and PostInstallCommand hooks do not run.
File association registration is handled by epi_recorder/__init__.py
(on first import) and epi_cli/main.py (on first CLI use).
"""
from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py


_PACKAGE_BUILD_TARGETS = (
    "epi_core",
    "epi_cli",
    "epi_recorder",
    "epi_analyzer",
    "epi_viewer_static",
    "pytest_epi",
)
_MODULE_BUILD_TARGETS = ("epi_postinstall.py",)


def _clear_stale_build_outputs(build_lib: str) -> None:
    """
    Remove previously-built package trees so incremental setup.py builds
    cannot accidentally package files that no longer exist in source.
    """
    build_root = Path(build_lib)
    if not build_root.exists():
        return

    for package_name in _PACKAGE_BUILD_TARGETS:
        shutil.rmtree(build_root / package_name, ignore_errors=True)

    for module_name in _MODULE_BUILD_TARGETS:
        module_path = build_root / module_name
        if module_path.exists():
            module_path.unlink()


class build_py(_build_py):
    def run(self):
        _clear_stale_build_outputs(self.build_lib)
        super().run()

if __name__ == "__main__":
    setup(cmdclass={"build_py": build_py})
