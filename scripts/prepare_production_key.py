"""
Prepare the Ed25519 private key for production deployment.

Reads your local ~/.epi/keys/default.key and outputs:
1. Base64-encoded raw private key (for EPI_ATTESTATION_PRIVATE_KEY env var)
2. The matching public key hex (for did.json)

Usage:
    python scripts/prepare_production_key.py

Then copy the base64 output into your Railway/Render environment variable.
"""

from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    key_path = Path.home() / ".epi" / "keys" / "default.key"
    if not key_path.exists():
        print(f"Key not found: {key_path}")
        print("Generate one with: epi keys generate")
        return

    pem_data = key_path.read_bytes()
    private_key = serialization.load_pem_private_key(pem_data, password=None)

    if not isinstance(private_key, Ed25519PrivateKey):
        print("Error: Key is not Ed25519")
        return

    # Raw private key bytes (32 bytes)
    raw_private = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    private_b64 = base64.b64encode(raw_private).decode("utf-8")

    # Raw public key bytes (32 bytes)
    public_key = private_key.public_key()
    raw_public = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_hex = raw_public.hex()

    print("=" * 70)
    print("PRODUCTION KEY SETUP")
    print("=" * 70)
    print()
    print("1. Set this as Railway/Render environment variable:")
    print("   EPI_ATTESTATION_PRIVATE_KEY")
    print()
    print(private_b64)
    print()
    print("2. Verify your DID document has this public key:")
    print(f"   {public_hex}")
    print()
    print("3. If the DID document has a different key, update it:")
    print("   assets/well-known/did.json")
    print("   EPI-OFFICIAL/public/.well-known/did.json")
    print()
    print("=" * 70)
    print("WARNING: Treat the base64 string above as a password.")
    print("Never commit it to GitHub or share it.")
    print("=" * 70)


if __name__ == "__main__":
    main()
