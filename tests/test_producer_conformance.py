"""Conformance gate: every lifecycle producer must own operation identity.

If a module logs an audited lifecycle kind but never mints
``epi-operation/v1`` identity, its steps would be audited by name only — or,
worse, sit uncorrelated inside a governed family. This test fails when a new
producer is added without wiring identity in.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epi_core.operation_identity import LIFECYCLE

RECORDER_ROOT = Path(__file__).resolve().parent.parent / "epi_recorder"

# Attributes used to emit a step. A literal lifecycle kind in the first
# argument is a producer; variable payloads are ignored.
LOGGER_ATTRS = {"log_step", "add_step", "_log", "_alog", "log"}

# Producers that intentionally do not mint identity: they are legacy shims
# whose callers could not correlate two calls even if the shim tried.
EXEMPT = {
    "wrappers/base.py": "deprecated helper: accepts correlation but cannot mint it",
}


def _emitted_kinds(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    kinds: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        else:
            continue
        if name not in LOGGER_ATTRS:
            continue
        first = node.args[0]
        if (
            isinstance(first, ast.Constant)
            and isinstance(first.value, str)
            and first.value in LIFECYCLE
        ):
            kinds.add(first.value)
    return kinds


def test_every_lifecycle_producer_mints_operation_identity():
    offenders: dict[str, sorted] = {}
    for path in sorted(RECORDER_ROOT.rglob("*.py")):
        rel = path.relative_to(RECORDER_ROOT).as_posix()
        kinds = _emitted_kinds(path)
        if not kinds or rel in EXEMPT:
            continue
        source = path.read_text(encoding="utf-8")
        if "make_correlation" not in source:
            offenders[rel] = sorted(kinds)
    assert not offenders, (
        "these modules emit audited lifecycle steps without epi-operation/v1 "
        f"identity: {offenders}"
    )


def test_exemptions_are_still_deprecated():
    for rel in EXEMPT:
        source = (RECORDER_ROOT / rel).read_text(encoding="utf-8")
        assert "Deprecated" in source or "deprecated" in source, rel
