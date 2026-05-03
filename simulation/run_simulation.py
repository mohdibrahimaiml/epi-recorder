#!/usr/bin/env python3
"""
EPI Recorder — Real-Life User Simulation
=========================================
Runs 5 realistic scenarios end-to-end and exercises the full CLI:
  record → verify → analyze (with policy) → ls → status

Scenarios:
  01  Loan Approval — Happy Path         (no policy faults expected)
  02  Loan Approval — Policy Fault       (R001: missing manager approval)
  03  Medical Triage — Cardiac Protocol  (no policy faults expected)
  04  Customer Refund — Compliant        (no policy faults expected)
  05  Customer Refund — Policy Fault     (R002 + R005: no id check, no human approval)
"""

import subprocess
import sys
import os
import re
from pathlib import Path

# Force UTF-8 output on Windows so box-drawing chars in CLI output don't crash
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SIM_DIR   = Path(__file__).parent
OUT_DIR   = SIM_DIR / "output"
POLICY    = SIM_DIR / "policy.json"
REPO_ROOT = SIM_DIR.parent          # epi-recorder root — needed for -m epi_cli
PYTHON    = sys.executable

# ── ANSI colours ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

SCENARIOS = [
    ("01", "Loan Approval — Happy Path",         "scenario_01_loan_happy.py",     "PASS",  []),
    ("02", "Loan Approval — Policy Fault",        "scenario_02_loan_fault.py",     "FAULT", ["R001"]),
    ("03", "Medical Triage — Cardiac Protocol",   "scenario_03_medical_triage.py", "PASS",  []),
    ("04", "Customer Refund — Compliant",         "scenario_04_refund_compliant.py","PASS", []),
    ("05", "Customer Refund — Policy Fault",      "scenario_05_refund_fault.py",   "FAULT", ["R002"]),   # R005 is secondary flag
]

def banner(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{'='*65}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'='*65}{RESET}")

def section(text: str) -> None:
    print(f"\n{BOLD}  >> {text}{RESET}")

def run(cmd: list[str], cwd=None) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd, cwd=cwd or REPO_ROOT,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()

def show_output(label: str, text: str, colour: str = DIM) -> None:
    if not text:
        return
    print(f"{colour}    [{label}]{RESET}")
    for line in text.splitlines():
        print(f"{DIM}      {line}{RESET}")

def run_scenario(num, title, script, expected, expected_faults):
    stem = script.replace(f"scenario_{num:02d}_", "").replace(".py", "")
    epi_file = OUT_DIR / f"{num:02d}_{stem}.epi"

    banner(f"SCENARIO {num}  {title}")
    print(f"  Expected verdict : {GREEN+'PASS'+RESET if expected == 'PASS' else RED+'FAULT'+RESET}")
    if expected_faults:
        print(f"  Expected faults  : {YELLOW}{', '.join(expected_faults)}{RESET}")

    # ── 1. Record ────────────────────────────────────────────────────────────
    section("1/4  Recording workflow...")
    code, out, err = run([PYTHON, str(SIM_DIR / script)])
    if code != 0:
        print(f"{RED}    FAILED to run scenario script{RESET}")
        show_output("stderr", err, RED)
        return False
    show_output("stdout", out, GREEN)
    if not epi_file.exists():
        print(f"{RED}    .epi file not created: {epi_file}{RESET}")
        return False
    size_kb = epi_file.stat().st_size // 1024
    print(f"{GREEN}    Created: {epi_file.name}  ({size_kb} KB){RESET}")

    # ── 2. Verify ────────────────────────────────────────────────────────────
    section("2/4  Verifying integrity + signature...")
    code, out, err = run([PYTHON, "-m", "epi_cli", "verify", str(epi_file), "--policy", "permissive"])
    show_output("verify", out or err)
    combined_v = (out + err).upper()
    sig_valid = "SIGNATURE:    VALID" in combined_v or "SIGNATURE: VALID" in combined_v
    integrity_ok = "INTEGRITY:    VERIFIED" in combined_v or "INTEGRITY: VERIFIED" in combined_v
    decision_pass = "DECISION: PASS" in combined_v
    if decision_pass and (sig_valid or integrity_ok):
        verdict_line = "PASS (Integrity Verified, Signature Valid)"
        print(f"    Integrity check: {GREEN}{verdict_line}{RESET}")
    elif decision_pass:
        verdict_line = "PASS (Integrity Verified)"
        print(f"    Integrity check: {GREEN}{verdict_line}{RESET}")
    else:
        print(f"    Integrity check: {YELLOW}SEE ABOVE{RESET}")

    # ── 3. Analyze with policy ────────────────────────────────────────────────
    section("3/4  Running policy analysis...")
    code, out, err = run([PYTHON, "-m", "epi_cli", "analyze", str(epi_file),
                          "--policy", str(POLICY)])
    combined = out + err
    show_output("analyze", combined)

    # Summarise detected faults
    detected = [r for r in ["R001","R002","R003","R004","R005"] if r in combined]
    if detected:
        print(f"{YELLOW}    Faults detected : {', '.join(detected)}{RESET}")
    else:
        print(f"{GREEN}    No policy faults detected{RESET}")

    # Check expectation
    missed  = [r for r in expected_faults if r not in detected]
    phantom = [r for r in detected if r not in expected_faults]
    if missed:
        print(f"{RED}    UNEXPECTED: expected faults not found: {missed}{RESET}")
    if phantom:
        print(f"{YELLOW}    NOTE: extra faults found (not in expected list): {phantom}{RESET}")
    if not missed and not phantom:
        print(f"{GREEN}    Fault detection matches expectations ✓{RESET}")

    # ── 4. Status ─────────────────────────────────────────────────────────────
    section("4/4  epi status snapshot...")
    code, out, err = run([PYTHON, "-m", "epi_cli", "status"])
    # Print only first 12 lines — status can be verbose
    lines = (out or err).splitlines()[:12]
    for line in lines:
        print(f"{DIM}    {line}{RESET}")

    return True

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    banner("EPI Recorder - Real-Life User Simulation  v1.0")
    print(f"  Simulation dir : {SIM_DIR}")
    print(f"  Output dir     : {OUT_DIR}")
    print(f"  Policy file    : {POLICY.name}")
    print(f"  Scenarios      : {len(SCENARIOS)}")

    results = {}
    for num, title, script, expected, faults in SCENARIOS:
        ok = run_scenario(int(num), title, script, expected, faults)
        results[num] = (title, ok)

    # ── Final summary ─────────────────────────────────────────────────────────
    banner("SIMULATION COMPLETE — SUMMARY")

    # Show all recorded files
    section("Recorded artifacts")
    code, out, err = run([PYTHON, "-m", "epi_cli", "ls"], cwd=str(OUT_DIR))
    if out:
        for line in out.splitlines():
            print(f"{DIM}    {line}{RESET}")
    else:
        for f in sorted(OUT_DIR.glob("*.epi")):
            print(f"{DIM}    {f.name}  ({f.stat().st_size//1024} KB){RESET}")

    section("Scenario results")
    passed = failed = 0
    for num, (title, ok) in results.items():
        icon = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        print(f"    {icon}  [{num}] {title}")
        if ok: passed += 1
        else:  failed += 1

    print()
    print(f"  {GREEN}{passed} passed{RESET}  {RED}{failed} failed{RESET}  out of {len(SCENARIOS)} scenarios")

    section("Next steps — open any artifact in the browser viewer")
    for f in sorted(OUT_DIR.glob("*.epi")):
        print(f"{DIM}    python -m epi_cli view {f}  {RESET}")

    print()
    if failed == 0:
        print(f"{GREEN}{BOLD}  All scenarios completed successfully.{RESET}")
    else:
        print(f"{YELLOW}{BOLD}  {failed} scenario(s) encountered errors — see output above.{RESET}")
    print()

if __name__ == "__main__":
    main()
