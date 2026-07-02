"""Role-based access control for Annex IV multi-signer approvals.

Enforces that signing keys are authorized for specific organizational roles
before they can sign compliance sections.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path


def _role_bindings_path() -> Path:
    """Resolve the role bindings file path."""
    return Path.home() / ".epi" / "role_bindings.json"


def _load_bindings() -> dict:
    """Load role->key bindings from disk."""
    path = _role_bindings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_bindings(bindings: dict) -> None:
    """Save role->key bindings to disk."""
    path = _role_bindings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bindings, indent=2))


def _pubkey_fingerprint(pubkey_hex: str) -> str:
    """Compute the SHA-256 fingerprint of a public key (hex)."""
    pubkey_bytes = bytes.fromhex(pubkey_hex)
    return hashlib.sha256(pubkey_bytes).hexdigest()[:16]


def check_role_authorized(role: str, pubkey_hex: str) -> tuple[bool, str]:
    """Check if a public key is authorized for a given role.

    Returns (authorized, message).
    """
    bindings = _load_bindings()
    fingerprint = _pubkey_fingerprint(pubkey_hex)

    if role not in bindings:
        return True, f"Role '{role}' has no binding restrictions - any key accepted"

    authorized_fingerprints = bindings.get(role, [])

    if not authorized_fingerprints:
        return True, f"Role '{role}' has empty binding list - any key accepted"

    if fingerprint in authorized_fingerprints:
        return True, f"Key fingerprint {fingerprint} authorized for role '{role}'"

    return (
        False,
        f"Key fingerprint {fingerprint} NOT authorized for role '{role}'. "
        f"Authorized: {', '.join(authorized_fingerprints)}"
    )


def bind_role(role: str, pubkey_hex: str) -> str:
    """Bind a public key to a role.

    Returns a status message.
    """
    bindings = _load_bindings()
    fingerprint = _pubkey_fingerprint(pubkey_hex)

    if role not in bindings:
        bindings[role] = []

    if fingerprint not in bindings[role]:
        bindings[role].append(fingerprint)
        _save_bindings(bindings)
        return f"Bound {fingerprint} to role '{role}'"
    else:
        return f"Fingerprint {fingerprint} already bound to role '{role}'"


def unbind_role(role: str, pubkey_hex: str = None) -> str:
    """Unbind a public key from a role (or remove entire role if no key specified).

    Returns a status message.
    """
    bindings = _load_bindings()

    if role not in bindings:
        return f"Role '{role}' has no bindings"

    if pubkey_hex is None:
        del bindings[role]
        _save_bindings(bindings)
        return f"Removed all bindings for role '{role}'"

    fingerprint = _pubkey_fingerprint(pubkey_hex)
    if fingerprint in bindings[role]:
        bindings[role].remove(fingerprint)
        if not bindings[role]:
            del bindings[role]
        _save_bindings(bindings)
        return f"Unbound {fingerprint} from role '{role}'"

    return f"Fingerprint {fingerprint} not bound to role '{role}'"


def list_roles() -> dict:
    """List all role->key bindings.

    Returns dict of {role: [fingerprints]}.
    """
    return _load_bindings()


def verify_all_signers(compliance_summary_path: Path | str = None, strict: bool = False) -> tuple[bool, list[str]]:
    """Verify that all signers in a compliance summary are authorized for their roles.

    Args:
        compliance_summary_path: Path to compliance-summary.json
        strict: If True, fail when signer role has no binding (all signers must have explicit bindings)

    Returns (all_authorized, list_of_messages).
    """
    bindings = _load_bindings()
    messages = []

    if compliance_summary_path is None:
        csf = Path("artifacts/annex_iv/compliance-summary.json")
    else:
        csf = Path(compliance_summary_path)

    if not csf.exists():
        return False, [f"Compliance summary not found: {csf}"]

    data = json.loads(csf.read_text())
    signers = data.get("signers", [])

    if not signers:
        messages.append("No signers found in compliance summary")
        return True, messages

    all_ok = True
    for signer in signers:
        name = signer.get("name", "unknown")
        key_name = signer.get("key_name", "unknown")

        if strict and name not in bindings:
            messages.append(f"FAIL: '{name}' has no role bindings (strict mode)")
            all_ok = False
            continue

        if name in bindings:
            messages.append(f"PASS: '{name}' has role bindings configured")
        else:
            messages.append(f"INFO: '{name}' signing as '{key_name}' - no role restrictions")

    return all_ok, messages


__all__ = [
    "check_role_authorized",
    "bind_role",
    "unbind_role",
    "list_roles",
    "verify_all_signers",
    "_pubkey_fingerprint",
]
