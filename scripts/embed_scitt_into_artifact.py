"""
Embed a real SCITT statement and receipt into an existing .epi artifact.

This script:
1. Reads the manifest from an existing .epi file
2. Creates a SCITT Signed Statement (COSE_Sign1) from the manifest
3. Creates a SCITT Receipt (COSE_Sign1) using the service private key
4. Updates the manifest with SCITT governance metadata
5. Re-signs the manifest
6. Recreates the .epi ZIP with the SCITT artifacts embedded

Usage:
    python scripts/embed_scitt_into_artifact.py <input.epi> <output.epi> \
        --service-url https://epilabs.org/scitt

Environment:
    EPI_SCITT_SERVICE_PRIVATE_KEY -- Base64-encoded raw 32-byte Ed25519 private key
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.scitt import (
    create_scitt_receipt,
    create_scitt_statement,
    scitt_governance_from_info,
    SCITTServiceInfo,
)
from epi_core.trust import sign_manifest


def _load_producer_key():
    key_path = Path.home() / ".epi" / "keys" / "default.key"
    if not key_path.exists():
        raise FileNotFoundError(f"Producer key not found: {key_path}")
    pem = key_path.read_bytes()
    return serialization.load_pem_private_key(pem, password=None)


def _load_service_key() -> Ed25519PrivateKey:
    raw_b64 = os.environ.get("EPI_SCITT_SERVICE_PRIVATE_KEY")
    if not raw_b64:
        raise RuntimeError("Set EPI_SCITT_SERVICE_PRIVATE_KEY env var")
    key_bytes = base64.b64decode(raw_b64)
    if len(key_bytes) != 32:
        raise ValueError("EPI_SCITT_SERVICE_PRIVATE_KEY must be 32 raw bytes")
    return Ed25519PrivateKey.from_private_bytes(key_bytes)


def embed_scitt(
    input_path: Path,
    output_path: Path,
    service_url: str,
) -> None:
    # Load keys
    producer_key = _load_producer_key()
    service_key = _load_service_key()

    # Read manifest from existing artifact
    manifest = EPIContainer.read_manifest(input_path)

    # Derive issuer
    gov = manifest.governance or {}
    issuer = gov.get("did", "did:web:epilabs.org")

    # Create SCITT statement from the FINAL manifest
    statement_bytes = create_scitt_statement(manifest, producer_key, issuer=issuer)
    print(f"[OK] SCITT statement: {len(statement_bytes)} bytes")

    # Create receipt
    receipt_bytes = create_scitt_receipt(statement_bytes, service_key, kid=b"epilabs-scitt")
    print(f"[OK] SCITT receipt: {len(receipt_bytes)} bytes")

    # Build SCITT governance
    entry_id = hashlib.sha256(statement_bytes).hexdigest()[:32]
    info = SCITTServiceInfo(
        service_url=service_url,
        entry_id=entry_id,
        registered_at=datetime.now(UTC).isoformat(),
    )
    scitt_gov = scitt_governance_from_info(info, issuer=issuer)

    # Update manifest
    manifest_dict = manifest.model_dump(mode="json")
    manifest_dict.setdefault("governance", {})
    manifest_dict["governance"]["scitt"] = scitt_gov

    updated_manifest = ManifestModel(**manifest_dict)
    signed_manifest = sign_manifest(updated_manifest, producer_key, "default")

    # Recreate ZIP preserving order, replacing manifest.json and adding SCITT files
    import tempfile
    import shutil

    tmp_output = output_path.parent / (output_path.name + ".tmp")

    with zipfile.ZipFile(input_path, "r") as zf_in:
        with zipfile.ZipFile(tmp_output, "w", zipfile.ZIP_DEFLATED) as zf_out:
            seen_manifest = False
            seen_stmt = False
            seen_rcpt = False

            for info in zf_in.infolist():
                name = info.filename

                # Skip old manifest.json and SCITT artifacts (we'll write new ones)
                if name == "manifest.json":
                    if not seen_manifest:
                        zf_out.writestr("manifest.json", signed_manifest.model_dump_json(indent=2))
                        seen_manifest = True
                    continue

                if name == "artifacts/scitt/statement.cbor":
                    if not seen_stmt:
                        zf_out.writestr("artifacts/scitt/statement.cbor", statement_bytes)
                        seen_stmt = True
                    continue

                if name == "artifacts/scitt/receipt.cbor":
                    if not seen_rcpt:
                        zf_out.writestr("artifacts/scitt/receipt.cbor", receipt_bytes)
                        seen_rcpt = True
                    continue

                zf_out.writestr(info, zf_in.read(name))

            # Ensure SCITT artifacts are present if artifact didn't have them
            if not seen_stmt:
                zf_out.writestr("artifacts/scitt/statement.cbor", statement_bytes)
            if not seen_rcpt:
                zf_out.writestr("artifacts/scitt/receipt.cbor", receipt_bytes)

    # Atomic replace
    shutil.move(str(tmp_output), str(output_path))
    print(f"[OK] Artifact written: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Embed SCITT artifacts into .epi")
    parser.add_argument("input", type=Path, help="Input .epi file")
    parser.add_argument("output", type=Path, help="Output .epi file")
    parser.add_argument(
        "--service-url",
        default="https://epilabs.org/scitt",
        help="SCITT transparency service URL",
    )
    args = parser.parse_args()

    embed_scitt(args.input, args.output, args.service_url)


if __name__ == "__main__":
    main()
