from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from pathlib import Path
from typing import Any


AUTH_ROLES = {"admin", "reviewer", "auditor"}
PASSWORD_HASH_PREFIX = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 200_000


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def normalize_role(value: Any) -> str:
    role = str(value or "reviewer").strip().lower()
    if role not in AUTH_ROLES:
        allowed = ", ".join(sorted(AUTH_ROLES))
        raise ValueError(f"Unsupported auth role '{value}'. Expected one of: {allowed}")
    return role


def hash_password(password: str, *, salt: str | None = None, iterations: int = PASSWORD_HASH_ITERATIONS) -> str:
    if not str(password or ""):
        raise ValueError("Password cannot be empty.")
    raw_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt.encode("utf-8"), iterations).hex()
    return f"{PASSWORD_HASH_PREFIX}${iterations}${raw_salt}${digest}"


def verify_password(password: str, stored_value: str) -> bool:
    candidate = str(password or "")
    stored = str(stored_value or "")
    if not candidate or not stored:
        return False

    prefix = f"{PASSWORD_HASH_PREFIX}$"
    if not stored.startswith(prefix):
        # Fail-closed: plaintext or unknown hash formats never verify.
        # Migrate with `epi gateway hash-password`.
        return False

    try:
        _, iteration_text, salt, expected = stored.split("$", 3)
        iterations = int(iteration_text)
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", candidate.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return hmac.compare_digest(actual, expected)


def build_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def load_auth_users(users_file: str | Path | None) -> list[dict[str, str]]:
    if not users_file:
        return []

    path = Path(users_file)
    if not path.exists():
        raise FileNotFoundError(f"EPI gateway users file not found: {path}")

    # Warn on overly permissive file modes (POSIX) — users file holds credentials.
    try:
        mode = path.stat().st_mode & 0o777
        if mode & 0o077:
            import warnings

            warnings.warn(
                f"Users file {path} is group/world-readable (mode {oct(mode)}); "
                "chmod 600 to protect password hashes.",
                UserWarning,
                stacklevel=2,
            )
    except OSError:
        pass

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        raw_users = payload.get("users")
    else:
        raw_users = payload

    if not isinstance(raw_users, list):
        raise ValueError("Users file must contain a JSON list or an object with a 'users' list.")

    normalized: list[dict[str, str]] = []
    for index, item in enumerate(raw_users, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid auth user entry at position {index}.")
        username = _clean(item.get("username") or item.get("email"))
        if not username:
            raise ValueError(f"Auth user entry {index} is missing 'username'.")
        role = normalize_role(item.get("role"))
        display_name = _clean(item.get("display_name") or item.get("name")) or username
        password_hash = _clean(item.get("password_hash"))
        password = item.get("password")
        if password_hash:
            if not password_hash.startswith(f"{PASSWORD_HASH_PREFIX}$"):
                raise ValueError(
                    f"Auth user entry '{username}' has a plaintext/unknown password_hash — "
                    "run `epi gateway hash-password` and store the pbkdf2_sha256 value."
                )
            stored_password = password_hash
        elif _clean(password):
            import warnings

            warnings.warn(
                f"Auth user entry '{username}' uses plaintext 'password'; "
                "migrate to 'password_hash' via `epi gateway hash-password`.",
                DeprecationWarning,
                stacklevel=2,
            )
            stored_password = hash_password(str(password))
        else:
            raise ValueError(f"Auth user entry '{username}' must define 'password' or 'password_hash'.")
        normalized.append(
            {
                "username": username.lower(),
                "display_name": display_name,
                "role": role,
                "password_hash": stored_password,
                "source": str(path.resolve()),
            }
        )

    deduped: dict[str, dict[str, str]] = {}
    for item in normalized:
        deduped[item["username"]] = item
    return list(deduped.values())
