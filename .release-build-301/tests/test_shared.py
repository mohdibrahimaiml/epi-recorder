"""
Tests for epi_cli._shared — shared subprocess helpers.

Covers ensure_python_command and build_env_for_child.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

from epi_cli._shared import ensure_python_command, build_env_for_child


class TestEnsurePythonCommand:
    """Tests for ensure_python_command()."""

    def test_empty_list_returns_empty(self):
        assert ensure_python_command([]) == []

    def test_py_file_gets_python_prepended(self):
        result = ensure_python_command(["script.py"])
        assert result[0] == sys.executable
        assert result[1] == "script.py"

    def test_py_file_uppercase_extension(self):
        result = ensure_python_command(["SCRIPT.PY"])
        assert result[0] == sys.executable
        assert result[1] == "SCRIPT.PY"

    def test_py_file_with_args(self):
        result = ensure_python_command(["script.py", "--arg1", "val"])
        assert result == [sys.executable, "script.py", "--arg1", "val"]

    def test_non_py_command_unchanged(self):
        cmd = ["python", "script.py"]
        assert ensure_python_command(cmd) == cmd

    def test_executable_command_unchanged(self):
        cmd = ["node", "app.js"]
        assert ensure_python_command(cmd) == cmd

    def test_full_path_py_file(self):
        result = ensure_python_command(["/home/user/my_script.py", "--flag"])
        assert result[0] == sys.executable
        assert result[1] == "/home/user/my_script.py"

    def test_windows_path_py_file(self):
        result = ensure_python_command(["C:\\Users\\test\\script.py"])
        assert result[0] == sys.executable

    def test_non_py_script_unchanged(self):
        cmd = ["bash", "run.sh"]
        assert ensure_python_command(cmd) == cmd


class TestBuildEnvForChild:
    """Tests for build_env_for_child()."""

    def test_returns_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_env_for_child(Path(tmpdir), enable_redaction=True)
            assert isinstance(env, dict)

    def test_epi_record_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_env_for_child(Path(tmpdir), enable_redaction=True)
            assert env["EPI_RECORD"] == "1"

    def test_epi_steps_dir_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_env_for_child(Path(tmpdir), enable_redaction=False)
            assert env["EPI_STEPS_DIR"] == str(tmpdir)

    def test_redaction_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_env_for_child(Path(tmpdir), enable_redaction=True)
            assert env["EPI_REDACT"] == "1"

    def test_redaction_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_env_for_child(Path(tmpdir), enable_redaction=False)
            assert env["EPI_REDACT"] == "0"

    def test_pythonpath_contains_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_env_for_child(Path(tmpdir), enable_redaction=True)
            assert "PYTHONPATH" in env
            # Bootstrap dir should be first entry
            pythonpath = env["PYTHONPATH"]
            first_entry = pythonpath.split(os.pathsep)[0]
            assert Path(first_entry).exists()

    def test_bootstrap_sitecustomize_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_env_for_child(Path(tmpdir), enable_redaction=True)
            bootstrap_dir = Path(env["PYTHONPATH"].split(os.pathsep)[0])
            sitecustomize = bootstrap_dir / "sitecustomize.py"
            assert sitecustomize.exists()
            content = sitecustomize.read_text()
            assert "initialize_recording" in content

    def test_inherits_parent_env(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_env_for_child(Path(tmpdir), enable_redaction=True)
            # Should contain PATH from parent
            assert "PATH" in env or "Path" in env

    def test_existing_pythonpath_preserved(self):
        original = os.environ.get("PYTHONPATH", "")
        test_path = "/some/existing/path"
        os.environ["PYTHONPATH"] = test_path
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                env = build_env_for_child(Path(tmpdir), enable_redaction=False)
                assert test_path in env["PYTHONPATH"]
        finally:
            if original:
                os.environ["PYTHONPATH"] = original
            else:
                os.environ.pop("PYTHONPATH", None)
