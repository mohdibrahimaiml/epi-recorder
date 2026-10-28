"""The conftest tracked-file guard must name the file it complains about.

A bare "the tree changed" tells nobody what to look at, which is how a real
failure gets dismissed as a flaky guard.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import conftest  # noqa: E402


def test_changed_paths_names_a_newly_dirty_file():
    changed = conftest._changed_paths({}, {"website/assets/demo/x.html": "b"})
    assert changed == [("website/assets/demo/x.html", "newly modified")]


def test_changed_paths_names_a_file_whose_contents_changed():
    before = {"examples/demo-banking-aml.html": "a"}
    after = {"examples/demo-banking-aml.html": "b"}
    assert conftest._changed_paths(before, after) == [
        ("examples/demo-banking-aml.html", "modified")
    ]


def test_changed_paths_ignores_a_file_dirty_the_same_way_throughout():
    """A dirty working tree is not itself a failure — that was the false alarm."""
    snapshot = {"epi_core/keys.py": "a"}
    assert conftest._changed_paths(snapshot, dict(snapshot)) == []


def test_changed_paths_reports_a_file_the_run_reverted():
    assert conftest._changed_paths({"a.py": "a"}, {}) == [("a.py", "no longer modified")]


def test_snapshot_includes_an_already_dirty_file(tmp_path, monkeypatch):
    """The dirty set is sampled, so its contents are compared, not just its size."""
    monkeypatch.setattr(conftest, "_git_nul", lambda *args: ["a.py"])
    monkeypatch.setattr(conftest, "_REPO_ROOT", tmp_path)
    (tmp_path / "a.py").write_text("hello", encoding="utf-8")
    snapshot = conftest._tree_snapshot()
    assert snapshot is not None
    assert snapshot["a.py"] == conftest._file_digest("a.py")


def test_snapshot_is_inert_outside_a_checkout(monkeypatch):
    monkeypatch.setattr(conftest, "_git_nul", lambda *args: None)
    assert conftest._tree_snapshot() is None
