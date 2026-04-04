"""
Tests for epi_cli.install — _has_epi_block, _remove_epi_block,
_get_sitecustomize_path, install_global, uninstall_global, CLI commands.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import click

from epi_cli.install import (
    EPI_BLOCK_START,
    EPI_BLOCK_END,
    EPI_SITECUSTOMIZE_CODE,
    _has_epi_block,
    _remove_epi_block,
    _get_sitecustomize_path,
    _ensure_recordings_dir,
    install_global,
    uninstall_global,
)


# ─────────────────────────────────────────────────────────────
# _has_epi_block
# ─────────────────────────────────────────────────────────────

class TestHasEpiBlock:
    def test_returns_true_when_block_present(self):
        content = f"# some code\n{EPI_BLOCK_START}\ncode\n{EPI_BLOCK_END}\n"
        assert _has_epi_block(content) is True

    def test_returns_false_when_block_absent(self):
        content = "# normal sitecustomize\nimport sys\n"
        assert _has_epi_block(content) is False

    def test_empty_content_returns_false(self):
        assert _has_epi_block("") is False

    def test_partial_match_is_true(self):
        # Only the start marker needs to match
        content = f"{EPI_BLOCK_START}\n# partial"
        assert _has_epi_block(content) is True


# ─────────────────────────────────────────────────────────────
# _remove_epi_block
# ─────────────────────────────────────────────────────────────

class TestRemoveEpiBlock:
    def test_removes_block(self):
        content = f"# before\n{EPI_BLOCK_START}\nblock code\n{EPI_BLOCK_END}\n# after\n"
        result = _remove_epi_block(content)
        assert EPI_BLOCK_START not in result
        assert EPI_BLOCK_END not in result
        assert "# before" in result
        assert "# after" in result

    def test_preserves_content_before_and_after(self):
        original = "line1\nline2\n"
        content = original + EPI_SITECUSTOMIZE_CODE
        result = _remove_epi_block(content)
        assert "line1" in result
        assert "line2" in result

    def test_returns_empty_when_only_block(self):
        result = _remove_epi_block(EPI_SITECUSTOMIZE_CODE)
        assert result.strip() == ""

    def test_no_trailing_blank_lines(self):
        content = f"import os\n{EPI_SITECUSTOMIZE_CODE}"
        result = _remove_epi_block(content)
        assert not result.endswith("\n\n")

    def test_idempotent_on_clean_content(self):
        content = "# no block here\nimport sys\n"
        result = _remove_epi_block(content)
        assert "no block here" in result


# ─────────────────────────────────────────────────────────────
# _get_sitecustomize_path
# ─────────────────────────────────────────────────────────────

class TestGetSitecustomizePath:
    def test_returns_path_object(self):
        path = _get_sitecustomize_path()
        assert isinstance(path, Path)

    def test_path_ends_with_sitecustomize(self):
        path = _get_sitecustomize_path()
        assert path.name == "sitecustomize.py"

    def test_path_is_absolute(self):
        path = _get_sitecustomize_path()
        assert path.is_absolute()


# ─────────────────────────────────────────────────────────────
# _ensure_recordings_dir
# ─────────────────────────────────────────────────────────────

class TestEnsureRecordingsDir:
    def test_creates_directory(self, tmp_path):
        expected = tmp_path / ".epi" / "recordings"
        with patch("epi_cli.install.Path") as mock_path_cls:
            mock_home = MagicMock()
            mock_path_cls.home.return_value = mock_home
            mock_home.__truediv__ = lambda self, other: tmp_path / other
            # Just call the real function with real paths
        # Use actual function
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _ensure_recordings_dir()
        assert result.exists()
        assert result.is_dir()


# ─────────────────────────────────────────────────────────────
# install_global
# ─────────────────────────────────────────────────────────────

class TestInstallGlobal:
    def test_installs_when_not_present(self, tmp_path):
        sc = tmp_path / "sitecustomize.py"
        with patch("epi_cli.install._get_sitecustomize_path", return_value=sc), \
             patch("epi_cli.install._ensure_recordings_dir", return_value=tmp_path):
            success, msg = install_global()
        assert success
        assert sc.exists()
        assert EPI_BLOCK_START in sc.read_text()

    def test_appends_to_existing_file(self, tmp_path):
        sc = tmp_path / "sitecustomize.py"
        sc.write_text("# existing content\nimport sys\n", encoding="utf-8")
        with patch("epi_cli.install._get_sitecustomize_path", return_value=sc), \
             patch("epi_cli.install._ensure_recordings_dir", return_value=tmp_path):
            success, msg = install_global()
        content = sc.read_text()
        assert "existing content" in content
        assert EPI_BLOCK_START in content

    def test_skips_when_already_installed(self, tmp_path):
        sc = tmp_path / "sitecustomize.py"
        sc.write_text(EPI_SITECUSTOMIZE_CODE, encoding="utf-8")
        with patch("epi_cli.install._get_sitecustomize_path", return_value=sc):
            success, msg = install_global()
        assert success
        assert "already installed" in msg

    def test_returns_false_on_runtime_error(self):
        with patch("epi_cli.install._get_sitecustomize_path",
                   side_effect=RuntimeError("no site-packages")):
            success, msg = install_global()
        assert not success
        assert "no site-packages" in msg


# ─────────────────────────────────────────────────────────────
# uninstall_global
# ─────────────────────────────────────────────────────────────

class TestUninstallGlobal:
    def test_removes_block(self, tmp_path):
        sc = tmp_path / "sitecustomize.py"
        sc.write_text("# before\n" + EPI_SITECUSTOMIZE_CODE + "# after\n", encoding="utf-8")
        with patch("epi_cli.install._get_sitecustomize_path", return_value=sc):
            success, msg = uninstall_global()
        assert success
        content = sc.read_text()
        assert EPI_BLOCK_START not in content

    def test_removes_file_when_empty_after_removal(self, tmp_path):
        sc = tmp_path / "sitecustomize.py"
        sc.write_text(EPI_SITECUSTOMIZE_CODE, encoding="utf-8")
        with patch("epi_cli.install._get_sitecustomize_path", return_value=sc):
            success, msg = uninstall_global()
        assert success
        assert not sc.exists()

    def test_skips_when_no_file(self, tmp_path):
        with patch("epi_cli.install._get_sitecustomize_path",
                   return_value=tmp_path / "nonexistent.py"):
            success, msg = uninstall_global()
        assert success
        assert "nothing to remove" in msg

    def test_skips_when_block_not_in_file(self, tmp_path):
        sc = tmp_path / "sitecustomize.py"
        sc.write_text("# clean file\n", encoding="utf-8")
        with patch("epi_cli.install._get_sitecustomize_path", return_value=sc):
            success, msg = uninstall_global()
        assert success
        assert "not installed" in msg

    def test_returns_false_on_runtime_error(self):
        with patch("epi_cli.install._get_sitecustomize_path",
                   side_effect=RuntimeError("no site-packages")):
            success, msg = uninstall_global()
        assert not success


# ─────────────────────────────────────────────────────────────
# CLI commands (cli_install, cli_uninstall)
# ─────────────────────────────────────────────────────────────

def _mock_console():
    return MagicMock()


class TestCliInstall:
    def _call_install(self, **kwargs):
        import typer
        from epi_cli.install import cli_install
        ctx = MagicMock()
        try:
            with patch("epi_cli.install.console", _mock_console()):
                cli_install(**kwargs)
            return 0
        except (SystemExit, click.exceptions.Exit) as e:
            return getattr(e, 'code', getattr(e, 'exit_code', 1))

    def test_show_path_exits_0(self, tmp_path):
        sc = tmp_path / "sitecustomize.py"
        with patch("epi_cli.install._get_sitecustomize_path", return_value=sc):
            code = self._call_install(show_path=True)
        assert code == 0

    def test_show_path_runtime_error_exits_1(self):
        with patch("epi_cli.install._get_sitecustomize_path",
                   side_effect=RuntimeError("no path")):
            code = self._call_install(show_path=True)
        assert code == 1

    def test_successful_install_exits_0(self, tmp_path):
        with patch("epi_cli.install.install_global", return_value=(True, "Installed")):
            code = self._call_install(show_path=False)
        assert code == 0

    def test_failed_install_exits_1(self, tmp_path):
        with patch("epi_cli.install.install_global", return_value=(False, "Failed")):
            code = self._call_install(show_path=False)
        assert code == 1


class TestCliUninstall:
    def _call_uninstall(self):
        import typer
        from epi_cli.install import cli_uninstall
        try:
            with patch("epi_cli.install.console", _mock_console()):
                cli_uninstall()
            return 0
        except (SystemExit, click.exceptions.Exit) as e:
            return getattr(e, 'code', getattr(e, 'exit_code', 1))

    def test_successful_uninstall_exits_0(self):
        with patch("epi_cli.install.uninstall_global", return_value=(True, "Removed")):
            code = self._call_uninstall()
        assert code == 0

    def test_failed_uninstall_exits_1(self):
        with patch("epi_cli.install.uninstall_global", return_value=(False, "Error")):
            code = self._call_uninstall()
        assert code == 1
