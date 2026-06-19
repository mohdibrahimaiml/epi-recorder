"""Lightweight, privacy-safe signals derived from the local environment.

These are computed from local git config and sent only when telemetry is
explicitly enabled. Full emails, repo names, hostnames, and paths are never
sent.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


_SSH_GIT_URL_RE = re.compile(r"git@github\.com:([^/]+)/.*")
_HTTPS_GIT_URL_RE = re.compile(r"https?://github\.com/([^/]+)/.*")
_EMAIL_RE = re.compile(r"[\w.+-]+@([\w.-]+\.[\w.-]+)")


_signals: dict[str, str] | None = None


def _state_dir() -> Path:
    override = os.getenv("EPI_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".epi"


def _run_git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
        if result.returncode != 0:
            return None
        text = result.stdout.strip()
        return text if text else None
    except Exception:
        return None


def _extract_domain(email: str) -> str | None:
    email = email.strip().lower()
    match = _EMAIL_RE.search(email)
    if match:
        domain = match.group(1).rstrip(" >);,\"'").rstrip(".")
        return domain
    if "@" in email:
        domain = email.split("@", 1)[-1].strip().split()[0]
        domain = domain.rstrip(" >);,\"'").rstrip(".")
        return domain
    return None


def _extract_github_org(remote_url: str) -> str | None:
    remote_url = remote_url.strip()
    for pattern in (_SSH_GIT_URL_RE, _HTTPS_GIT_URL_RE):
        match = pattern.match(remote_url)
        if match:
            org = match.group(1).lower()
            # Ignore individual user namespaces that look like personal accounts.
            if org in {"personal", "private"}:
                return None
            return org
    return None


def _collect_signals() -> dict[str, str]:
    signals: dict[str, str] = {}

    email = _run_git("config", "user.email")
    if email:
        domain = _extract_domain(email)
        if domain:
            signals["email_domain"] = domain

    remote = _run_git("remote", "get-url", "origin")
    if not remote:
        remotes = _run_git("remote", "-v")
        if remotes:
            for line in remotes.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "origin":
                    remote = parts[1]
                    break
    if remote:
        org = _extract_github_org(remote)
        if org:
            signals["github_org"] = org

    return signals


def get_identity_signals() -> dict[str, str]:
    """Return cached identity signals. Safe to call repeatedly."""
    global _signals
    if _signals is None:
        _signals = _collect_signals()
    return dict(_signals)


def get_email_domain() -> str | None:
    return get_identity_signals().get("email_domain")


def get_github_org() -> str | None:
    return get_identity_signals().get("github_org")


def _get_auth_identity() -> dict[str, str]:
    """Read locally saved EPI Cloud identity, if any."""
    try:
        path = _state_dir() / "auth.json"
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        result: dict[str, str] = {}
        if data.get("user_id"):
            result["user_id"] = str(data["user_id"])
        if data.get("org"):
            result["org_id"] = str(data["org"])
        return result
    except Exception:
        return {}


def attach_identity_signals(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Merge identity signals into telemetry metadata without overwriting."""
    metadata = dict(metadata or {})
    for key, value in get_identity_signals().items():
        if key not in metadata and value:
            metadata[key] = value
    for key, value in _get_auth_identity().items():
        if key not in metadata and value:
            metadata[key] = value
    return metadata
