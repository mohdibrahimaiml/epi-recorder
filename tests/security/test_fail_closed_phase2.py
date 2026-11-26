"""Phase 2 regression guards for verification error handling (risk T3).

1. A source-level guard: inside verify_command, no try block that changes the
   decision status may end in a bare `except Exception: pass`.
2. A corruption fuzz: changed, truncated or padded .epi files never pass the
   integrity check.
"""
from __future__ import annotations

import ast
import random
import zipfile
from pathlib import Path

import pytest

import epi_cli.verify as verify_mod

VERIFY_SRC = Path(verify_mod.__file__).read_text(encoding="utf-8")


def _verify_command() -> ast.FunctionDef:
    tree = ast.parse(VERIFY_SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "verify_command":
            return node
    raise AssertionError("verify_command not found")


def _sets_decision_status(stmts) -> bool:
    for node in ast.walk(ast.Module(body=list(stmts), type_ignores=[])):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                src = ast.unparse(tgt)
                if '["decision"]["status"]' in src or "['decision']['status']" in src:
                    return True
    return False


def _swallows(handler: ast.ExceptHandler) -> bool:
    broad = handler.type is None or (
        isinstance(handler.type, ast.Name) and handler.type.id in {"Exception", "BaseException"}
    )
    return broad and all(isinstance(s, ast.Pass) for s in handler.body)


def test_no_decision_change_is_swallowed():
    offenders = []
    for node in ast.walk(_verify_command()):
        if isinstance(node, ast.Try) and _sets_decision_status(node.body):
            for h in node.handlers:
                if _swallows(h):
                    offenders.append(h.lineno)
    assert not offenders, f"decision change swallowed by except/pass at lines {offenders}"


def test_integrity_failure_writes_are_not_swallowed():
    offenders = []
    for node in ast.walk(_verify_command()):
        if not isinstance(node, ast.Try):
            continue
        body = ast.unparse(ast.Module(body=node.body, type_ignores=[]))
        if "integrity_ok" in body and "= False" in body:
            offenders += [h.lineno for h in node.handlers if _swallows(h)]
    assert not offenders, f"integrity FAIL write swallowed at lines {offenders}"


@pytest.fixture()
def sealed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from epi_recorder import get_current_session, record

    out = tmp_path / "case.epi"
    with record(str(out), goal="fuzz"):
        s = get_current_session()
        s.log("tool.call", tool="lookup", id="A-1")
        s.log("decision", action="approve", reason="within limit")
    if not out.exists():
        found = list(tmp_path.rglob("case.epi"))
        assert found, "record() did not produce case.epi"
        out = found[0]
    return out


def _integrity_ok(path: Path) -> bool:
    from epi_core.container import EPIContainer

    try:
        ok, _ = EPIContainer.verify_integrity(path)
    except Exception:
        return False
    return bool(ok)


def test_sealed_file_passes(sealed):
    assert _integrity_ok(sealed)


def test_truncated_file_never_passes(sealed, tmp_path):
    data = sealed.read_bytes()
    for cut in (1, len(data) // 4, len(data) // 2, len(data) - 1):
        bad = tmp_path / f"trunc_{cut}.epi"
        bad.write_bytes(data[:cut])
        assert not _integrity_ok(bad), f"truncated at {cut} bytes passed"


def test_flipped_bytes_never_pass(sealed, tmp_path):
    data = bytearray(sealed.read_bytes())
    rng = random.Random(1234)
    for n in range(20):
        bad_bytes = bytearray(data)
        i = rng.randrange(len(bad_bytes))
        bad_bytes[i] ^= 0xFF
        bad = tmp_path / f"flip_{n}.epi"
        bad.write_bytes(bytes(bad_bytes))
        # A flip inside unused zip padding can be harmless; any flip that
        # still parses must leave the sealed contents identical.
        if _integrity_ok(bad):
            with zipfile.ZipFile(sealed) as a, zipfile.ZipFile(bad) as b:
                for name in a.namelist():
                    assert a.read(name) == b.read(name), f"flip {i} changed {name} and passed"


def test_edited_member_never_passes(sealed, tmp_path):
    bad = tmp_path / "edited.epi"
    with zipfile.ZipFile(sealed) as src, zipfile.ZipFile(bad, "w") as dst:
        names = src.namelist()
        target = next((n for n in names if n.endswith("steps.jsonl")), None) or next(
            n for n in names if not n.endswith("manifest.json") and not n.endswith("/")
        )
        for name in names:
            body = src.read(name)
            if name == target:
                body = body + b"\n"
            dst.writestr(name, body)
    assert not _integrity_ok(bad)


def test_extra_member_never_passes(sealed, tmp_path):
    bad = tmp_path / "extra.epi"
    with zipfile.ZipFile(sealed) as src, zipfile.ZipFile(bad, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, src.read(name))
        dst.writestr("injected.txt", b"not in the manifest")
    assert not _integrity_ok(bad)
