"""
Shared Ed25519 key management used by runtime and CLI code.
"""

from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


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
    candidates = [
        Path.home() / ".epi" / "keys",
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

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        private_key_path.write_bytes(private_pem)
        if os.name != "nt":
            os.chmod(private_key_path, 0o600)
        else:
            import stat

            os.chmod(private_key_path, stat.S_IREAD | stat.S_IWRITE)

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
        return serialization.load_pem_private_key(key_path.read_bytes(), password=None)

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


__all__ = ["KeyManager"]
