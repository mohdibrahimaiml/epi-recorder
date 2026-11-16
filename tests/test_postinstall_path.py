"""`epi doctor` PATH repair.

`epi_postinstall.get_scripts_dir()` and `add_to_user_path_windows()` are called
from `epi doctor` on Windows, and did not exist: the call site swallowed the
AttributeError, so the repair silently never ran. These tests pin the behaviour
so it cannot quietly disappear again.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

import epi_postinstall


class _FakeKey:
    pass


def _install_fake_winreg(monkeypatch, initial: str | None):
    """Put a stub `winreg` in sys.modules and record what gets written."""
    store: dict[str, tuple[str, int]] = {}
    if initial is not None:
        store["Path"] = (initial, 2)  # REG_EXPAND_SZ
    writes: list[tuple[str, int, str]] = []

    def _query(_key, name):
        if name not in store:
            raise FileNotFoundError(name)
        return store[name]

    def _set(_key, name, _reserved, value_type, value):
        store[name] = (value, value_type)
        writes.append((name, value_type, value))

    fake = types.SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        KEY_READ=1,
        KEY_WRITE=2,
        REG_SZ=1,
        REG_EXPAND_SZ=2,
        OpenKey=lambda *_a, **_k: _FakeKey(),
        CloseKey=lambda _k: None,
        QueryValueEx=_query,
        SetValueEx=_set,
    )
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setattr(sys, "platform", "win32")
    return writes, store


def test_get_scripts_dir_is_a_real_path():
    scripts = epi_postinstall.get_scripts_dir()
    assert scripts is None or isinstance(scripts, Path)


def test_add_to_user_path_is_a_noop_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert epi_postinstall.add_to_user_path_windows(Path("/usr/local/bin")) is False


def test_missing_path_entry_is_appended(monkeypatch):
    writes, store = _install_fake_winreg(monkeypatch, r"C:\Windows;C:\Tools")
    assert epi_postinstall.add_to_user_path_windows(Path(r"C:\Py\Scripts")) is True
    assert len(writes) == 1
    name, value_type, value = writes[0]
    assert name == "Path"
    assert value.endswith(r";C:\Py\Scripts")
    # The existing entries survive, and the type is preserved.
    assert value.startswith(r"C:\Windows;C:\Tools")
    assert value_type == 2


def test_existing_entry_is_not_duplicated(monkeypatch):
    writes, _ = _install_fake_winreg(monkeypatch, r"C:\Windows;C:\Py\Scripts")
    assert epi_postinstall.add_to_user_path_windows(Path(r"C:\Py\Scripts")) is False
    assert writes == []


def test_comparison_ignores_case_and_trailing_separator(monkeypatch):
    writes, _ = _install_fake_winreg(monkeypatch, "c:\\py\\scripts\\")
    assert epi_postinstall.add_to_user_path_windows(Path(r"C:\Py\Scripts")) is False
    assert writes == []


def test_absent_user_path_is_created(monkeypatch):
    writes, _ = _install_fake_winreg(monkeypatch, None)
    assert epi_postinstall.add_to_user_path_windows(Path(r"C:\Py\Scripts")) is True
    assert writes[0][2] == r"C:\Py\Scripts"
    assert not writes[0][2].startswith(";")
