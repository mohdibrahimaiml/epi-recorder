#!/usr/bin/env python3
"""
DID Mismatch Attack Test
=========================
Scenario: Attacker claims a legitimate DID (did:web:legit.org) but signs
with their own key — the DID resolves to a different key.

Expected behavior:
  - Integrity:    PASS (content unchanged)
  - Signature:    PASS (cryptographically valid)
  - Identity:     MISMATCH
  - Trust Level:  FAIL
  - Decision:     REJECT (under STANDARD policy)

If trust level is not FAIL → critical flaw (impersonation not detected).
"""

import json
import shutil
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from epi_core.schemas import ManifestModel
from epi_core.trust import (
    sign_manifest,
    create_verification_report,
    apply_policy,
    TrustRegistry,
    VerificationPolicy,
)
from epi_core.container import EPIContainer

# ── paths ──────────────────────────────────────────────
BASE = REPO_ROOT / "demo_workflows"
CLEAN = BASE / "loan_decision.epi"
ATTACKED = BASE / "loan_decision_did_mismatch.epi"


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
    tmp = epi_path.with_suffix(".tmp.epi")
    with zipfile.ZipFile(epi_path, "r") as zin:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "manifest.json":
                    data = json.dumps(manifest, indent=2).encode("utf-8")
                zout.writestr(item, data)
    shutil.move(tmp, epi_path)


def verify_epi(epi_path: Path) -> dict:
    """Run full verification in-process (so mocks apply)."""
    manifest = EPIContainer.read_manifest(epi_path)
    integrity_ok, mismatches = EPIContainer.verify_integrity(epi_path)

    from epi_core.trust import verify_embedded_manifest_signature
    signature_valid, signer_name, sig_message = verify_embedded_manifest_signature(manifest)

    registry = TrustRegistry()
    report = create_verification_report(
        integrity_ok=integrity_ok,
        signature_valid=signature_valid,
        signer_name=signer_name,
        mismatches=mismatches,
        manifest=manifest,
        trusted_registry=registry,
    )
    apply_policy(report, VerificationPolicy.STANDARD)
    return report


def main() -> int:
    print("=" * 70)
    print("DID MISMATCH ATTACK TEST")
    print("=" * 70)

    if not CLEAN.exists():
        print(f"ERROR: Clean artifact not found: {CLEAN}")
        return 1

    # ── Step 1: Extract original manifest ───────────────
    print("\n[1/5] Extracting original manifest ...")
    original_manifest = extract_manifest(CLEAN)
    original_key = original_manifest.get("public_key", "none")
    print(f"  Original public key: {original_key[:16]}...")

    # ── Step 2: Generate attacker keypair ───────────────
    print("\n[2/5] Generating attacker keypair ...")
    attacker_private_key, attacker_public_key_hex = generate_attacker_keypair()
    print(f"  Attacker public key: {attacker_public_key_hex[:16]}...")

    # ── Step 3: Inject DID claim + attacker key + re-sign ─
    print("\n[3/5] Injecting DID:web:legit.org claim + re-signing ...")
    shutil.copy2(CLEAN, ATTACKED)

    manifest = ManifestModel(**original_manifest)
    # Attacker claims they are legit.org
    manifest.governance = {"did": "did:web:legit.org"}
    manifest.public_key = attacker_public_key_hex
    signed_manifest = sign_manifest(manifest, attacker_private_key, key_name="attacker")

    write_manifest(ATTACKED, json.loads(signed_manifest.model_dump_json()))
    print("  Attacked artifact written.")

    # ── Step 4: Mock DID resolution and verify ──────────
    print("\n[4/5] Verifying with mocked DID resolution ...")
    # The legitimate DID resolves to a DIFFERENT key
    legit_did_doc = {
        "id": "did:web:legit.org",
        "verificationMethod": [{
            "id": "did:web:legit.org#key1",
            "type": "Ed25519VerificationKey2020",
            "publicKeyHex": "b" * 64,  # NOT the attacker's key
        }],
    }

    with patch("epi_core.did_web.resolve_did_web", return_value=legit_did_doc):
        with patch("epi_core.did_web.extract_ed25519_key", return_value="b" * 64):
            report = verify_epi(ATTACKED)

    # ── Step 5: Analyze results ─────────────────────────
    print("\n[5/5] Analyzing results ...")
    print()

    integrity = report["facts"]["integrity_ok"]
    signature = report["facts"]["signature_valid"]
    identity_status = report["identity"]["status"]
    trust_level = report["trust_level"]
    decision = report["decision"]["status"]

    print(f"  Integrity:    {'PASS' if integrity else 'FAIL'}")
    print(f"  Signature:    {'PASS' if signature else 'FAIL'}")
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

    if identity_status != "MISMATCH":
        print(f"  [FAIL] Identity should be MISMATCH, got {identity_status}")
        passed = False
    else:
        print("  [OK]   Identity correctly MISMATCH")

    if trust_level != "FAIL":
        print(f"  [CRITICAL FLAW] Trust level should be FAIL, got {trust_level}")
        passed = False
    else:
        print("  [OK]   Trust level correctly FAIL")

    if decision != "FAIL":
        print(f"  [CRITICAL FLAW] Decision should be FAIL, got {decision}")
        passed = False
    else:
        print("  [OK]   Decision correctly FAIL")

    print()
    if passed:
        print("RESULT: System correctly detects and rejects DID impersonation attacks.")
    else:
        print("RESULT: System has a CRITICAL FLAW in DID impersonation handling.")
    print()

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
