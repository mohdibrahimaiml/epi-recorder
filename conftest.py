"""
Pytest session-level safety shims for local Windows development.

On this machine, pytest's built-in temp cleanup can raise PermissionError when
Windows briefly holds a handle on the basetemp directory during session finish.
That cleanup failure obscures real test results. We degrade that one cleanup
step to a warning so the actual pass/fail signal is preserved.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import ctypes
import os
import shutil
import tempfile
import uuid
import warnings

import _pytest.pathlib
import _pytest.tmpdir
import pytest

from epi_core.workspace import create_recording_workspace


_original_cleanup_dead_symlinks = _pytest.pathlib.cleanup_dead_symlinks


def _unavailable_startfile(_path: str) -> None:
    raise OSError("os.startfile is only available on Windows")


def _install_windows_api_test_shims() -> None:
    """Expose Windows-only patch targets when tests simulate Windows on POSIX."""
    if not hasattr(os, "startfile"):
        os.startfile = _unavailable_startfile  # type: ignore[attr-defined]

    if not hasattr(ctypes, "windll"):
        ctypes.windll = SimpleNamespace(  # type: ignore[attr-defined]
            shell32=SimpleNamespace(
                IsUserAnAdmin=lambda: False,
                ShellExecuteW=lambda *args, **kwargs: 0,
                ShellExecuteExW=lambda *args, **kwargs: 0,
                SHChangeNotify=lambda *args, **kwargs: None,
            ),
            kernel32=SimpleNamespace(
                WaitForSingleObject=lambda *args, **kwargs: 0,
                CloseHandle=lambda *args, **kwargs: 0,
                SetConsoleOutputCP=lambda *args, **kwargs: 0,
                SetConsoleCP=lambda *args, **kwargs: 0,
            ),
        )


def _safe_cleanup_dead_symlinks(root):  # type: ignore[no-untyped-def]
    try:
        return _original_cleanup_dead_symlinks(root)
    except PermissionError as exc:
        warnings.warn(
            f"Pytest basetemp cleanup skipped due to Windows permission lock: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )


_original_mkdtemp = tempfile.mkdtemp


def _probe_temp_dir(path: Path) -> bool:
    try:
        probe = path / ".tmp_probe_write"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _manual_mkdtemp(prefix: str, suffix: str, dir_: str | None) -> str:
    if dir_:
        root = Path(dir_)
        root.mkdir(parents=True, exist_ok=True)
        candidate = root / f"{prefix}{uuid.uuid4().hex}{suffix}"
        candidate.mkdir(parents=True, exist_ok=False)
        if _probe_temp_dir(candidate):
            return str(candidate)
        shutil.rmtree(candidate, ignore_errors=True)

    return str(create_recording_workspace(prefix or "tmp_"))


def _safe_mkdtemp(
    suffix: str | None = None,
    prefix: str | None = None,
    dir: str | None = None,
):  # type: ignore[no-untyped-def]
    normalized_suffix = suffix or ""
    normalized_prefix = prefix or "tmp_"
    try:
        created = Path(
            _original_mkdtemp(
                suffix=normalized_suffix,
                prefix=normalized_prefix,
                dir=dir,
            )
        )
        if _probe_temp_dir(created):
            return str(created)
        shutil.rmtree(created, ignore_errors=True)
    except Exception:
        pass

    return _manual_mkdtemp(
        prefix=normalized_prefix,
        suffix=normalized_suffix,
        dir_=dir,
    )


def pytest_configure(config):  # type: ignore[no-untyped-def]
    import sys as _sys

    _install_windows_api_test_shims()

    # Windows-only: mkdtemp can fail due to ACL issues in some environments.
    # On Linux/macOS the standard mkdtemp works fine; only apply the shim on Windows.
    if _sys.platform == "win32":
        tempfile.mkdtemp = _safe_mkdtemp  # type: ignore[assignment]

    # Guard against AttributeError in case the pytest version doesn't expose
    # cleanup_dead_symlinks on _pytest.tmpdir (varies across pytest releases).
    if hasattr(_pytest.pathlib, "cleanup_dead_symlinks"):
        _pytest.pathlib.cleanup_dead_symlinks = _safe_cleanup_dead_symlinks
    if hasattr(_pytest.tmpdir, "cleanup_dead_symlinks"):
        _pytest.tmpdir.cleanup_dead_symlinks = _safe_cleanup_dead_symlinks


@pytest.fixture
def tmp_path():
    path = create_recording_workspace("pytest_tmp_")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
