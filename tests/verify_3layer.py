#!/usr/bin/env python3
"""
Lightweight 3-layer verifier for `.epi` artifacts.

Verifies:
 - Functional: export to AGT JSON and check required keys
 - Determinism: export twice and compare outputs
 - Integrity: verify internal file hashes from manifest
 - Identity: workspace-scoped identity mapping check for producer agent

Usage:
  python tests/verify_3layer.py [--epi path/to.epi] [--identity-dir .epi_test_state]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from epi_recorder.integrations.agt.exporter import export_epi_to_agt
from epi_core.container import EPIContainer
import epi_cli.identity as identity

ALLOWED_EVENT_TYPES = {"llm_call", "decision", "redaction", "event"}


def find_epi(preferred_name: str | None = None) -> Path | None:
    cands = list(Path.cwd().rglob("*.epi"))
    if not cands:
        return None
    if preferred_name:
        for p in cands:
            if "epi-recordings" in str(p).replace("\\", "/") and p.name == preferred_name:
                return p
    # newest fallback
    return sorted(cands, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="3-layer verifier for .epi artifacts")
    parser.add_argument("--epi", "-e", help="Path to .epi to verify", default=None)
    parser.add_argument("--identity-dir", help="Workspace dir for identity map", default=".epi_test_state")
    args = parser.parse_args(argv)

    reports: list[str] = []
    ok = True

    # Resolve .epi
    if args.epi:
        epi_path = Path(args.epi)
        if not epi_path.exists():
            print(f"ERROR: specified .epi not found: {epi_path}")
            return 2
    else:
        epi_path = find_epi(preferred_name="demo_refund.epi")
        if epi_path is None:
            print("ERROR: no .epi artifacts found in workspace")
            return 2

    reports.append(f"Located .epi: {epi_path}")

    # Prepare workspace-scoped identity state dir to avoid touching user home
    state_dir = Path(args.identity_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    identity._state_dir = lambda: state_dir
    reports.append(f"Using identity state dir: {state_dir}")

    # Register a test mapping for the demo agent so we can validate mapping behavior
    identity.register_agent("RefundApprovalAgent", "did:key:demo123", public_key="ed25519:abc", trust_tier="standard")
    reports.append("Registered identity mapping for RefundApprovalAgent")

    # Export twice to check determinism
    out1 = epi_path.with_suffix(".agt.json")
    out2 = epi_path.with_name(epi_path.stem + ".agt.v2.json")
    try:
        export_epi_to_agt(epi_path, out1, include_raw=True)
        # slight pause to avoid any FS timestamp weirdness
        time.sleep(0.05)
        export_epi_to_agt(epi_path, out2, include_raw=True)
        b1 = out1.read_bytes()
        b2 = out2.read_bytes()
        if b1 != b2:
            ok = False
            reports.append("Determinism: exports differ")
        else:
            reports.append("Determinism: exports identical")
    except Exception as e:
        ok = False
        reports.append(f"Export failed: {e}")

    # Integrity
    try:
        integrity_ok, mismatches = EPIContainer.verify_integrity(epi_path)
        if not integrity_ok:
            ok = False
            reports.append(f"Integrity: FAILED - {mismatches}")
        else:
            reports.append("Integrity: OK")
    except Exception as e:
        ok = False
        reports.append(f"Integrity check error: {e}")

    # Read export JSON and perform functional checks
    try:
        payload = json.loads(out1.read_text(encoding="utf-8"))
        for key in ("audit_id", "timestamp", "agent", "execution", "events", "integrity"):
            if key not in payload:
                ok = False
                reports.append(f"Missing key in AGT export: {key}")
    except Exception as e:
        ok = False
        reports.append(f"Reading export JSON failed: {e}")
        payload = {}

    # Event filtering
    try:
        event_types = {e.get("type") for e in payload.get("events", []) if isinstance(e, dict)}
        unexpected = {t for t in event_types if t not in ALLOWED_EVENT_TYPES}
        if unexpected:
            ok = False
            reports.append(f"Unexpected event types: {unexpected}")
        else:
            reports.append(f"Event types OK: {sorted(event_types)}")
    except Exception as e:
        ok = False
        reports.append(f"Event inspection failed: {e}")

    # Identity mapping check: discover agent name in steps and ensure mapping exists
    try:
        steps = EPIContainer.read_steps(epi_path)
        agent_name = None
        for s in steps:
            if s.get("kind") == "agent.run.start" and isinstance(s.get("content"), dict):
                agent_name = s["content"].get("agent_name")
                break
        if not agent_name:
            for s in steps:
                if s.get("kind", "").startswith("agent") and isinstance(s.get("content"), dict):
                    agent_name = s["content"].get("agent_name") or s["content"].get("agent")
                    if agent_name:
                        break
        if not agent_name:
            reports.append("Agent name not found in steps")
        else:
            reports.append(f"Agent name in steps: {agent_name}")
            stored = json.loads((state_dir / "identity_map.json").read_text(encoding="utf-8"))
            if stored.get(agent_name, {}).get("did") == "did:key:demo123":
                reports.append("Identity mapping file contains DID for agent")
            else:
                ok = False
                reports.append("Identity mapping file missing DID for agent")
    except Exception as e:
        ok = False
        reports.append(f"Identity check failed: {e}")

    # Emit final report
    if ok:
        print("3-LAYER VERIFICATION: PASS")
    else:
        print("3-LAYER VERIFICATION: FAIL")
    for r in reports:
        print("-", r)

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
