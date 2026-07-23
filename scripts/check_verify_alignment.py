#!/usr/bin/env python3
"""Prove golden .epi verify expectations + tamper fails (Phase 4).

Usage (repo root):
  python scripts/check_verify_alignment.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs" / "assets" / "sample-hello.epi"


def _verify_json(path: Path) -> dict:
    # Prefer in-process CLI for speed/reliability in CI
    from typer.testing import CliRunner

    from epi_cli.main import app

    result = CliRunner().invoke(app, ["verify", str(path), "--json"])
    text = result.output or ""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise SystemExit(f"No JSON in verify output for {path}:\n{text[:800]}")
    return json.loads(text[start : end + 1])


def _facts(report: dict) -> dict:
    return report.get("facts") or report


def main() -> int:
    if not GOLDEN.is_file():
        print(f"FAIL: missing golden {GOLDEN}", file=sys.stderr)
        return 2

    good = _verify_json(GOLDEN)
    gf = _facts(good)
    identity = good.get("identity") or {}
    decision = good.get("decision") or {}

    errors: list[str] = []
    if gf.get("integrity_ok") is not True:
        errors.append(f"golden integrity_ok expected True, got {gf.get('integrity_ok')}")
    if gf.get("signature_valid") is not True:
        errors.append(
            f"golden signature_valid expected True, got {gf.get('signature_valid')}"
        )
    if str(identity.get("status", "")).upper() not in ("UNKNOWN", ""):
        # Pinning on the runner is allowed but then WARN→PASS; still require valid crypto
        pass
    if decision.get("status") == "PASS" and str(identity.get("status", "")).upper() == "UNKNOWN":
        errors.append("decision PASS with UNKNOWN identity is unexpected under standard policy")

    # Tamper: one-byte flip
    raw = bytearray(GOLDEN.read_bytes())
    if not raw:
        errors.append("golden file empty")
    else:
        idx = max(0, len(raw) - 200)
        raw[idx] = raw[idx] ^ 0xFF
        tmp = Path(tempfile.mkdtemp()) / "tampered.epi"
        tmp.write_bytes(bytes(raw))
        bad = _verify_json(tmp)
        bf = _facts(bad)
        bdec = (bad.get("decision") or {}).get("status")
        clean = (
            bf.get("integrity_ok") is True
            and bf.get("signature_valid") is True
            and bdec == "PASS"
        )
        if clean:
            errors.append("tampered file still reported clean PASS — alignment broken")
        if bf.get("integrity_ok") is True and bf.get("signature_valid") is True and bdec == "WARN":
            # Still too clean for a byte flip of the envelope
            errors.append(
                "tampered file still integrity+signature OK (expected structural/crypto failure)"
            )

    print("golden:", GOLDEN.relative_to(ROOT))
    print(
        "  integrity_ok=",
        gf.get("integrity_ok"),
        " signature_valid=",
        gf.get("signature_valid"),
        " identity=",
        identity.get("status"),
        " decision=",
        decision.get("status"),
    )
    if errors:
        print("FAIL:")
        for e in errors:
            print(" -", e)
        return 1
    print("OK: golden crypto OK; tampered copy rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
