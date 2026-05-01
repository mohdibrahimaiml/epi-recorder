#!/usr/bin/env python3
"""
Forensic Audit & Tamper-Evidence Demo
======================================
Demonstrates how a third-party auditor can independently verify EPI artifacts,
detect tampering, and produce a court-ready audit report.

Artifacts:
  1. loan_decision.epi      - Clean, signed loan approval (HIGH trust)
  2. loan_decision_unsigned.epi - Same workflow but unsigned (MEDIUM trust)
  3. loan_decision_tampered.epi - Tampered payload (FAIL)

Usage:
    python forensic_audit_demo.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.helpers.artifacts import rewrite_legacy_member  # type: ignore

# ── paths ──────────────────────────────────────────────
BASE = Path(__file__).resolve().parent
CLEAN = BASE / "loan_decision.epi"
UNSIGNED = BASE / "loan_decision_unsigned.epi"
TAMPERED = BASE / "loan_decision_tampered.epi"
AUDIT_REPORT = BASE / "AUDIT_REPORT.md"


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
    )


def header(title: str, width: int = 72) -> str:
    pad = "-" * ((width - len(title) - 2) // 2)
    return f"\n{pad} {title} {pad}"


def create_tampered() -> None:
    """Create a tampered copy by corrupting a step inside the archive."""
    print("  -> Creating tampered artifact ...")
    import json
    shutil.copy2(CLEAN, TAMPERED)
    # Read steps.jsonl, corrupt first step
    import zipfile
    with zipfile.ZipFile(TAMPERED, "r") as zf:
        steps = zf.read("steps.jsonl").decode("utf-8").strip().split("\n")
    # Corrupt the first step's content
    first_step = json.loads(steps[0])
    first_step["content"]["workflow_name"] = first_step["content"]["workflow_name"] + "_TAMPERED"
    steps[0] = json.dumps(first_step)
    rewrite_legacy_member(TAMPERED, "steps.jsonl", "\n".join(steps).encode("utf-8"))
    print(f"     Written: {TAMPERED}")


def create_unsigned() -> None:
    """Create an unsigned copy by stripping the signature from manifest."""
    print("  -> Creating unsigned artifact ...")
    import json

    tmp = BASE / "_tmp_unsigned.epi"
    shutil.copy2(CLEAN, tmp)

    import zipfile
    tmp2 = BASE / "_tmp_unsigned2.epi"
    shutil.copy2(tmp, tmp2)
    tmp.unlink()
    with zipfile.ZipFile(tmp2, "r") as zin:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "manifest.json":
                    manifest = json.loads(data)
                    manifest["signature"] = None
                    data = json.dumps(manifest, indent=2).encode("utf-8")
                zout.writestr(item, data)
    tmp2.unlink()
    if UNSIGNED.exists():
        UNSIGNED.unlink()
    shutil.move(tmp, UNSIGNED)
    print(f"     Written: {UNSIGNED}")


def verify(path: Path) -> dict:
    """Run epi verify and parse the trust level."""
    print(f"  -> Verifying: {path.name}")
    r = run(["epi", "verify", str(path)])
    out = r.stdout + r.stderr

    # Trust level based on DECISION + Identity + Signature
    if "DECISION: PASS" in out:
        if "Signature:    Valid" in out and "Status:       KNOWN" in out:
            trust = "HIGH"
        elif "Signature:    Valid" in out:
            trust = "LOW"   # Valid sig but unknown identity
        elif "Signature:    Unsigned" in out:
            trust = "MEDIUM"
        else:
            trust = "LOW"
    elif "DECISION: FAIL" in out:
        trust = "FAIL"
    else:
        trust = "UNKNOWN"

    integrity = "PASS" if "Integrity:    Verified" in out else "FAIL"
    signature = "PASS" if "Signature:    Valid" in out else ("FAIL" if "Signature:    Invalid" in out else "N/A")

    return {
        "file": path.name,
        "trust": trust,
        "integrity": integrity,
        "signature": signature,
        "output": out,
    }


def generate_report(results: list[dict]) -> str:
    """Build a Markdown audit report."""
    lines = [
        "# Forensic Audit Report - EPI Artifacts",
        "",
        "**Auditor:** Independent Third-Party Verifier  ",
        "**Date:** Auto-generated  ",
        "**Tool:** `epi verify` (compatibility-locked v4.0.1)  ",
        "",
        "## Executive Summary",
        "",
        f"| Artifact | Trust Level | Integrity | Signature | Verdict |",
        f"|----------|-------------|-----------|-----------|---------|",
    ]

    for r in results:
        verdict = "[ACCEPT]" if r["trust"] == "HIGH" else (
            "[CONDITIONAL]" if r["trust"] == "MEDIUM" else (
                "[REJECT]" if r["trust"] in ("FAIL", "NONE") else "[VERIFY IDENTITY]"
            )
        )
        lines.append(
            f"| `{r['file']}` | {r['trust']} | {r['integrity']} | {r['signature']} | {verdict} |"
        )

    lines += [
        "",
        "## Detailed Findings",
        "",
    ]

    for r in results:
        lines += [
            f"### {r['file']}",
            "",
            f"- **Trust Level:** {r['trust']}",
            f"- **Integrity Check:** {r['integrity']}",
            f"- **Signature Check:** {r['signature']}",
            "",
            "**Raw `epi verify` output:**",
            "```",
            r["output"].strip(),
            "```",
            "",
        ]

    lines += [
        "## Conclusions",
        "",
        "1. **Clean signed artifacts with known identity** achieve **HIGH** trust - suitable for regulatory submission.",
        "   (`loan_decision.epi` shows LOW because the signer's key is not in a trust registry.)",
        "2. **Signed artifacts with unknown identity** achieve **LOW** trust - signature is valid but signer is unverified.",
        "   This is the expected result for key substitution attacks: integrity passes, signature passes, but identity is UNKNOWN.",
        "3. **Unsigned artifacts** (`loan_decision_unsigned.epi`) achieve **MEDIUM** trust - acceptable for internal review only.",
        "4. **Tampered artifacts** (`loan_decision_tampered.epi`) are **FAIL** - integrity compromise is detected immediately, regardless of signature validity.",
        "",
        "---",
        "*This report was generated automatically by the EPI forensic audit demo.*",
    ]

    return "\n".join(lines)


def main() -> int:
    print(header("FORENSIC AUDIT & TAMPER-EVIDENCE DEMO"))

    if not CLEAN.exists():
        print(f"ERROR: Clean artifact not found: {CLEAN}")
        print("Run: python demo_workflows/loan_approval.py")
        return 1

    # ── Prepare artifacts ──────────────────────────────
    print("\n[1/4] Preparing artifacts ...")
    create_unsigned()
    create_tampered()

    # ── Verify each artifact ───────────────────────────
    print("\n[2/4] Running independent verification ...")
    results = [verify(CLEAN), verify(UNSIGNED), verify(TAMPERED)]

    # ── Generate report ────────────────────────────────
    print("\n[3/4] Generating audit report ...")
    report = generate_report(results)
    AUDIT_REPORT.write_text(report, encoding="utf-8")
    print(f"     Written: {AUDIT_REPORT}")

    # ── Summary ────────────────────────────────────────
    print(header("AUDIT SUMMARY"))
    for r in results:
        icon = "[OK]" if r["trust"] == "HIGH" else (
            "[WARN]" if r["trust"] == "MEDIUM" else (
                "[FAIL]" if r["trust"] in ("FAIL", "NONE") else "[VERIFY]"
            )
        )
        print(f"  {icon} {r['file']:30s} -> Trust: {r['trust']:8s} | Integrity: {r['integrity']} | Signature: {r['signature']}")

    print(f"\nFull report: {AUDIT_REPORT}\n")

    # Return non-zero if any tampered artifact wasn't caught
    tampered = next((r for r in results if "tampered" in r["file"]), None)
    if tampered and tampered["trust"] != "FAIL":
        print("ERROR: Tampered artifact was NOT detected!")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
