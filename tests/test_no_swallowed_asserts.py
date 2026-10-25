"""Guard: a test may not hide a real assertion behind ``except: pass``.

The 4.6.x coverage-wave files did exactly that, so the suite reported green
while the code under test raised. Cleanup/optional calls with no assertion in
the try block are allowed; this rule only catches handlers that would discard
an assert.

Scans bare / Exception / BaseException handlers whose body is only ``pass`` or
``...`` and whose try body contains an assert.
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def _handler_names(handler: ast.ExceptHandler) -> list[str]:
    if handler.type is None:
        return ["bare"]
    nodes = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    names: list[str] = []
    for node in nodes:
        try:
            names.append(ast.unparse(node))
        except Exception:
            names.append("<expr>")
    return names


def _is_swallow_body(body: list[ast.stmt]) -> bool:
    if len(body) != 1:
        return False
    node = body[0]
    if isinstance(node, ast.Pass):
        return True
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and node.value.value is Ellipsis
    )


def _contains_assert(body: list[ast.stmt]) -> bool:
    return any(
        isinstance(node, ast.Assert) for stmt in body for node in ast.walk(stmt)
    )


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try) or not _contains_assert(node.body):
            continue
        for handler in node.handlers:
            if not _is_swallow_body(handler.body):
                continue
            names = _handler_names(handler)
            if not any(n in ("Exception", "BaseException", "bare") for n in names):
                continue
            found.append(
                f"{path.relative_to(TESTS.parent)}:{handler.lineno} "
                f"(except {','.join(names)}: pass around an assert)"
            )
    return found


def test_no_test_swallows_an_assertion() -> None:
    violations: list[str] = []
    for path in sorted(TESTS.rglob("*.py")):
        if path.name == Path(__file__).name:
            continue
        violations.extend(_violations(path))
    assert violations == [], (
        "a test body hides an assert behind except: pass — remove the swallow "
        "so the assertion can fail:\n  " + "\n  ".join(violations)
    )
