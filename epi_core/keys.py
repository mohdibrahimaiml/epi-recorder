"""
Shared Ed25519 key management used by runtime and CLI code.
"""

from __future__ import annotations

import base64
import os
import re
import stat
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

# One live signer per (keys dir, name): vault sessions are slow to open.
_EXTERNAL_SIGNERS: dict[tuple[str, str], object] = {}


class ExternalKeyRequiredError(RuntimeError):
    """EPI_REQUIRE_EXTERNAL_KEY is set but the key is a file on disk."""


def external_key_required() -> bool:
    val = os.environ.get("EPI_REQUIRE_EXTERNAL_KEY", "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def key_fingerprint(public_key_hex: str, *, grouped: bool = True) -> str:
    """The one fingerprint EPI shows for an Ed25519 public key.

    First 16 hex chars of SHA-256 over the lowercase hex key text (the value
    the witness log records as ``key_fingerprint``). ``grouped`` formats it
    for reading aloud: ``4148 fb59 a148 a6dc``.
    """
    import hashlib

    raw = hashlib.sha256(public_key_hex.strip().lower().encode("utf-8")).hexdigest()[:16]
    return " ".join(raw[i:i + 4] for i in range(0, 16, 4)) if grouped else raw


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


def _dir_has_keys(path: Path) -> bool:
    """True if *path* already holds key material (no side effects)."""
    try:
        if not path.is_dir():
            return False
        return any(path.glob("*.key")) or any(path.glob("*.pub"))
    except Exception:
        return False


def _resolve_default_keys_dir() -> Path:
    """Resolve a writable default keys directory with fallbacks.

    Precedence: ``EPI_KEYS_DIR`` > ``EPI_HOME`` > ``~/.epi/keys`` > ``cwd``.
    ``EPI_HOME`` names the state dir (same convention as telemetry), so keys
    live at ``$EPI_HOME/keys`` (with legacy ``$EPI_HOME/.epi/keys`` honoured).

    Anti-confusion rule: when ``EPI_HOME`` is set but holds no keys while the
    real-home keystore does, we keep using the real-home keystore *and* warn
    loudly instead of silently switching to a fresh empty keystore (which
    would surface as a baffling "key not found").

    The tmpdir fallback is now fail-closed: it will only be used if
    EPI_ALLOW_TMP_KEYS=1 is set, or if the caller explicitly passes a
    keys_dir. Otherwise a PermissionError is raised with a clear message,
    because keys in tmpdir may be lost on reboot and make artifacts
    permanently unverifiable.
    """
    import warnings

    env_dir = os.environ.get("EPI_KEYS_DIR")
    if env_dir:
        candidate = Path(env_dir).expanduser()
        if _is_writable_dir(candidate):
            return candidate
    else:
        epi_home = os.environ.get("EPI_HOME")
        if epi_home:
            base = Path(epi_home).expanduser()
            home_style = base / "keys"
            nested_style = base / ".epi" / "keys"
            for epi_candidate in (home_style, nested_style):
                if _dir_has_keys(epi_candidate):
                    if _is_writable_dir(epi_candidate):
                        return epi_candidate
            real_home_keys = Path.home() / ".epi" / "keys"
            if _dir_has_keys(real_home_keys):
                warnings.warn(
                    f"EPI_HOME is set ({base}) but holds no keys; using existing "
                    f"keystore at {real_home_keys}. Set EPI_KEYS_DIR explicitly "
                    "to choose, or generate keys under EPI_HOME.",
                    UserWarning,
                    stacklevel=2,
                )
                if _is_writable_dir(real_home_keys):
                    return real_home_keys
            # Newcomer path: no keys anywhere — create under EPI_HOME so a
            # user setting only EPI_HOME finds their keys where they look.
            if _is_writable_dir(home_style):
                return home_style
    candidates = [
        Path(env_dir).expanduser() if env_dir else Path.home() / ".epi" / "keys",
        Path.cwd() / ".epi" / "keys",
    ]
    # Check primary candidates first
    for candidate in candidates:
        if _is_writable_dir(candidate):
            return candidate

    # Tmpdir is a last resort and must be explicitly opted in
    tmp_candidate = Path(tempfile.gettempdir()) / "epi" / "keys"
    allow_tmp = os.environ.get("EPI_ALLOW_TMP_KEYS", "").strip().lower() in ("1", "true", "yes", "on")
    if allow_tmp and _is_writable_dir(tmp_candidate):
        return tmp_candidate
    if _is_writable_dir(tmp_candidate):
        raise PermissionError(
            f"Refusing to use tmpdir keys directory {tmp_candidate} without explicit opt-in. "
            "This directory may be cleared on reboot and would make signed artifacts permanently unverifiable. "
            "Set EPI_ALLOW_TMP_KEYS=1 to allow it, or provide --keys-dir / set EPI_KEYS_DIR / ensure ~/.epi/keys is writable."
        )

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
        private_key_path = self._key_file_path(name, ".key")
        public_key_path = self._key_file_path(name, ".pub")

        if not overwrite and (private_key_path.exists() or public_key_path.exists()):
            raise FileExistsError(
                f"Key pair '{name}' already exists. Use --overwrite to replace."
            )
        self._unlink_external(name)

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

    def import_hex_seed(self, name: str = "default", seed_hex: str = "", overwrite: bool = False) -> tuple[Path, Path]:
        """Import an Ed25519 private key from a 64-hex-char seed (32 bytes).

        Used for CI signing (e.g. ``EPI_SIGNING_KEY``): the caller supplies the
        seed from a secret instead of a key file. The key is then stored like
        any other key - ``<keys_dir>/<name>.key`` with 0600 permissions
        (encrypted at rest when ``EPI_KEY_PASSWORD`` is set) - so a CI runner
        holds it only for the life of the job.

        Raises:
            ValueError: If the seed is not exactly 64 hex characters.
            FileExistsError: If keys exist and overwrite=False.
        """
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        seed_hex = (seed_hex or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", seed_hex):
            raise ValueError(
                "Seed must be exactly 64 hex characters (32-byte Ed25519 seed)."
            )
        private_key_path = self._key_file_path(name, ".key")
        public_key_path = self._key_file_path(name, ".pub")
        if not overwrite and (private_key_path.exists() or public_key_path.exists()):
            raise FileExistsError(
                f"Key pair '{name}' already exists. Use overwrite=True to replace."
            )
        self._unlink_external(name)
        private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
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

    # -- keys held in an HSM / cloud KMS ---------------------------------

    def _key_file_path(self, name: str, suffix: str) -> Path:
        if not name or name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
            raise ValueError(f"Invalid key name: {name!r}")
        base = os.path.normpath(os.path.abspath(str(self.keys_dir)))
        candidate = os.path.normpath(os.path.join(base, name + suffix))
        if not candidate.startswith(base + os.sep):
            raise ValueError(f"Invalid key name: {name!r}")
        return Path(candidate)

    def _signer_path(self, name: str) -> Path:
        return self._key_file_path(name, ".signer")

    def _unlink_external(self, name: str) -> None:
        self._signer_path(name).unlink(missing_ok=True)
        _EXTERNAL_SIGNERS.pop((str(self.keys_dir), name), None)

    def external_signer_uri(self, name: str = "default") -> str | None:
        """The vault URI a key name is linked to, or None for a file key."""
        try:
            path = self._signer_path(name)
        except ValueError:
            return None
        if not path.is_file():
            return None
        import json

        return str(json.loads(path.read_text(encoding="utf-8"))["uri"])

    def link_external_key(
        self, name: str, uri: str, *, overwrite: bool = False, **backend_kwargs
    ) -> tuple[Path, str]:
        """Point a key name at an Ed25519 key held in an HSM or cloud KMS.

        Fetches the public key from the vault and writes ``<name>.pub`` plus
        ``<name>.signer`` (the URI and the pinned public key; nothing
        secret). Refuses while a ``<name>.key`` file exists: deleting a
        private key is left to the owner. Returns (signer path, public hex).
        """
        import json

        from epi_core.signers import load_signer

        private_key_path = self._key_file_path(name, ".key")
        public_key_path = self._key_file_path(name, ".pub")
        signer_path = self._signer_path(name)
        if private_key_path.exists():
            raise FileExistsError(
                f"Key '{name}' is a key file ({private_key_path}). Move or delete it "
                "first, or link the vault key under another name."
            )
        if not overwrite and (signer_path.exists() or public_key_path.exists()):
            raise FileExistsError(
                f"Key '{name}' already exists. Use --overwrite to re-link it."
            )
        signer = load_signer(uri, **backend_kwargs)
        public_key_hex = signer.public_key_hex()
        # Prove the vault can sign with it before anything is written.
        signer.sign(b"epi-recorder key link check")

        public_key_path.write_bytes(
            signer.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        if os.name != "nt":
            os.chmod(public_key_path, 0o644)
        signer_path.write_text(
            json.dumps(
                {"uri": signer.uri, "backend": signer.backend, "public_key": public_key_hex},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _EXTERNAL_SIGNERS[(str(self.keys_dir), name)] = signer
        return signer_path, public_key_hex

    def _load_external_signer(self, name: str):
        import json

        from epi_core.signers import ExternalSignerError, load_signer

        cache_key = (str(self.keys_dir), name)
        cached = _EXTERNAL_SIGNERS.get(cache_key)
        if cached is not None:
            return cached
        record = json.loads(self._signer_path(name).read_text(encoding="utf-8"))
        pinned = str(record.get("public_key") or "").lower()
        signer = load_signer(str(record["uri"]))
        live = signer.public_key_hex()
        pub_exists = self._key_file_path(name, ".pub").exists()
        file_pub = self.load_public_key(name).hex() if pub_exists else ""
        # The vault must still hold the key that was linked: a swapped key
        # would sign records nobody pinned.
        if live != pinned or (file_pub and file_pub != pinned):
            raise ExternalSignerError(
                f"Key '{name}': the vault now returns public key {live[:16]}..., but "
                f"{pinned[:16]}... was linked. Refusing to sign. Re-link with "
                f"`epi keys link --name {name} --uri ... --overwrite` if the change is intended."
            )
        _EXTERNAL_SIGNERS[cache_key] = signer
        return signer

    def load_private_key(self, name: str = "default") -> Ed25519PrivateKey:
        """Load a signing key: the vault signer when linked, else the key file.

        A vault signer has the same ``sign()`` / ``public_key()`` surface as
        ``Ed25519PrivateKey`` but cannot be exported.
        """
        if self._signer_path(name).is_file():
            return self._load_external_signer(name)  # type: ignore[return-value]
        key_path = self._key_file_path(name, ".key")
        if external_key_required():
            raise ExternalKeyRequiredError(
                f"EPI_REQUIRE_EXTERNAL_KEY is set, so key '{name}' must be held in an "
                f"HSM or KMS. Link one with: epi keys link --name {name} --uri <vault-uri>"
            )
        if not key_path.exists():
            raise FileNotFoundError(
                f"Private key '{name}' not found. Generate with: epi keys generate --name {name}"
            )
        key_password = os.environ.get("EPI_KEY_PASSWORD")
        return serialization.load_pem_private_key(key_path.read_bytes(), password=key_password.encode() if key_password else None)

    def load_public_key(self, name: str = "default") -> bytes:
        """Load a public key from disk."""
        key_path = self._key_file_path(name, ".pub")
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
            signer_uri = None
            try:
                signer_uri = self.external_signer_uri(key_name)
            except Exception:
                pass
            keys.append(
                {
                    "name": key_name,
                    "has_private": private_exists or bool(signer_uri),
                    "has_public": True,
                    "public_path": str(pub_file),
                    "private_path": (
                        signer_uri
                        if signer_uri
                        else str(self.keys_dir / f"{key_name}.key") if private_exists else "N/A"
                    ),
                    "external": bool(signer_uri),
                }
            )
        return keys

    def export_public_key(self, name: str = "default") -> str:
        """Export public key as base64 string for sharing."""
        public_key_bytes = self.load_public_key(name)
        return base64.b64encode(public_key_bytes).decode("utf-8")

    def has_key(self, name: str = "default") -> bool:
        """Check if a key pair exists. Invalid names never exist."""
        try:
            private_path = self._key_file_path(name, ".key")
            public_path = self._key_file_path(name, ".pub")
            signer_path = self._signer_path(name)
        except ValueError:
            return False
        return (private_path.exists() or signer_path.exists()) and public_path.exists()

    def has_default_key(self) -> bool:
        """Check if default key pair exists (a key file or a linked vault key)."""
        return (self.keys_dir / "default.key").exists() or self._signer_path("default").exists()

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

        # What `epi keys export` prints by default: base64 of the 32 raw bytes.
        if len(text) == 44 and text.endswith("="):
            try:
                raw = base64.b64decode(text, validate=True)
                if len(raw) == 32:
                    return raw
            except Exception:
                pass

        # A did.json the vendor sent (offline pinning without resolving did:web).
        if text.startswith("{"):
            import json as _json

            try:
                doc = _json.loads(text)
            except ValueError:
                doc = None
            if isinstance(doc, dict) and "verificationMethod" in doc:
                from epi_core.did_web import extract_ed25519_keys

                found = extract_ed25519_keys(doc)
                if len(found) == 1:
                    return bytes.fromhex(found[0])
                if not found:
                    raise ValueError(f"{path} is a DID document with no Ed25519 key")
                raise ValueError(
                    f"{path} lists {len(found)} Ed25519 keys; pin each one from "
                    "`epi keys trust --from-did` or a single-key .pub file"
                )

        # PEM public key
        try:
            return self._load_public_key_raw_bytes_from_file(path)
        except Exception as pem_exc:
            raise ValueError(
                f"Could not load Ed25519 public key from {path}. "
                "Expected PEM, 64-char hex .pub, base64 key (from `epi keys export`), "
                "did.json, or signed .epi. "
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

    def unrevoke_key(self, name: str, *, trusted_keys_dir: Path) -> list[Path]:
        """Undo ``revoke_key``: remove every revocation marker for that key.

        Revocation applies to the key, not the pin name, so markers written
        under any name for the same key are removed. Returns removed paths.
        """
        trusted_keys_dir = Path(trusted_keys_dir)
        hex_key = None
        for candidate in (
            trusted_keys_dir / f"{name}.revoked",
            trusted_keys_dir / f"{name}.pub",
        ):
            if candidate.exists():
                hex_key = candidate.read_text(encoding="utf-8").strip().lower()
                break
        if hex_key is None and (self.keys_dir / f"{name}.pub").exists():
            hex_key = self._load_public_key_raw_bytes(name).hex()
        if hex_key is None:
            raise FileNotFoundError(f"No trusted or revoked key named '{name}'.")
        removed: list[Path] = []
        for marker in trusted_keys_dir.glob("*.revoked"):
            try:
                if marker.read_text(encoding="utf-8").strip().lower() == hex_key:
                    marker.unlink()
                    removed.append(marker)
            except OSError:
                continue
        return removed


def revoked_key_hexes(trusted_keys_dir: Path) -> set[str]:
    """Hex keys with a revocation marker (revocation is per key, not per name)."""
    out: set[str] = set()
    trusted_keys_dir = Path(trusted_keys_dir)
    if trusted_keys_dir.exists():
        for marker in trusted_keys_dir.glob("*.revoked"):
            try:
                out.add(marker.read_text(encoding="utf-8").strip().lower())
            except OSError:
                continue
    return out


def export_trust_bundle(
    key_manager: KeyManager,
    out_path: Path,
    *,
    names: list[str] | None = None,
    trusted_keys_dir: Path | None = None,
    pubs: list[tuple[str, str]] | None = None,
) -> Path:
    """
    Export public keys only into a zip auditors can import.

    Includes:
    - README.txt with verify instructions
    - keys/<name>.pub as hex raw Ed25519 (TrustRegistry format)
    - Never includes private keys

    Args:
        pubs: Optional explicit (name, hex) public keys to export instead of
            looking names up in the key manager's signing directory. Used when
            the keys belong to someone else (e.g. an org bundle built from a
            customer-supplied public key) and must not enter the local
            signing namespace.
    """
    import zipfile
    from datetime import datetime, timezone

    out_path = Path(out_path)
    if out_path.suffix.lower() != ".zip":
        out_path = out_path.with_suffix(".zip")

    pub_entries: list[tuple[str, bytes]] = []
    if pubs is not None:
        for entry_name, entry_hex in pubs:
            try:
                raw = bytes.fromhex(str(entry_hex).strip())
            except ValueError as exc:
                raise ValueError(
                    f"Invalid key material for '{entry_name}': not hex"
                ) from exc
            if len(raw) != 32:
                raise ValueError(
                    f"Expected 32-byte Ed25519 key for '{entry_name}', got {len(raw)}"
                )
            pub_entries.append((str(entry_name), raw))
    else:
        if names:
            key_names = list(names)
        else:
            key_names = [k["name"] for k in key_manager.list_keys() if k.get("has_public")]

        if not key_names:
            raise FileNotFoundError(
                "No public keys to export. Generate one with: epi keys generate"
            )

        for kn in key_names:
            pub_path = key_manager.keys_dir / f"{kn}.pub"
            if not pub_path.exists():
                raise FileNotFoundError(f"Public key not found for '{kn}': {pub_path}")
            raw = key_manager._load_public_key_raw_bytes(kn)
            pub_entries.append((kn, raw))

    if not pub_entries:
        raise FileNotFoundError(
            "No public keys to export. Generate one with: epi keys generate"
        )
    pubs = [(n, r.hex().encode("utf-8")) for n, r in pub_entries]

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
