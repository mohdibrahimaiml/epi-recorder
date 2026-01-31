"""
EPI CLI Keys - Ed25519 key pair management for cryptographic signing.

Provides secure key generation, storage, and management following best practices.
"""

import base64
import os
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rich.console import Console
from rich.table import Table

console = Console()


class KeyManager:
    """
    Manages Ed25519 key pairs for EPI signing.
    
    Keys are stored in ~/.epi/keys/ with secure permissions:
    - Private keys: 0600 (owner read/write only)
    - Public keys: 0644 (owner write, all read)
    """
    
    def __init__(self, keys_dir: Optional[Path] = None):
        """
        Initialize key manager.
        
        Args:
            keys_dir: Optional custom keys directory (default: ~/.epi/keys/)
        """
        if keys_dir is None:
            self.keys_dir = Path.home() / ".epi" / "keys"
        else:
            self.keys_dir = keys_dir
        
        # Ensure keys directory exists with secure permissions
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        
        # On Unix-like systems, set directory permissions to 0700
        if os.name != 'nt':  # Not Windows
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
        
        # Check for existing keys
        if not overwrite:
            if private_key_path.exists() or public_key_path.exists():
                raise FileExistsError(
                    f"Key pair '{name}' already exists. Use --overwrite to replace."
                )
        
        # Generate Ed25519 key pair
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        
        # Serialize private key (PEM format, no encryption for simplicity in MVP)
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        # Serialize public key (PEM format)
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        # Write private key with secure permissions
        private_key_path.write_bytes(private_pem)
        if os.name != 'nt':  # Unix-like systems
            os.chmod(private_key_path, 0o600)  # Owner read/write only
        else:  # Windows
            # Set file to be readable only by owner
            import stat
            os.chmod(private_key_path, stat.S_IREAD | stat.S_IWRITE)
        
        # Write public key
        public_key_path.write_bytes(public_pem)
        if os.name != 'nt':
            os.chmod(public_key_path, 0o644)  # Owner write, all read
        
        return private_key_path, public_key_path
    
    def load_private_key(self, name: str = "default") -> Ed25519PrivateKey:
        """
        Load a private key from disk.
        
        Args:
            name: Key pair name
            
        Returns:
            Ed25519PrivateKey: Loaded private key
            
        Raises:
            FileNotFoundError: If key doesn't exist
        """
        key_path = self.keys_dir / f"{name}.key"
        
        if not key_path.exists():
            raise FileNotFoundError(
                f"Private key '{name}' not found. Generate with: epi keys generate --name {name}"
            )
        
        key_data = key_path.read_bytes()
        return serialization.load_pem_private_key(key_data, password=None)
    
    def load_public_key(self, name: str = "default") -> bytes:
        """
        Load a public key from disk.
        
        Args:
            name: Key pair name
            
        Returns:
            bytes: Public key bytes (raw 32 bytes for Ed25519)
            
        Raises:
            FileNotFoundError: If key doesn't exist
        """
        key_path = self.keys_dir / f"{name}.pub"
        
        if not key_path.exists():
            raise FileNotFoundError(
                f"Public key '{name}' not found. Generate with: epi keys generate --name {name}"
            )
        
        pem_data = key_path.read_bytes()
        public_key = serialization.load_pem_public_key(pem_data)
        
        # Return raw 32-byte public key
        return public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    
    def list_keys(self) -> list[dict[str, str]]:
        """
        List all available key pairs.
        
        Returns:
            list: List of dicts with key information
        """
        keys = []
        
        # Find all .pub files
        for pub_file in self.keys_dir.glob("*.pub"):
            key_name = pub_file.stem
            private_exists = (self.keys_dir / f"{key_name}.key").exists()
            
            keys.append({
                "name": key_name,
                "has_private": private_exists,
                "has_public": True,
                "public_path": str(pub_file),
                "private_path": str(self.keys_dir / f"{key_name}.key") if private_exists else "N/A"
            })
        
        return keys
    
    def export_public_key(self, name: str = "default") -> str:
        """
        Export public key as base64 string for sharing.
        
        Args:
            name: Key pair name
            
        Returns:
            str: Base64-encoded public key
        """
        public_key_bytes = self.load_public_key(name)
        return base64.b64encode(public_key_bytes).decode("utf-8")
    
    def has_key(self, name: str = "default") -> bool:
        """
        Check if a key pair exists.
        
        Args:
            name: Key pair name
            
        Returns:
            bool: True if key pair exists
        """
        private_path = self.keys_dir / f"{name}.key"
        public_path = self.keys_dir / f"{name}.pub"
        return private_path.exists() and public_path.exists()
    
    def has_default_key(self) -> bool:
        """
        Check if default key pair exists.
        
        Returns:
            bool: True if default key exists
        """
        return (self.keys_dir / "default.key").exists()


def generate_default_keypair_if_missing(console_output: bool = True) -> bool:
    """
    Generate default key pair if it doesn't exist (frictionless first run).
    
    Args:
        console_output: Whether to print console messages
        
    Returns:
        bool: True if key was generated, False if already exists
    """
    key_manager = KeyManager()
    
    if key_manager.has_default_key():
        return False
    
    # Generate default key pair
    private_path, public_path = key_manager.generate_keypair("default")
    
    if console_output:
        console.print("\n[bold green]Welcome to EPI![/bold green]")
        console.print("\n[dim]Generated default Ed25519 key pair for signing:[/dim]")
        console.print(f"  [cyan]Private:[/cyan] {private_path}")
        console.print(f"  [cyan]Public:[/cyan]  {public_path}")
        console.print("\n[dim]Your .epi files will be automatically signed for authenticity.[/dim]\n")
    
    return True


def print_keys_table(keys: list[dict[str, str]]) -> None:
    """
    Print a formatted table of keys using Rich.
    
    Args:
        keys: List of key information dicts
    """
    if not keys:
        console.print("[yellow]No keys found. Generate with: epi keys generate[/yellow]")
        return
    
    table = Table(title="EPI Key Pairs", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Private Key", style="green")
    table.add_column("Public Key", style="blue")
    
    for key in keys:
        private_status = "[Y]" if key["has_private"] else "[N]"
        public_status = "[Y]" if key["has_public"] else "[N]"
        
        table.add_row(
            key["name"],
            f"{private_status} {key['private_path']}",
            f"{public_status} {key['public_path']}"
        )
    
    console.print(table)


