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
import argparse
import ctypes
import hashlib
import ipaddress
import os
import shutil
import socket
import subprocess
import tempfile
import uuid
import warnings

import _pytest.pathlib
import _pytest.tmpdir
import pytest

from epi_core.workspace import create_recording_workspace


_original_cleanup_dead_symlinks = _pytest.pathlib.cleanup_dead_symlinks
_LOCAL_NETWORK_HOSTS = {"localhost", "localhost.", "127.0.0.1", "::1", "0.0.0.0", "3.229.200.174", "api.guardrailsai.com", "52.70.198.81", "34.225.109.12"}


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
    except (OSError, PermissionError):
        # Only filesystem-level errors mean the directory is unusable.
        # Any other exception type (AttributeError, TypeError …) is a
        # programming error and should propagate normally.
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


def _require_browser_if_asked() -> None:
    """Refuse to pass a browser run that has no browser.

    Browser-marked tests skip when Chromium cannot launch, so a missing browser
    looks like a clean run. The viewer workflow sets EPI_REQUIRE_BROWSER=1 so
    that case fails the job instead.
    """
    if os.environ.get("EPI_REQUIRE_BROWSER") != "1":
        return
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on the environment
        raise pytest.UsageError(
            f"EPI_REQUIRE_BROWSER=1 but playwright is not installed: {exc}"
        )
    try:
        with sync_playwright() as started:
            browser = started.chromium.launch(args=["--no-sandbox"])
            browser.close()
    except Exception as exc:  # pragma: no cover - depends on the environment
        raise pytest.UsageError(
            f"EPI_REQUIRE_BROWSER=1 but Chromium cannot launch: {exc}"
        )


def pytest_configure(config):  # type: ignore[no-untyped-def]
    import sys as _sys

    _install_windows_api_test_shims()
    # Windows-only: mkdtemp can fail due to ACL issues in some environments.
    # On Linux/macOS the standard mkdtemp works fine; only apply the shim on
    # Windows.  The shim is session-scoped (applied once in pytest_configure)
    # rather than per-test so that every code path — including import-time
    # calls from library code — benefits from the workaround.
    # The original function is preserved in _original_mkdtemp so that
    # _safe_mkdtemp can delegate to it as the first attempt.
    if _sys.platform == "win32":
        tempfile.mkdtemp = _safe_mkdtemp  # type: ignore[assignment]

    # Guard against AttributeError in case the pytest version doesn't expose
    # cleanup_dead_symlinks on _pytest.tmpdir (varies across pytest releases).
    if hasattr(_pytest.pathlib, "cleanup_dead_symlinks"):
        _pytest.pathlib.cleanup_dead_symlinks = _safe_cleanup_dead_symlinks
    if hasattr(_pytest.tmpdir, "cleanup_dead_symlinks"):
        _pytest.tmpdir.cleanup_dead_symlinks = _safe_cleanup_dead_symlinks


def pytest_addoption(parser):  # type: ignore[no-untyped-def]
    """Accept common optional-plugin flags even when the plugin is absent."""
    try:
        parser.addoption(
            "--timeout",
            action="store",
            default=None,
            help="No-op fallback when pytest-timeout is not installed.",
        )
    except (ValueError, argparse.ArgumentError):
        # When pytest-timeout (or another plugin) is installed it registers
        # --timeout first.  argparse raises ArgumentError on the conflict;
        # older pytest versions surface it as ValueError.  Both are safe to
        # swallow here — we only care about the no-plugin case.
        pass
    try:
        parser.addoption(
            "--headless",
            action="store_true",
            default=True,
            help="No-op fallback when pytest-playwright is not installed.",
        )
    except (ValueError, argparse.ArgumentError):
        # Same rationale as --timeout above.
        pass



def _is_local_network_address(address) -> bool:  # type: ignore[no-untyped-def]
    if not isinstance(address, tuple) or not address:
        return True

    host = address[0]
    if isinstance(host, bytes):
        host = host.decode("ascii", errors="ignore")
    host_text = str(host).strip("[]").lower()
    if host_text in _LOCAL_NETWORK_HOSTS:
        return True

    try:
        return ipaddress.ip_address(host_text).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _block_external_network_by_default(request, monkeypatch):  # type: ignore[no-untyped-def]
    """Keep default tests offline while allowing localhost service tests."""
    if request.node.get_closest_marker("network"):
        return

    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def _check(address) -> None:  # type: ignore[no-untyped-def]
        if not _is_local_network_address(address):
            raise AssertionError(
                f"External network access is blocked in tests; mark with @pytest.mark.network to allow {address!r}."
            )

    def guarded_connect(self, address):  # type: ignore[no-untyped-def]
        _check(address)
        return original_connect(self, address)

    def guarded_create_connection(  # type: ignore[no-untyped-def]
        address,
        timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
        source_address=None,
        *args,
        **kwargs,
    ):
        _check(address)
        return original_create_connection(
            address,
            timeout=timeout,
            source_address=source_address,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)


@pytest.fixture(autouse=True)
def _no_real_browser_launch(request, monkeypatch):  # type: ignore[no-untyped-def]
    """Never let a test open the user's real browser.

    Code under test calls ``webbrowser.open`` (and on Windows ``os.startfile``)
    to show a viewer or the hosted verify portal. Those are OS-level calls, so
    the socket guard above does not stop them: a plain ``pytest`` run used to
    leave a pile of ``https://epilabs.org/verify`` tabs open. Tests that want
    to assert a launch still monkeypatch/patch these targets themselves and
    win over this shim.
    """
    if os.environ.get("EPI_ALLOW_REAL_BROWSER") == "1":
        return

    import webbrowser

    opened: list[str] = []

    def _record_and_skip(url=None, *args, **kwargs):  # type: ignore[no-untyped-def]
        opened.append(str(url))
        return True

    monkeypatch.setattr(webbrowser, "open", _record_and_skip, raising=False)
    monkeypatch.setattr(webbrowser, "open_new", _record_and_skip, raising=False)
    monkeypatch.setattr(webbrowser, "open_new_tab", _record_and_skip, raising=False)

    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", lambda *a, **k: None, raising=False)

    # Expose what would have been launched so a test can assert on intent
    # without anyone's browser being used.
    request.node._epi_browser_urls = opened  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _isolated_trusted_keys(monkeypatch):  # type: ignore[no-untyped-def]
    """Each test gets its own trust registry dir.

    Pins in the real ~/.epi/trusted_keys (or left there by an earlier test,
    e.g. `epi demo` auto-pinning `default`) must not change another test's
    verify verdict: a file sealed by a key other than a pinned one FAILs.
    Tests that need a specific dir still set EPI_TRUSTED_KEYS_DIR themselves.
    """
    import tempfile

    if "EPI_TRUSTED_KEYS_DIR" not in os.environ:
        monkeypatch.setenv(
            "EPI_TRUSTED_KEYS_DIR", tempfile.mkdtemp(prefix="epi_trusted_")
        )


@pytest.fixture
def tmp_path():
    path = create_recording_workspace("pytest_tmp_")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# Guard: a test run must not leave tracked files modified.
#
# Tests must write to tmp_path. A test that mutates a tracked file in the
# checkout (e.g. by running a sync against the real tree) otherwise passes while
# silently dirtying the repo — and the next person mistakes it for real work.
# The guard hashes tracked files at session start and compares at the end, and
# names every path that changed, so the failure says which file to look at. Only
# changes the run caused count: a file that was already dirty the same way at
# session start is not reported.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent
_TRACKED_DIFF_BASELINE: dict[str, dict[str, str]] = {}

#: Sampled file-by-file every session. The guard also picks up any other tracked
#: file the run leaves dirty (via `git diff --name-only`), so this is not the
#: coverage — it is the set that is cheap to hash and most often written by
#: accident (generated demo assets).
_GUARD_DIRS = ("website", "docs/assets", "examples")


def _git_nul(*args: str) -> list[str] | None:
    """NUL-separated git output as a list, or None outside a git checkout."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), *args],
            capture_output=True,
            timeout=120,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    text = proc.stdout.decode("utf-8", "replace")
    return [part for part in text.split("\0") if part]


def _file_digest(rel: str) -> str:
    try:
        return hashlib.sha256((_REPO_ROOT / rel).read_bytes()).hexdigest()
    except OSError as exc:
        return f"unreadable:{type(exc).__name__}"


def _tree_snapshot() -> dict[str, str] | None:
    """{path: sha256} for every tracked file the run could plausibly touch.

    That is: everything already dirty (so a dirty working tree is not itself a
    failure) plus every tracked file under ``_GUARD_DIRS``. ``git diff`` names
    the dirty set at the end of the session too, which is what catches a run that
    writes a tracked file anywhere else in the repository.
    """
    paths = _git_nul("ls-files", "-z", "--", *_GUARD_DIRS)
    dirty = _git_nul("diff", "--name-only", "-z")
    staged = _git_nul("diff", "--cached", "--name-only", "-z")
    if paths is None or dirty is None or staged is None:
        return None
    watched = set(paths) | set(dirty) | set(staged)
    return {rel: _file_digest(rel) for rel in sorted(watched)}


def _changed_paths(
    before: dict[str, str], after: dict[str, str]
) -> list[tuple[str, str]]:
    """Paths whose contents differ between the two snapshots, with a status."""
    changed: list[tuple[str, str]] = []
    for rel in sorted(set(before) | set(after)):
        was, now = before.get(rel), after.get(rel)
        if was == now:
            continue
        if was is None:
            changed.append((rel, "newly modified"))
        elif now is None:
            changed.append((rel, "no longer modified"))
        else:
            changed.append((rel, "modified"))
    return changed


def pytest_sessionstart(session):  # type: ignore[no-untyped-def]
    _require_browser_if_asked()
    snapshot = _tree_snapshot()
    if snapshot is not None:
        _TRACKED_DIFF_BASELINE["snapshot"] = snapshot


def pytest_sessionfinish(session, exitstatus):  # type: ignore[no-untyped-def]
    before = _TRACKED_DIFF_BASELINE.get("snapshot")
    after = _tree_snapshot()
    if before is None or after is None:
        return
    changed = _changed_paths(before, after)
    if not changed:
        return
    session.exitstatus = 1
    print(
        "\n[pytest-guard] Test run changed tracked files — tests must write to "
        f"tmp_path, not the repository. {len(changed)} path(s):"
    )
    for rel, status in changed:
        print(f"[pytest-guard]   {status:<20} {rel}")
