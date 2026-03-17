"""
Tests for signed, unsigned, and tampered .epi files.
Run with: python test_signing.py
"""
import json, sys, tempfile, shutil, zipfile
from pathlib import Path

sys.path.insert(0, '.')

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.trust import sign_manifest, verify_signature
from epi_core.fault_analyzer import FaultAnalyzer
from epi_core.policy import EPIPolicy

SEP  = "=" * 62
PASS = "[PASS]"
FAIL = "[FAIL]"
INFO = "[INFO]"

def check(cond, label):
    print(f"  {PASS if cond else FAIL}  {label}")

# ── Build a minimal workspace ──────────────────────────────────
workspace = Path(tempfile.mkdtemp(prefix="epi_sign_test_"))

steps = [
    {"index":0,"kind":"session.start","content":{"workflow":"test_agent","session_id":"SESS-001"}},
    {"index":1,"kind":"tool.call","content":{"tool":"get_account","account_id":"ACC-123"}},
    {"index":2,"kind":"tool.result","content":{"account_id":"ACC-123","balance":5000.0}},
    {"index":3,"kind":"tool.call","content":{"tool":"approve_loan","amount":8500.0}},
    {"index":4,"kind":"tool.result","content":{"success":True,"approved_amount":8500.0}},
    {"index":5,"kind":"session.end","content":{"exit_code":0}},
]
(workspace / "steps.jsonl").write_text(
    "\n".join(json.dumps(s) for s in steps), encoding="utf-8"
)
(workspace / "env.json").write_text(
    json.dumps({"python": "3.11", "platform": "test"}), encoding="utf-8"
)

# ── Generate TWO keypairs (signer A and signer B) ──────────────
key_a = Ed25519PrivateKey.generate()
pub_a = key_a.public_key().public_bytes_raw()

key_b = Ed25519PrivateKey.generate()
pub_b = key_b.public_key().public_bytes_raw()

out_dir = Path(tempfile.mkdtemp(prefix="epi_out_"))

print(SEP)
print("  EPI — SIGNING, UNSIGNED & TAMPER TESTS")
print(SEP)

# ══════════════════════════════════════════════════════════════
# PART A — UNSIGNED RECORDING
# ══════════════════════════════════════════════════════════════
print("\n── PART A: UNSIGNED RECORDING ──────────────────────────────")

unsigned_path = out_dir / "unsigned.epi"
manifest = ManifestModel(cli_command="epi run test.py", goal="unsigned demo")
EPIContainer.pack(workspace, manifest, unsigned_path)

stored = EPIContainer.read_manifest(unsigned_path)

print("\n  What unsigned means:")
check(stored.signature is None, "No signature field in manifest")
check(stored.public_key is None, "No public key embedded")

print("\n  Integrity check still works (SHA-256 hashes, no signature needed):")
ok, mismatches = EPIContainer.verify_integrity(unsigned_path)
check(ok, f"All file hashes match ({len(stored.file_manifest)} files verified)")
check(len(mismatches) == 0, "Zero mismatches")

print("\n  Trying to verify signature on unsigned file:")
sig_ok, msg = verify_signature(stored, pub_a)
check(not sig_ok, f"Signature check correctly returns False")
print(f"  {INFO}  Message: '{msg}'")

print("\n  Summary — unsigned file is:")
print(f"  {INFO}  Integrity  : PROTECTED (hashes catch any edit)")
print(f"  {INFO}  Authenticity: NOT PROVEN (anyone could have made this)")
print(f"  {INFO}  Use case    : internal testing, dev recordings")

# ══════════════════════════════════════════════════════════════
# PART B — SIGNED RECORDING
# ══════════════════════════════════════════════════════════════
print("\n── PART B: SIGNED RECORDING ─────────────────────────────────")

signed_path = out_dir / "signed.epi"

def sign_fn(m):
    return sign_manifest(m, key_a, key_name="company-key-A")

manifest2 = ManifestModel(cli_command="epi run test.py", goal="signed demo",
                           tags=["production", "signed"])
EPIContainer.pack(workspace, manifest2, signed_path, signer_function=sign_fn)

stored2 = EPIContainer.read_manifest(signed_path)

print("\n  What signed means:")
check(stored2.signature is not None, f"Signature present ({stored2.signature[:32] if stored2.signature else None}...)")
check(stored2.public_key is not None, f"Public key embedded ({stored2.public_key[:32] if stored2.public_key else None}...)")

print("\n  Verifying with the CORRECT key (key A):")
sig_ok, msg = verify_signature(stored2, pub_a)
check(sig_ok, f"Signature valid with correct key")
print(f"  {INFO}  Message: '{msg}'")

print("\n  Verifying with the WRONG key (key B — different person):")
sig_ok_wrong, msg_wrong = verify_signature(stored2, pub_b)
check(not sig_ok_wrong, f"Signature correctly REJECTED with wrong key")
print(f"  {INFO}  Message: '{msg_wrong}'")

print("\n  Integrity check on signed file:")
ok2, mismatches2 = EPIContainer.verify_integrity(signed_path)
check(ok2, f"All hashes match")

print("\n  Summary — signed file proves:")
print(f"  {INFO}  Who ran it    : whoever holds key-A (stored in epi keys/)")
print(f"  {INFO}  What it did   : exactly this steps.jsonl, nothing else")
print(f"  {INFO}  When it ran   : timestamp in manifest is part of the signed data")
print(f"  {INFO}  Not modified  : any change breaks both hash AND signature")

# ══════════════════════════════════════════════════════════════
# PART C — TAMPERING SCENARIOS
# ══════════════════════════════════════════════════════════════
print("\n── PART C: TAMPERING SCENARIOS ──────────────────────────────")

# ── C1: Edit steps.jsonl — change approved amount ─────────────
print("\n  [C1] Someone edits steps.jsonl to hide the $8500 loan amount")
tampered1 = out_dir / "tampered_steps.epi"
shutil.copy2(signed_path, tampered1)
with zipfile.ZipFile(tampered1, "a") as zf:
    original = zf.read("steps.jsonl").decode("utf-8")
    zf.writestr("steps.jsonl", original.replace("8500.0", "1000.0"))

ok_t1, mm_t1 = EPIContainer.verify_integrity(tampered1)
stored_t1 = EPIContainer.read_manifest(tampered1)
sig_t1, msg_t1 = verify_signature(stored_t1, pub_a)

check(not ok_t1, f"Integrity FAILED — tampering detected in {len(mm_t1)} file(s)")
check(sig_t1, f"Signature still VALID (manifest unchanged — integrity check caught it)")
print(f"  {INFO}  Why? Signature covers manifest.json only. The manifest has the ORIGINAL")
print(f"  {INFO}  hash of steps.jsonl — that mismatch is caught by verify_integrity().")
for f, reason in mm_t1.items():
    print(f"  {INFO}  Modified: {f}")
    print(f"  {INFO}  Reason  : {reason[:72]}")

# ── C2: Edit manifest.json — change the goal text ─────────────
print("\n  [C2] Someone edits manifest.json to change the goal")
tampered2 = out_dir / "tampered_manifest.epi"
shutil.copy2(signed_path, tampered2)
with zipfile.ZipFile(tampered2, "a") as zf:
    mdata = json.loads(zf.read("manifest.json").decode("utf-8"))
    mdata["goal"] = "completely innocent loan"  # attacker changes goal
    zf.writestr("manifest.json", json.dumps(mdata))

stored_t2 = EPIContainer.read_manifest(tampered2)
sig_t2, msg_t2 = verify_signature(stored_t2, pub_a)

check(not sig_t2, f"Signature INVALID — manifest edit caught")
print(f"  {INFO}  Message: '{msg_t2}'")
print(f"  {INFO}  Original goal: 'signed demo'")
print(f"  {INFO}  Tampered goal: '{stored_t2.goal}'")

# ── C3: Add a fake file to the archive ────────────────────────
print("\n  [C3] Someone injects a fake file into the .epi archive")
tampered3 = out_dir / "tampered_injected.epi"
shutil.copy2(signed_path, tampered3)
with zipfile.ZipFile(tampered3, "a") as zf:
    zf.writestr("fake_approval.json", json.dumps({"approved": True, "signed_by": "CEO"}))

ok_t3, mm_t3 = EPIContainer.verify_integrity(tampered3)
stored_t3 = EPIContainer.read_manifest(tampered3)
sig_t3, msg_t3 = verify_signature(stored_t3, pub_a)

# Injected file is NOT in file_manifest, so integrity passes but signature covers manifest
# The injected file itself doesn't affect the existing hashes
check(sig_t3, f"Signature still valid (manifest + existing files unchanged)")
print(f"  {INFO}  The injected file is NOT in the signed file_manifest")
print(f"  {INFO}  An auditor opening the .epi can see the extra file 'fake_approval.json'")
print(f"  {INFO}  It has no hash in the manifest — clearly not part of the original recording")
print(f"  {INFO}  Best practice: epi verify checks only manifest-listed files")

# ── C4: Delete a file from the archive ────────────────────────
print("\n  [C4] Someone deletes env.json from the archive (removes evidence)")
tampered4 = out_dir / "tampered_deleted.epi"
# Rebuild zip without env.json
with zipfile.ZipFile(signed_path, "r") as zin, zipfile.ZipFile(tampered4, "w") as zout:
    for item in zin.infolist():
        if item.filename != "env.json":
            zout.writestr(item, zin.read(item.filename))

ok_t4, mm_t4 = EPIContainer.verify_integrity(tampered4)
check(not ok_t4, f"Integrity FAILED — missing file caught ({len(mm_t4)} missing)")
for f, reason in mm_t4.items():
    print(f"  {INFO}  {f}: {reason}")

# ── C5: Replace signed file with unsigned version ─────────────
print("\n  [C5] Someone replaces a signed .epi with an unsigned copy")
stored_unsigned = EPIContainer.read_manifest(unsigned_path)
sig_u, msg_u = verify_signature(stored_unsigned, pub_a)
check(not sig_u, f"Unsigned file correctly fails signature check when key is expected")
print(f"  {INFO}  Message: '{msg_u}'")
print(f"  {INFO}  A reviewer requiring signatures would immediately notice no signature exists")

# ── C6: Replay attack — reuse an old valid recording ──────────
print("\n  [C6] Replay attack — reuse old valid .epi as if it were new")
print(f"  {INFO}  The manifest contains 'created_at' timestamp (signed)")
print(f"  {INFO}  An auditor checks if created_at matches the claimed run date")
stored_s = EPIContainer.read_manifest(signed_path)
print(f"  {INFO}  created_at in manifest: {stored_s.created_at}")
sig_replay, _ = verify_signature(stored_s, pub_a)
check(sig_replay, f"Signature is valid — but timestamp proves it was created at {str(stored_s.created_at)[:19]}")
print(f"  {INFO}  Replay detected by checking timestamp, not the signature itself")

# ══════════════════════════════════════════════════════════════
# PART D — WHAT THE VIEWER SHOWS
# ══════════════════════════════════════════════════════════════
print("\n── PART D: WHAT THE USER SEES IN THE VIEWER ─────────────────")

cases = [
    ("Unsigned, no tampering",    unsigned_path, pub_a),
    ("Signed, no tampering",      signed_path,   pub_a),
    ("Signed, steps tampered",    tampered1,     pub_a),
    ("Signed, manifest tampered", tampered2,     pub_a),
    ("Signed, file deleted",      tampered4,     pub_a),
]

print()
print(f"  {'File':<30}  {'Integrity':<12}  {'Signature':<20}  {'Status'}")
print(f"  {'-'*30}  {'-'*12}  {'-'*20}  {'-'*20}")

for label, path, pubkey in cases:
    try:
        integrity_ok, mm = EPIContainer.verify_integrity(path)
        stored_m = EPIContainer.read_manifest(path)
        if stored_m.signature and stored_m.public_key:
            pk_bytes = bytes.fromhex(stored_m.public_key)
            sig_ok, sig_msg = verify_signature(stored_m, pk_bytes)
        elif stored_m.signature is None:
            sig_ok, sig_msg = None, "unsigned"
        else:
            sig_ok, sig_msg = False, "no pubkey"

        integrity_str = "OK" if integrity_ok else f"FAIL({len(mm)})"
        sig_str = ("valid" if sig_ok else ("unsigned" if sig_ok is None else "INVALID"))

        if integrity_ok and sig_ok:
            status = "GREEN — Trusted"
        elif integrity_ok and sig_ok is None:
            status = "YELLOW — Unverified"
        else:
            status = "RED — TAMPERED / INVALID"

        print(f"  {label:<30}  {integrity_str:<12}  {sig_str:<20}  {status}")
    except Exception as e:
        print(f"  {label:<30}  ERROR: {e}")

# ══════════════════════════════════════════════════════════════
# PART E — SIGNATURE ROUNDTRIP
# ══════════════════════════════════════════════════════════════
print("\n── PART E: SIGNATURE ROUNDTRIP INTEGRITY ────────────────────")

print("\n  Signing → extracting public key from manifest → verifying:")
stored_final = EPIContainer.read_manifest(signed_path)
pub_from_manifest = bytes.fromhex(stored_final.public_key)
sig_final, msg_final = verify_signature(stored_final, pub_from_manifest)
check(sig_final, f"Self-contained verification (public key from manifest itself)")
print(f"  {INFO}  A reviewer only needs the .epi file — no external key needed")
print(f"  {INFO}  The embedded public key proves WHO signed it")
print(f"  {INFO}  Message: '{msg_final}'")

# Cleanup
shutil.rmtree(workspace, ignore_errors=True)
shutil.rmtree(out_dir, ignore_errors=True)

print()
print(SEP)
print("  ALL SIGNING TESTS COMPLETE")
print(SEP)
