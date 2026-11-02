"""The plugin seam is additive and cannot break the CLI.

A third-party package (including the private enterprise one) must never be able
to stop `epi` from starting, and must never be required.
"""

from __future__ import annotations

import pytest
import typer

from epi_core import plugins as plugin_mod


class _FakeEntryPoint:
    def __init__(self, name: str, obj=None, error: Exception | None = None, value: str = ""):
        self.name = name
        self._obj = obj
        self._error = error
        self.value = value

    def load(self):
        if self._error is not None:
            raise self._error
        return self._obj


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(plugin_mod.DISABLE_ENV, raising=False)
    monkeypatch.delenv(plugin_mod.DEBUG_ENV, raising=False)


def test_no_plugins_is_not_an_error(monkeypatch):
    monkeypatch.setattr(plugin_mod.metadata, "entry_points", lambda group=None: [])
    assert plugin_mod.load() == []
    app = typer.Typer()
    assert plugin_mod.register_typer(app) == []


def test_broken_plugin_is_skipped_not_raised(monkeypatch):
    monkeypatch.setattr(
        plugin_mod.metadata,
        "entry_points",
        lambda group=None: [
            _FakeEntryPoint("broken", error=RuntimeError("import exploded")),
            _FakeEntryPoint("not-an-app", obj=object()),
        ],
    )
    assert plugin_mod.load() == []


def test_callable_returning_an_app_is_accepted(monkeypatch):
    monkeypatch.setattr(
        plugin_mod.metadata,
        "entry_points",
        lambda group=None: [_FakeEntryPoint("factory", obj=lambda: typer.Typer())],
    )
    loaded = plugin_mod.load()
    assert [p.name for p in loaded] == ["factory"]


def test_plugin_adds_a_command_group(monkeypatch):
    plugin_app = typer.Typer()

    @plugin_app.command("report")
    def _report():  # pragma: no cover - registered, not invoked
        pass

    monkeypatch.setattr(
        plugin_mod.metadata,
        "entry_points",
        lambda group=None: [
            _FakeEntryPoint("enterprise", obj=plugin_app, value="epi_enterprise.cli:app")
        ],
    )

    root = typer.Typer()
    attached = plugin_mod.register_typer(root)
    assert [p.name for p in attached] == ["enterprise"]


def test_disable_env_skips_everything(monkeypatch):
    monkeypatch.setenv(plugin_mod.DISABLE_ENV, "1")
    monkeypatch.setattr(
        plugin_mod.metadata,
        "entry_points",
        lambda group=None: [_FakeEntryPoint("enterprise", obj=typer.Typer())],
    )
    assert plugin_mod.load() == []


def test_duplicate_names_load_once(monkeypatch):
    monkeypatch.setattr(
        plugin_mod.metadata,
        "entry_points",
        lambda group=None: [
            _FakeEntryPoint("dup", obj=typer.Typer()),
            _FakeEntryPoint("dup", obj=typer.Typer()),
        ],
    )
    assert len(plugin_mod.load()) == 1

class _RegisterHook:
    """A plugin that adds top-level commands itself, like epi-enterprise."""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[object] = []

    def register(self, app):
        if self.error is not None:
            raise self.error
        self.calls.append(app)

        @app.command("premium")
        def _premium():  # pragma: no cover - registered, not invoked
            pass


def test_register_hook_adds_top_level_commands(monkeypatch):
    hook = _RegisterHook()
    monkeypatch.setattr(
        plugin_mod.metadata,
        "entry_points",
        lambda group=None: [_FakeEntryPoint("enterprise", obj=hook)],
    )
    root = typer.Typer()
    attached = plugin_mod.register_typer(root)
    assert [p.name for p in attached] == ["enterprise"]
    assert hook.calls == [root]
    assert "premium" in {c.name for c in root.registered_commands}


def test_broken_register_hook_is_skipped(monkeypatch):
    hook = _RegisterHook(error=RuntimeError("boom"))
    monkeypatch.setattr(
        plugin_mod.metadata,
        "entry_points",
        lambda group=None: [_FakeEntryPoint("enterprise", obj=hook)],
    )
    app = typer.Typer()
    assert plugin_mod.register_typer(app) == []
    assert app.registered_commands == []
