"""A command that moved into the paid package must explain itself.

Click's default is `No such command 'gateway'.` plus a usage dump, which reads
like a typo. Someone who used the command yesterday deserves one line telling
them what happened and where the plan is.
"""

from __future__ import annotations

import pytest

from epi_cli.main import PAID_COMMANDS, _paid_command_hint, _registered_names


def test_moved_command_explains_itself(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as stop:
        _paid_command_hint(["enterprise", "status"], known=set())
    assert stop.value.code == 2
    out = capsys.readouterr().out
    assert "enterprise" in out
    assert "https://epilabs.org/plans" in out


def test_installed_plugin_is_never_intercepted():
    # When epi-enterprise is installed the real command is registered, so the
    # hint must do nothing at all.
    _paid_command_hint(["enterprise"], known={"enterprise"})


def test_free_commands_and_flags_pass_through():
    for argv in (["--help"], ["--version"], ["verify", "run.epi"], ["record", "-o", "x.epi"]):
        _paid_command_hint(argv, known=set())


def test_the_real_app_still_has_the_free_surface():
    names = _registered_names()
    for free in ("verify", "record", "view", "witness", "cloud", "review", "approvers", "demo", "dev"):
        assert free in names, f"{free} disappeared from the free CLI"
    # Guard against the list going stale: every entry still names something.
    assert all(name and plan for name, plan in PAID_COMMANDS.items())


def test_gateway_and_connect_moved_to_epi_enterprise(capsys: pytest.CaptureFixture[str]):
    names = _registered_names()
    for moved in ("gateway", "connect"):
        assert moved not in names, f"{moved} is still in the free CLI"
        with pytest.raises(SystemExit) as stop:
            _paid_command_hint([moved, "serve"], known=names)
        assert stop.value.code == 2
        out = capsys.readouterr().out
        assert moved in out
        assert "EPI Enterprise" in out
        assert "https://epilabs.org/plans" in out


def test_the_gateway_package_is_gone_from_the_public_tree():
    import importlib.util

    assert importlib.util.find_spec("epi_gateway") is None, "epi_gateway still importable from the public install"
