"""Optional plugin seam for extensions that are not in this repository.

Why this module exists
----------------------
The open-core split keeps the trust layer (format, verifier, recorder, gateway,
witness receiver) MIT, and keeps commercial additions out of the published
wheel. Those additions still need somewhere to attach. This is that seam, and
nothing more:

* A plugin is discovered through the ``epi.plugins`` entry-point group.
* A plugin can either **add a Typer command group** or provide a
  ``register(app)`` hook that adds top-level commands. It can only **add**;
  it cannot replace, gate or alter an existing command.
* There is no licence check anywhere in this module or in ``epi verify``. With
  zero plugins installed the CLI is complete; plugins are additive.
* A broken or missing plugin is skipped silently (with ``EPI_PLUGIN_DEBUG=1``
  it prints a warning to stderr instead). A third-party package can never stop
  the CLI from starting.

The private ``epi-enterprise`` package declares::

    [project.entry-points."epi.plugins"]
    enterprise = "epi_enterprise.cli:app"

It depends on the public package and imports its API; it does not copy public
code, and it is never published to PyPI.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from importlib import metadata
from typing import Any

ENTRY_GROUP = "epi.plugins"
DISABLE_ENV = "EPI_DISABLE_PLUGINS"
DEBUG_ENV = "EPI_PLUGIN_DEBUG"

_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Plugin:
    """A loaded extension: a name and the Typer app it registered."""

    name: str
    module: str
    app: Any


def plugins_disabled() -> bool:
    return str(os.getenv(DISABLE_ENV, "")).strip().lower() in _TRUTHY


def _debug(message: str) -> None:
    if str(os.getenv(DEBUG_ENV, "")).strip().lower() in _TRUTHY:
        print(f"[epi.plugins] {message}", file=sys.stderr)


def _entry_points(group: str = ENTRY_GROUP) -> list[metadata.EntryPoint]:
    try:
        return list(metadata.entry_points(group=group))
    except Exception as exc:  # pragma: no cover - defensive: broken metadata
        _debug(f"could not read entry points: {exc}")
        return []


def _as_app(obj: Any) -> Any:
    """Accept a register hook, a Typer instance, or a zero-arg callable returning one."""
    if hasattr(obj, "register") and callable(getattr(obj, "register")):
        return obj
    if hasattr(obj, "add_typer") and hasattr(obj, "registered_commands"):
        return obj
    if callable(obj) and not isinstance(obj, type):
        candidate = obj()
        if hasattr(candidate, "add_typer"):
            return candidate
    raise TypeError("plugin did not provide a Typer app or a register(app) hook")


def load(group: str = ENTRY_GROUP) -> list[Plugin]:
    """Return every loadable plugin. Never raises because of a bad plugin."""
    if plugins_disabled():
        return []

    loaded: list[Plugin] = []
    seen: set[str] = set()

    for entry in _entry_points(group):
        name = str(getattr(entry, "name", "") or "").strip()
        if not name or name in seen:
            _debug(f"skipping unnamed or duplicate plugin: {name!r}")
            continue
        try:
            app = _as_app(entry.load())
        except Exception as exc:
            _debug(f"skipping plugin {name!r}: {exc}")
            continue
        seen.add(name)
        loaded.append(Plugin(name=name, module=str(getattr(entry, "value", "")), app=app))

    return loaded


def register_typer(app: Any, group: str = ENTRY_GROUP) -> list[Plugin]:
    """Attach plugins to ``app`` and return what was attached.

    A plugin either exposes a Typer app (mounted as a group under its entry-point
    name) or a ``register(app)`` hook (adds its own top-level commands).
    """
    attached: list[Plugin] = []
    for plugin in load(group):
        try:
            hook = getattr(plugin.app, "register", None)
            if callable(hook):
                hook(app)
            else:
                app.add_typer(plugin.app, name=plugin.name)
        except Exception as exc:
            _debug(f"could not register plugin {plugin.name!r}: {exc}")
            continue
        attached.append(plugin)
    return attached
