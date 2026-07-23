"""
Shared Ed25519 key management used by runtime and CLI code.
"""

from __future__ import annotations

import base64
import os
import stat
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def _is_writable_dir(path: Path) -> bool:
    """Return True if directory is creatable and writable."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".epi_key_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _resolve_default_keys_dir() -> Path:
    """Resolve a writable default keys directory with fallbacks."""
    env_dir = os.environ.get("EPI_KEYS_DIR")
    candidates = [
        Path(env_dir) if env_dir else Path.home() / ".epi" / "keys",
        Path.cwd() / ".epi" / "keys",
        Path(tempfile.gettempdir()) / "epi" / "keys",
    ]

    for candidate in candidates:
        if _is_writable_dir(candidate):
            return candidate

    raise PermissionError(
        "Unable to create a writable keys directory. "
        "Provide --keys-dir or set a writable home/temp path."
    )


class KeyManager:
    """
    Manages Ed25519 key pairs for EPI signing.

    Keys are stored in ~/.epi/keys/ with secure permissions:
    - Private keys: 0600 (owner read/write only)
    - Public keys: 0644 (owner write, all read)
    """

    def __init__(self, keys_dir: Path | None = None):
        """
        Initialize key manager.

        Args:
            keys_dir: Optional custom keys directory (default: ~/.epi/keys/)
        """
        if keys_dir is None:
            self.keys_dir = _resolve_default_keys_dir()
        else:
            self.keys_dir = keys_dir

        self.keys_dir.mkdir(parents=True, exist_ok=True)

        if os.name != "nt":
            os.chmod(self.keys_dir, 0o700)

    def generate_keypair(self, name: str = "default", overwrite: bool = False) -> tuple[Path, Path]:
        """
        Generate an Ed25519 key pair.

        Args:
            name: Key pair name
            overwrite: Whether to overwrite existing keys

        Returns:
            tuple: (private_key_path, public_key_path)

        Raises:
            FileExistsError: If keys exist and overwrite=False
        """
        private_key_path = self.keys_dir / f"{name}.key"
        public_key_path = self.keys_dir / f"{name}.pub"

        if not overwrite and (private_key_path.exists() or public_key_path.exists()):
            raise FileExistsError(
                f"Key pair '{name}' already exists. Use --overwrite to replace."
            )

        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        key_password = os.environ.get("EPI_KEY_PASSWORD")
        encryption = serialization.BestAvailableEncryption(key_password.encode()) if key_password else serialization.NoEncryption()
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # Write to temp file then atomically rename to avoid TOCTOU race
        private_tmp = private_key_path.with_suffix(private_key_path.suffix + ".tmp")
        private_tmp.write_bytes(private_pem)
        if os.name != "nt":
            os.chmod(private_tmp, 0o600)
        else:
            os.chmod(private_tmp, stat.S_IREAD | stat.S_IWRITE)
        private_tmp.replace(private_key_path)

        public_key_path.write_bytes(public_pem)
        if os.name != "nt":
            os.chmod(public_key_path, 0o644)

        return private_key_path, public_key_path

    def load_private_key(self, name: str = "default") -> Ed25519PrivateKey:
        """Load a private key from disk."""
        key_path = self.keys_dir / f"{name}.key"
        if not key_path.exists():
            raise FileNotFoundError(
                f"Private key '{name}' not found. Generate with: epi keys generate --name {name}"
            )
        key_password = os.environ.get("EPI_KEY_PASSWORD")
        return serialization.load_pem_private_key(key_path.read_bytes(), password=key_password.encode() if key_password else None)

    def load_public_key(self, name: str = "default") -> bytes:
        """Load a public key from disk."""
        key_path = self.keys_dir / f"{name}.pub"
        if not key_path.exists():
            raise FileNotFoundError(
                f"Public key '{name}' not found. Generate with: epi keys generate --name {name}"
            )

        pem_data = key_path.read_bytes()
        public_key = serialization.load_pem_public_key(pem_data)
        return public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def list_keys(self) -> list[dict[str, str]]:
        """List all available key pairs."""
        keys = []
        for pub_file in self.keys_dir.glob("*.pub"):
            key_name = pub_file.stem
            private_exists = (self.keys_dir / f"{key_name}.key").exists()
            keys.append(
                {
                    "name": key_name,
                    "has_private": private_exists,
                    "has_public": True,
                    "public_path": str(pub_file),
                    "private_path": str(self.keys_dir / f"{key_name}.key") if private_exists else "N/A",
                }
            )
        return keys

    def export_public_key(self, name: str = "default") -> str:
        """Export public key as base64 string for sharing."""
        public_key_bytes = self.load_public_key(name)
        return base64.b64encode(public_key_bytes).decode("utf-8")

    def has_key(self, name: str = "default") -> bool:
        """Check if a key pair exists."""
        private_path = self.keys_dir / f"{name}.key"
        public_path = self.keys_dir / f"{name}.pub"
        return private_path.exists() and public_path.exists()

    def has_default_key(self) -> bool:
        """Check if default key pair exists."""
        return (self.keys_dir / "default.key").exists()

    def _load_public_key_raw_bytes(self, name: str) -> bytes:
        """Load the raw 32-byte Ed25519 public key for a key name."""
        return self.load_public_key(name)

    def _load_public_key_raw_bytes_from_file(self, path: Path) -> bytes:
        """Load raw 32-byte Ed25519 public key from a PEM file."""
        public_key = serialization.load_pem_public_key(path.read_bytes())
        if not isinstance(public_key, Ed25519PublicKey):
            raise ValueError(f"Public key in {path} is not an Ed25519 key")
        return public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def trust_key(
        self,
        source: str | Path,
        *,
        trusted_keys_dir: Path,
        trusted_name: str | None = None,
        overwrite: bool = False,
    ) -> Path:
        """
        Copy/convert a public key into the local trust registry.

        Args:
            source: Either a key name in the managed keys directory, a path
                to a PEM-encoded public key file, a path to a 64-hex-char
                raw Ed25519 ``.pub`` file, or a path to a signed ``.epi``
                artifact (uses ``manifest.public_key``).
            trusted_keys_dir: Directory where trusted public keys are stored.
            trusted_name: Optional name for the trusted key entry. Defaults to
                the key name or the stem of the provided file path.
            overwrite: Replace an existing trusted key file with the same name.

        Returns:
            Path to the written trusted key file.

        Raises:
            FileExistsError: If the trusted key already exists and overwrite=False.
            FileNotFoundError: If the source key name or path cannot be found.
            ValueError: If the source file does not contain an Ed25519 public key.
        """
        trusted_keys_dir = Path(trusted_keys_dir)
        trusted_keys_dir.mkdir(parents=True, exist_ok=True)

        source_path = Path(source)
        if source_path.exists():
            raw_bytes = self._load_public_key_raw_bytes_from_any(source_path)
            name = trusted_name or source_path.stem
        else:
            raw_bytes = self._load_public_key_raw_bytes(str(source))
            name = trusted_name or str(source)

        if len(raw_bytes) != 32:
            raise ValueError(
                f"Ed25519 public key must be 32 raw bytes (got {len(raw_bytes)})"
            )

        target = trusted_keys_dir / f"{name}.pub"
        if target.exists() and not overwrite:
            raise FileExistsError(
                f"Trusted key '{name}' already exists. Use --overwrite to replace."
            )

        target.write_text(raw_bytes.hex(), encoding="utf-8")
        return target

    def _load_public_key_raw_bytes_from_any(self, path: Path) -> bytes:
        """
        Load 32-byte Ed25519 public key from PEM, hex .pub, or signed .epi.

        This is the implementation behind ``trust_key`` when ``source`` is a path.
        """
        path = Path(path)
        suffix = path.suffix.lower()

        # Signed EPI artifact: pin manifest.public_key (hex raw Ed25519)
        if suffix == ".epi":
            from epi_core.container import EPIContainer

            manifest = EPIContainer.read_manifest(path)
            pub_hex = getattr(manifest, "public_key", None)
            if not pub_hex or not isinstance(pub_hex, str):
                raise ValueError(
                    f"No public_key in manifest of {path}. "
                    "File is unsigned or not a valid EPI artifact."
                )
            pub_hex = pub_hex.strip().lower()
            if len(pub_hex) != 64:
                raise ValueError(
                    f"manifest.public_key in {path} is not 64 hex chars "
                    f"(got length {len(pub_hex)})"
                )
            try:
                return bytes.fromhex(pub_hex)
            except ValueError as exc:
                raise ValueError(
                    f"manifest.public_key in {path} is not valid hex"
                ) from exc

        # Trust-registry style: raw hex in a .pub text file
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if len(text) == 64 and all(c in "0123456789abcdefABCDEF" for c in text):
            return bytes.fromhex(text)

        # PEM public key
        try:
            return self._load_public_key_raw_bytes_from_file(path)
        except Exception as pem_exc:
            raise ValueError(
                f"Could not load Ed25519 public key from {path}. "
                "Expected PEM, 64-char hex .pub, or signed .epi. "
                f"Detail: {pem_exc}"
            ) from pem_exc

    def revoke_key(self, name: str, *, trusted_keys_dir: Path) -> Path:
        """
        Create a revocation marker for a public key.

        The marker is written as ``<trusted_keys_dir>/<name>.revoked`` and
        contains the hex-encoded public key, matching the format expected by
        ``TrustRegistry``.

        Args:
            name: Name of the trusted or signing key to revoke.
            trusted_keys_dir: Directory where trusted public keys are stored.

        Returns:
            Path to the written revocation marker.

        Raises:
            FileNotFoundError: If no public key can be located for ``name``.
        """
        trusted_keys_dir = Path(trusted_keys_dir)
        trusted_keys_dir.mkdir(parents=True, exist_ok=True)

        trusted_pub = trusted_keys_dir / f"{name}.pub"
        signing_pub = self.keys_dir / f"{name}.pub"

        if trusted_pub.exists():
            hex_key = trusted_pub.read_text(encoding="utf-8").strip()
        elif signing_pub.exists():
            hex_key = self._load_public_key_raw_bytes(name).hex()
        else:
            raise FileNotFoundError(
                f"No public key found for '{name}'. Generate or trust the key first."
            )

        revoked_path = trusted_keys_dir / f"{name}.revoked"
        revoked_path.write_text(hex_key, encoding="utf-8")
        return revoked_path


def export_trust_bundle(
    key_manager: KeyManager,
    out_path: Path,
    *,
    names: list[str] | None = None,
    trusted_keys_dir: Path | None = None,
) -> Path:
    """
    Export public keys only into a zip auditors can import.

    Includes:
    - README.txt with verify instructions
    - keys/<name>.pub as hex raw Ed25519 (TrustRegistry format)
    - Never includes private keys
    """
    import zipfile
    from datetime import datetime, timezone

    out_path = Path(out_path)
    if out_path.suffix.lower() != ".zip":
        out_path = out_path.with_suffix(".zip")

    if names:
        key_names = list(names)
    else:
        key_names = [k["name"] for k in key_manager.list_keys() if k.get("has_public")]

    if not key_names:
        raise FileNotFoundError(
            "No public keys to export. Generate one with: epi keys generate"
        )

    pubs: list[tuple[str, bytes]] = []
    for kn in key_names:
        pub_path = key_manager.keys_dir / f"{kn}.pub"
        if not pub_path.exists():
            raise FileNotFoundError(f"Public key not found for '{kn}': {pub_path}")
        raw = key_manager._load_public_key_raw_bytes(kn)
        pubs.append((kn, raw.hex().encode("utf-8")))

    readme = f"""EPI Trust Bundle
================
Generated: {datetime.now(timezone.utc).isoformat()}
Keys: {", ".join(n for n, _ in pubs)}

This archive contains PUBLIC keys only (safe to share with auditors).
It does NOT contain private keys.

On a verifier machine:
  epi keys bundle-import {out_path.name}
  epi verify artifact.epi --policy strict

Enterprise docs:
  docs/ENTERPRISE-TRUST-PROFILE.md
  docs/ENTERPRISE-TRUST-BUNDLE.md
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme)
        zf.writestr(
            "manifest.json",
            __import__("json").dumps(
                {
                    "format": "epi-trust-bundle-v1",
                    "keys": [n for n, _ in pubs],
                },
                indent=2,
            ),
        )
        for kn, hex_bytes in pubs:
            zf.writestr(f"keys/{kn}.pub", hex_bytes.decode("utf-8") + "\n")

    return out_path


def import_trust_bundle(
    bundle_path: Path,
    *,
    trusted_keys_dir: Path,
    overwrite: bool = False,
) -> list[Path]:
    """
    Import public keys from an epi-trust-bundle zip into trusted_keys_dir.
    """
    import zipfile

    bundle_path = Path(bundle_path)
    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle not found: {bundle_path}")

    trusted_keys_dir = Path(trusted_keys_dir)
    trusted_keys_dir.mkdir(parents=True, exist_ok=True)
    imported: list[Path] = []

    with zipfile.ZipFile(bundle_path, "r") as zf:
        names = [n for n in zf.namelist() if n.startswith("keys/") and n.endswith(".pub")]
        if not names:
            raise ValueError("No keys/*.pub entries found in trust bundle")
        for member in names:
            stem = Path(member).stem
            target = trusted_keys_dir / f"{stem}.pub"
            if target.exists() and not overwrite:
                raise FileExistsError(
                    f"Trusted key '{stem}' already exists. Use --overwrite to replace."
                )
            data = zf.read(member).decode("utf-8").strip()
            # Accept hex raw or PEM
            if "BEGIN" in data:
                # write via temp trust_key path
                import tempfile

                with tempfile.NamedTemporaryFile(
                    "w", suffix=".pub", delete=False, encoding="utf-8"
                ) as tmp:
                    tmp.write(data)
                    tmp_path = Path(tmp.name)
                try:
                    km = KeyManager()
                    written = km.trust_key(
                        tmp_path,
                        trusted_keys_dir=trusted_keys_dir,
                        trusted_name=stem,
                        overwrite=overwrite,
                    )
                    imported.append(written)
                finally:
                    tmp_path.unlink(missing_ok=True)
            else:
                # hex raw
                try:
                    raw = bytes.fromhex(data)
                except ValueError as e:
                    raise ValueError(f"Invalid key material in {member}: {e}") from e
                if len(raw) != 32:
                    raise ValueError(f"Expected 32-byte Ed25519 key in {member}, got {len(raw)}")
                target.write_text(data + "\n", encoding="utf-8")
                imported.append(target)

    return imported


__all__ = ["KeyManager", "export_trust_bundle", "import_trust_bundle"]
