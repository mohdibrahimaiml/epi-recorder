"""
Minimal setup.py for backwards compatibility.
All project configuration is in pyproject.toml.

Note: pip install uses pyproject.toml + wheel builds — setup.py install
is not called by modern pip and PostInstallCommand hooks do not run.
Windows file association registration is handled explicitly by
epi_postinstall.py, `epi associate`, and the packaged installer.
"""
from pathlib import Path
import shutil

try:
    from setuptools import setup
    from setuptools.command.build_py import build_py as _build_py
except ModuleNotFoundError:  # pragma: no cover - exercised in packaging hygiene tests
    setup = None
    _build_py = None


_PACKAGE_BUILD_TARGETS = (
    "epi_core",
    "epi_cli",
    "epi_recorder",
    "epi_analyzer",
    "epi_viewer_static",
    "web_viewer",
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


if _build_py is not None:
    class build_py(_build_py):
        def run(self):
            _clear_stale_build_outputs(self.build_lib)
            super().run()
else:
    class build_py:  # pragma: no cover - only used when setuptools is unavailable
        def __init__(self, *args, **kwargs):
            raise ModuleNotFoundError("setuptools is required to run setup.py build commands")

if __name__ == "__main__":
    if setup is None:
        raise ModuleNotFoundError("setuptools is required to execute setup.py")
    setup(cmdclass={"build_py": build_py})
