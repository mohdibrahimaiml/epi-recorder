"""
Generate deterministic golden .epi artifacts for backward compatibility tests.
Run this script manually whenever the contract intentionally changes.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.container import EPIContainer, EPI_CONTAINER_FORMAT_LEGACY, EPI_CONTAINER_FORMAT_ENVELOPE
from epi_core.schemas import ManifestModel
from epi_core.trust import sign_manifest

GOLDEN_DIR = Path(__file__).with_suffix("").parent / "golden"
DETERMINISTIC_SEED = b"\x42" * 32
FIXED_UUID = UUID("550e8400-e29b-41d4-a716-446655440000")
FIXED_CREATED_AT = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)


def _make_key():
    return Ed25519PrivateKey.from_private_bytes(DETERMINISTIC_SEED)


def _signer(manifest: ManifestModel) -> ManifestModel:
    """Deterministic signer for golden artifacts."""
    key = _make_key()
    return sign_manifest(manifest, key, key_name="golden")


def generate():
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    # Build minimal workspace
    ws_dir = GOLDEN_DIR / "_workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "steps.jsonl").write_text(
        json.dumps({"index": 0, "timestamp": "2025-01-15T10:30:00Z", "kind": "shell.command", "content": {"cmd": "echo hello"}}) + "\n",
        encoding="utf-8",
    )
    (ws_dir / "environment.json").write_text("{}", encoding="utf-8")

    # Common manifest — pack will mutate file_manifest, trust, viewer_version, etc.
    manifest = ManifestModel(
        spec_version="4.0.1",
        workflow_id=FIXED_UUID,
        created_at=FIXED_CREATED_AT,
        cli_command="epi record --out golden.epi -- python demo.py",
        goal="Golden artifact for compatibility testing",
        tags=["golden", "compatibility"],
    )

    # Legacy artifact
    legacy_path = GOLDEN_DIR / "golden_legacy.epi"
    EPIContainer.pack(
        source_dir=ws_dir,
        manifest=manifest,
        output_path=legacy_path,
        signer_function=_signer,
        container_format=EPI_CONTAINER_FORMAT_LEGACY,
        generate_analysis=False,
    )
    print(f"Generated: {legacy_path} ({legacy_path.stat().st_size} bytes)")

    # Envelope artifact — need a fresh manifest because pack mutates in-place
    manifest2 = ManifestModel(
        spec_version="4.0.1",
        workflow_id=FIXED_UUID,
        created_at=FIXED_CREATED_AT,
        cli_command="epi record --out golden.epi -- python demo.py",
        goal="Golden artifact for compatibility testing",
        tags=["golden", "compatibility"],
    )
    envelope_path = GOLDEN_DIR / "golden_envelope.epi"
    EPIContainer.pack(
        source_dir=ws_dir,
        manifest=manifest2,
        output_path=envelope_path,
        signer_function=_signer,
        container_format=EPI_CONTAINER_FORMAT_ENVELOPE,
        generate_analysis=False,
    )
    print(f"Generated: {envelope_path} ({envelope_path.stat().st_size} bytes)")

    # Cleanup workspace
    import shutil
    shutil.rmtree(ws_dir, ignore_errors=True)
    print("Done.")


if __name__ == "__main__":
    generate()
