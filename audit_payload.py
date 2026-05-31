import json
import hashlib
import os

with open(os.path.join("audit_dir", "manifest.json"), "r", encoding="utf-8") as f:
    manifest = json.load(f)

# Read the zip payload hash from the EPI header.
# We'll just hash the refund_case.epi file starting after the EPI1 envelope.
# Actually, the envelope is something like: b"EPI1", 2 bytes version, 32 bytes hash.
with open("refund_case.epi", "rb") as f:
    header = f.read(4)
    if header == b"EPI1":
        version = f.read(2)
        expected_payload_hash = f.read(32).hex()
        payload = f.read()
        actual_payload_hash = hashlib.sha256(payload).hexdigest()
        print(f"Header Payload Hash: {expected_payload_hash}")
        print(f"Actual Payload Hash: {actual_payload_hash}")
        
        manifest_payload_hash = manifest.get("trust", {}).get("payload_hash")
        print(f"Manifest Payload Hash: {manifest_payload_hash}")
        
        if actual_payload_hash != expected_payload_hash:
            print("Payload tampering detected! The ZIP file was modified after sealing, but the outer envelope header wasn't updated (or vice versa).")
        else:
            print("Payload hash matches envelope.")
    else:
        print("Not an EPI envelope format.")
