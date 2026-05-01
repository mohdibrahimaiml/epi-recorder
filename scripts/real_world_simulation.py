#!/usr/bin/env python3
"""
Real-world EPI simulation — proves behavior under actual usage conditions.

Scenarios:
  A) User workflow: create → verify (pass)
  B) Third-party verification: fresh machine, no keys, no cache
  C) Failure cases: payload tamper, signature tamper, key removal, DID break
  D) Time-gap simulation: verify after cache clear / offline mode
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure repo root is on path so tests.helpers is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.trust import verify_embedded_manifest_signature
from epi_recorder.api import EpiRecorderSession
from tests.helpers.artifacts import make_decision_epi, rewrite_legacy_member

EPITAPH = "-" * 60
PASS_MARK = "[PASS]"
FAIL_MARK = "[FAIL]"
WARN_MARK = "[WARN]"


def _run(cmd: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", env=env
    )


def _fresh_env() -> dict[str, str]:
    """Return an environment that simulates a machine with no EPI installation."""
    env = dict(os.environ)
    tmp = tempfile.mkdtemp(prefix="epi_fresh_")
    env["EPI_HOME"] = tmp
    env["EPI_KEYS_DIR"] = str(Path(tmp) / "keys")
    env["EPI_TRUSTED_KEYS_DIR"] = str(Path(tmp) / "trusted_keys")
    return env, tmp


def scenario_a_user_workflow():
    print(f"\n{EPITAPH}")
    print("SCENARIO A — User Workflow")
    print(f"{EPITAPH}\n")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        artifact = tmp / "user_workflow.epi"

        # 1. Create artifact (simulates `epi record`)
        with EpiRecorderSession(
            output_path=artifact,
            workflow_name="real-world-test",
            goal="Prove the system works end to end",
            auto_sign=True,
        ) as epi:
            epi.log_step("shell.command", {"cmd": "echo hello"})
            epi.log_step("llm.request", {"model": "gpt-4", "prompt": "hello"})
            epi.log_step("llm.response", {"output": "world"})

        print(f"Created: {artifact} ({artifact.stat().st_size} bytes)")

        # 2. Verify via CLI
        result = _run(["epi", "verify", "--json", str(artifact)])
        report = json.loads(result.stdout) if result.stdout else {}

        ok = result.returncode == 0 and report.get("facts", {}).get("signature_valid") is True
        mark = PASS_MARK if ok else FAIL_MARK
        print(f"{mark} CLI verify exit={result.returncode}")
        print(f"       integrity_ok={report.get('facts', {}).get('integrity_ok')}")
        print(f"       signature_valid={report.get('facts', {}).get('signature_valid')}")
        print(f"       trust_level={report.get('trust_level')}")
        print(f"       identity={report.get('identity', {}).get('status')}")
        return ok


def scenario_b_third_party_verification():
    print(f"\n{EPITAPH}")
    print("SCENARIO B — Third-Party Verification (Fresh Machine)")
    print(f"{EPITAPH}\n")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        artifact = tmp / "portable.epi"

        # Create on "machine A"
        with EpiRecorderSession(
            output_path=artifact, workflow_name="portable", auto_sign=True
        ) as epi:
            epi.log_step("test.step", {"message": "portable artifact"})

        # Verify on "machine B" — no keys, no cache, no trust registry
        env, fresh_dir = _fresh_env()
        try:
            result = _run(["epi", "verify", "--json", str(artifact)], env=env)
            report = json.loads(result.stdout) if result.stdout else {}

            ok = (
                result.returncode == 0
                and report.get("facts", {}).get("signature_valid") is True
                and report.get("facts", {}).get("integrity_ok") is True
                and report.get("identity", {}).get("status") == "UNKNOWN"
            )
            mark = PASS_MARK if ok else FAIL_MARK
            print(f"{mark} Fresh-machine verify")
            print(f"       exit_code={result.returncode}")
            print(f"       signature_valid={report.get('facts', {}).get('signature_valid')}")
            print(f"       integrity_ok={report.get('facts', {}).get('integrity_ok')}")
            print(f"       identity={report.get('identity', {}).get('status')}")
            print(f"       decision={report.get('decision', {}).get('status')}")
            return ok
        finally:
            shutil.rmtree(fresh_dir, ignore_errors=True)


def scenario_c_failure_cases():
    print(f"\n{EPITAPH}")
    print("SCENARIO C — Failure Cases (Tamper Resistance)")
    print(f"{EPITAPH}\n")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        artifact = tmp / "original.epi"

        with EpiRecorderSession(
            output_path=artifact, workflow_name="tamper-test", auto_sign=True
        ) as epi:
            epi.log_step("test.step", {"message": "original"})

        results = []

        # C1 — Payload tamper
        tampered = tmp / "tampered_payload.epi"
        shutil.copy(artifact, tampered)
        rewrite_legacy_member(tampered, "steps.jsonl", b'{"tampered":true}\n')
        r = _run(["epi", "verify", "--json", str(tampered)])
        report = json.loads(r.stdout) if r.stdout else {}
        ok = r.returncode != 0 and report.get("facts", {}).get("integrity_ok") is False
        print(f"{'[PASS]' if ok else '[FAIL]'} Payload tamper detected (exit={r.returncode}, integrity_ok={report.get('facts', {}).get('integrity_ok')})")
        results.append(ok)

        # C2 — Signature tamper
        tampered_sig = tmp / "tampered_sig.epi"
        shutil.copy(artifact, tampered_sig)
        manifest = json.loads(EPIContainer.read_manifest(tampered_sig).model_dump_json())
        manifest["signature"] = manifest["signature"][:-8] + "deadbeef"
        rewrite_legacy_member(
            tampered_sig, "manifest.json", json.dumps(manifest, indent=2).encode("utf-8")
        )
        r = _run(["epi", "verify", "--json", str(tampered_sig)])
        report = json.loads(r.stdout) if r.stdout else {}
        ok = r.returncode != 0 and report.get("facts", {}).get("signature_valid") is False
        print(f"{'[PASS]' if ok else '[FAIL]'} Signature tamper detected (exit={r.returncode}, signature_valid={report.get('facts', {}).get('signature_valid')})")
        results.append(ok)

        # C3 — Key removal
        tampered_key = tmp / "tampered_key.epi"
        shutil.copy(artifact, tampered_key)
        manifest = json.loads(EPIContainer.read_manifest(tampered_key).model_dump_json())
        manifest["public_key"] = None
        rewrite_legacy_member(
            tampered_key, "manifest.json", json.dumps(manifest, indent=2).encode("utf-8")
        )
        r = _run(["epi", "verify", "--json", str(tampered_key)])
        report = json.loads(r.stdout) if r.stdout else {}
        ok = r.returncode != 0
        print(f"{'[PASS]' if ok else '[FAIL]'} Key removal detected (exit={r.returncode})")
        results.append(ok)

        # C4 — DID break must NOT fail crypto
        did_artifact = tmp / "did_artifact.epi"
        with EpiRecorderSession(
            output_path=did_artifact,
            workflow_name="did-break",
            did_web="did:web:unreachable.example",
            auto_sign=True,
        ) as epi:
            epi.log_step("test.step", {"message": "did"})

        env, fresh_dir = _fresh_env()
        try:
            with patch("epi_core.did_web.requests.get", side_effect=ConnectionError("offline")):
                r = _run(["epi", "verify", "--json", str(did_artifact)], env=env)
            report = json.loads(r.stdout) if r.stdout else {}
            ok = (
                r.returncode == 0
                and report.get("facts", {}).get("signature_valid") is True
                and report.get("identity", {}).get("status") == "UNKNOWN"
            )
            print(f"{'[PASS]' if ok else '[FAIL]'} DID break does not kill crypto (exit={r.returncode}, signature_valid={report.get('facts', {}).get('signature_valid')}, identity={report.get('identity', {}).get('status')})")
            results.append(ok)
        finally:
            shutil.rmtree(fresh_dir, ignore_errors=True)

        return all(results)


def scenario_d_time_gap_simulation():
    print(f"\n{EPITAPH}")
    print("SCENARIO D — Time-Gap Simulation")
    print(f"{EPITAPH}\n")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        artifact = tmp / "timegap.epi"

        # 1. Generate today
        with EpiRecorderSession(
            output_path=artifact, workflow_name="timegap", auto_sign=True
        ) as epi:
            epi.log_step("test.step", {"message": "time gap"})

        # 2. Simulate future: clear cache, fresh env, offline
        env, fresh_dir = _fresh_env()
        # Also nuke any DID cache
        did_cache = Path(fresh_dir) / "cache" / "did_web"
        if did_cache.exists():
            shutil.rmtree(did_cache)
        try:
            result = _run(["epi", "verify", "--json", str(artifact)], env=env)
            report = json.loads(result.stdout) if result.stdout else {}

            ok = (
                result.returncode == 0
                and report.get("facts", {}).get("signature_valid") is True
                and report.get("facts", {}).get("integrity_ok") is True
            )
            mark = PASS_MARK if ok else FAIL_MARK
            print(f"{mark} Verify after cache-clear / offline simulation")
            print(f"       exit_code={result.returncode}")
            print(f"       signature_valid={report.get('facts', {}).get('signature_valid')}")
            print(f"       integrity_ok={report.get('facts', {}).get('integrity_ok')}")
            return ok
        finally:
            shutil.rmtree(fresh_dir, ignore_errors=True)


def main():
    print("=" * 60)
    print("EPI REAL-WORLD SIMULATION")
    print("Version: 4.0.1")
    print("=" * 60)

    results = {
        "A: User workflow": scenario_a_user_workflow(),
        "B: Third-party verify": scenario_b_third_party_verification(),
        "C: Failure cases": scenario_c_failure_cases(),
        "D: Time-gap simulation": scenario_d_time_gap_simulation(),
    }

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    all_ok = True
    for name, ok in results.items():
        mark = PASS_MARK if ok else FAIL_MARK
        print(f"  {mark} {name}")
        if not ok:
            all_ok = False

    print(f"\n{'=' * 60}")
    if all_ok:
        print("ALL SCENARIOS PASSED")
        sys.exit(0)
    else:
        print("SOME SCENARIOS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
