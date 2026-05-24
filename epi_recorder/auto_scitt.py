"""
Auto-SCITT Anchoring for EPI artifacts.

Automatically submits signed .epi artifacts to a SCITT Transparency Service
when EPI_SCITT_URL and EPI_SCITT_AUTO_ANCHOR=1 are set.

Usage:
    from epi_recorder.auto_scitt import AutoSCITTAnchor
    anchor = AutoSCITTAnchor()
    anchor.anchor_if_configured(manifest, epi_path, private_key, key_name)

Environment variables:
    EPI_SCITT_URL          — SCITT transparency service endpoint
    EPI_SCITT_AUTO_ANCHOR  — Set to "1" to enable auto-anchoring
    EPI_SCITT_TIMEOUT      — HTTP timeout in seconds (default: 30)
"""

from __future__ import annotations

import os
import time
import warnings
from pathlib import Path
from typing import Any

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.scitt import (
    SCITTRegistrationError,
    SCITTServiceClient,
    create_scitt_statement,
    scitt_governance_from_info,
    verify_scitt_statement,
)
from epi_core.trust import sign_manifest


class AutoSCITTAnchor:
    """
    Handles automatic SCITT anchoring of EPI artifacts after signing.

    Features:
    - Exponential backoff retry (1s, 2s, 4s, 8s)
    - Fail-open: .epi creation is never blocked by SCITT failure
    - Embeds receipt directly into the .epi artifact
    - Updates manifest.governance.scitt with service metadata
    """

    def __init__(
        self,
        service_url: str | None = None,
        timeout: int | None = None,
        max_retries: int = 4,
    ):
        self.service_url = service_url or os.environ.get("EPI_SCITT_URL")
        self.timeout = timeout or int(os.environ.get("EPI_SCITT_TIMEOUT", "30"))
        self.max_retries = max_retries
        self._enabled = os.environ.get("EPI_SCITT_AUTO_ANCHOR", "0") == "1"

    def is_configured(self) -> bool:
        """Return True if auto-anchoring is enabled and a service URL is set."""
        return self._enabled and bool(self.service_url)

    def anchor_if_configured(
        self,
        manifest: ManifestModel,
        epi_path: Path,
        private_key: Any,
        key_name: str = "default",
    ) -> bool:
        """
        Anchor the artifact to SCITT if configured.

        Args:
            manifest: The signed manifest
            epi_path: Path to the .epi file
            private_key: Ed25519 private key for SCITT statement signing
            key_name: Name of the signing key

        Returns:
            True if anchored successfully, False if skipped or failed.
        """
        if not self.is_configured():
            return False

        try:
            return self._anchor(manifest, epi_path, private_key, key_name)
        except Exception as exc:
            warnings.warn(
                f"SCITT auto-anchoring failed (artifact saved regardless): {exc}",
                UserWarning,
                stacklevel=2,
            )
            return False

    def _anchor(
        self,
        manifest: ManifestModel,
        epi_path: Path,
        private_key: Any,
        key_name: str,
    ) -> bool:
        """Internal anchoring logic with retry."""
        issuer = self._derive_issuer(manifest)

        # Create SCITT Signed Statement
        statement_bytes = create_scitt_statement(manifest, private_key, issuer=issuer)

        # Submit to transparency service with exponential backoff
        client = SCITTServiceClient(self.service_url, timeout=self.timeout)
        receipt_bytes = None
        info = None
        last_error = None

        for attempt in range(self.max_retries):
            try:
                receipt_bytes, info = client.register(statement_bytes)
                break
            except SCITTRegistrationError as exc:
                last_error = exc
                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt  # 1s, 2s, 4s, 8s
                    time.sleep(wait)
                else:
                    raise SCITTRegistrationError(
                        f"SCITT registration failed after {self.max_retries} attempts: {exc}"
                    ) from exc

        if receipt_bytes is None or info is None:
            raise SCITTRegistrationError("SCITT registration returned no receipt")

        # Embed receipt into .epi artifact
        self._embed_receipt(
            epi_path, manifest, statement_bytes, receipt_bytes, info,
            private_key, key_name,
        )
        return True

    def _derive_issuer(self, manifest: ManifestModel) -> str:
        """Derive issuer identifier from manifest governance."""
        gov = manifest.governance or {}
        if gov.get("did"):
            return gov["did"]
        if manifest.public_key:
            return f"epi:pubkey:{manifest.public_key[:16]}"
        return "epi:anonymous"

    def _embed_receipt(
        self,
        epi_path: Path,
        manifest: ManifestModel,
        statement_bytes: bytes,
        receipt_bytes: bytes,
        info,
        private_key: Any,
        key_name: str,
    ) -> None:
        """Embed SCITT artifacts into the .epi file and re-sign."""
        import hashlib
        import tempfile
        import zipfile

        scitt_gov = scitt_governance_from_info(info, issuer=self._derive_issuer(manifest))

        # Build updated manifest
        manifest_dict = manifest.model_dump(mode="json")
        manifest_dict.setdefault("governance", {})
        manifest_dict["governance"]["scitt"] = scitt_gov

        updated_manifest = ManifestModel(**manifest_dict)
        signed_manifest = sign_manifest(updated_manifest, private_key, key_name)

        # Write new ZIP with SCITT artifacts
        with tempfile.TemporaryDirectory() as tmpdir:
            extract_dir = Path(tmpdir) / "extract"
            extract_dir.mkdir()

            with zipfile.ZipFile(epi_path, "r") as zf_in:
                zf_in.extractall(extract_dir)

            scitt_dir = extract_dir / "artifacts" / "scitt"
            scitt_dir.mkdir(parents=True, exist_ok=True)
            (scitt_dir / "statement.cbor").write_bytes(statement_bytes)
            (scitt_dir / "receipt.cbor").write_bytes(receipt_bytes)

            (extract_dir / "manifest.json").write_text(
                signed_manifest.model_dump_json(indent=2),
                encoding="utf-8",
            )

            # Determine container format
            with open(epi_path, "rb") as f:
                header = f.read(4)
            container_format = "envelope-v2" if header == b"<!--" else "legacy-zip"

            EPIContainer.pack(
                source_dir=extract_dir,
                manifest=signed_manifest,
                output_path=epi_path,
                container_format=container_format,
                preserve_generated=True,
                generate_analysis=False,
            )
