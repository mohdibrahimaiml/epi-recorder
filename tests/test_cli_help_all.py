"""B4: every command and subcommand must render ``--help``.

The original crash was a Rich markup error in a Typer help string
(``s3://bucket[/prefix]``).  A one-off test for ``cloud storage set`` would
miss the next command with an unescaped ``[``, so this walks the whole Typer
command tree and invokes ``--help`` on every node.
"""

from __future__ import annotations

import click
from typer.main import get_command
from typer.testing import CliRunner

from epi_cli.main import app

runner = CliRunner()


def _walk(group: click.Group, path: tuple[str, ...] = ()):
    for name, command in sorted(group.commands.items()):
        current = (*path, name)
        yield current, command
        if isinstance(command, click.Group):
            yield from _walk(command, current)


def test_every_command_and_subcommand_help_renders() -> None:
    root = get_command(app)
    assert hasattr(root, "commands")

    failures: list[str] = []
    for path, _command in [((), root), *_walk(root)]:
        result = runner.invoke(app, [*path, "--help"])
        if result.exit_code != 0:
            failures.append(f"{' '.join(path) or '<root>'}: exit {result.exit_code}")
        for marker in ("Traceback", "MarkupError", "Error: Invalid value"):
            if marker in result.output:
                failures.append(f"{' '.join(path) or '<root>'}: {marker}")

    assert not failures, "\n".join(failures)
