#!/usr/bin/env python3
"""
Key Substitution Attack Test
==============================
Scenario: Attacker replaces the embedded public key and re-signs with their own key.

Expected behavior:
  - Integrity: PASS (content unchanged)
  - Signature: PASS (cryptographically valid)
  - Identity: UNKNOWN (attacker key not in trust registry)
  - Trust level: MUST NOT be HIGH

If trust level is HIGH → critical flaw (identity not verified before granting high trust)
"""

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from epi_core.schemas import ManifestModel
from epi_core.serialize import get_canonical_hash
from epi_core.trust import sign_manifest

# ── paths ──────────────────────────────────────────────
BASE = REPO_ROOT / "demo_workflows"
CLEAN = BASE / "loan_decision.epi"
ATTACKED = BASE / "loan_decision_attacked.epi"


def generate_attacker_keypair():
    """Generate a fresh Ed25519 keypair for the attacker."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_key_hex = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    ).hex()
    return private_key, public_key_hex


def extract_manifest(epi_path: Path) -> dict:
    with zipfile.ZipFile(epi_path, "r") as zf:
        return json.loads(zf.read("manifest.json"))


def write_manifest(epi_path: Path, manifest: dict) -> None:
    """Rewrite manifest.json inside the EPI zip."""
    import tempfile
    tmp = epi_path.with_suffix(".tmp.epi")
    with zipfile.ZipFile(epi_path, "r") as zin:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "manifest.json":
                    data = json.dumps(manifest, indent=2).encode("utf-8")
                zout.writestr(item, data)
    shutil.move(tmp, epi_path)


def run_verify(path: Path) -> dict:
    r = subprocess.run(
        ["epi", "verify", str(path), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
    )
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        print("STDOUT:", r.stdout)
        print("STDERR:", r.stderr)
        raise


def main() -> int:
    print("=" * 70)
    print("KEY SUBSTITUTION ATTACK TEST")
    print("=" * 70)

    if not CLEAN.exists():
        print(f"ERROR: Clean artifact not found: {CLEAN}")
        return 1

    # ── Step 1: Extract original manifest ───────────────
    print("\n[1/5] Extracting original manifest ...")
    original_manifest = extract_manifest(CLEAN)
    original_key = original_manifest["public_key"]
    print(f"  Original public key: {original_key[:16]}...")

    # ── Step 2: Generate attacker keypair ───────────────
    print("\n[2/5] Generating attacker keypair ...")
    attacker_private_key, attacker_public_key_hex = generate_attacker_keypair()
    print(f"  Attacker public key: {attacker_public_key_hex[:16]}...")

    # ── Step 3: Replace key and re-sign ─────────────────
    print("\n[3/5] Replacing key and re-signing manifest ...")
    shutil.copy2(CLEAN, ATTACKED)

    # Load manifest as ManifestModel
    manifest = ManifestModel(**original_manifest)

    # Replace public key with attacker's key
    manifest.public_key = attacker_public_key_hex

    # Re-sign with attacker's key
    signed_manifest = sign_manifest(manifest, attacker_private_key, key_name="attacker")

    # Write back to EPI
    write_manifest(ATTACKED, json.loads(signed_manifest.model_dump_json()))
    print("  Attacked artifact written.")

    # ── Step 4: Verify attacked artifact ────────────────
    print("\n[4/5] Verifying attacked artifact ...")
    report = run_verify(ATTACKED)

    # ── Step 5: Analyze results ─────────────────────────
    print("\n[5/5] Analyzing results ...")
    print()

    integrity = report.get("facts", {}).get("integrity_ok", False)
    signature = report.get("facts", {}).get("signature_valid")
    identity_status = report.get("identity", {}).get("status", "UNKNOWN")
    trust_level = report.get("trust_level", "NONE")
    decision = report.get("decision", {}).get("status", "FAIL")

    print(f"  Integrity:    {'PASS' if integrity else 'FAIL'}")
    print(f"  Signature:    {'PASS' if signature else 'FAIL'} (valid from attacker's key)")
    print(f"  Identity:     {identity_status}")
    print(f"  Trust Level:  {trust_level}")
    print(f"  Decision:     {decision}")
    print()

    # ── Evaluation ──────────────────────────────────────
    passed = True

    if not integrity:
        print("  [FAIL] Integrity should be PASS (content was not modified)")
        passed = False
    else:
        print("  [OK]   Integrity correctly PASS")

    if not signature:
        print("  [FAIL] Signature should be PASS (cryptographically valid)")
        passed = False
    else:
        print("  [OK]   Signature correctly PASS")

    if identity_status != "UNKNOWN":
        print(f"  [FAIL] Identity should be UNKNOWN, got {identity_status}")
        passed = False
    else:
        print("  [OK]   Identity correctly UNKNOWN")

    if trust_level == "HIGH":
        print("  [CRITICAL FLAW] Trust level is HIGH for an unknown identity!")
        print("                   Key substitution attack would succeed.")
        passed = False
    else:
        print(f"  [OK]   Trust level correctly NOT HIGH ({trust_level})")

    print()
    if passed:
        print("RESULT: System is ROBUST against key substitution attacks.")
    else:
        print("RESULT: System has a CRITICAL FLAW.")
    print()

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
