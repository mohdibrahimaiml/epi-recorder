"""MCP tool implementations (transport-independent).

Pure functions returning JSON-serializable dicts, registered by both the
stdio server (``server.py``) and the Streamable HTTP server (``http.py``.

File delivery: ``epi_seal_record`` returns the artifact bytes as base64
plus filename and SHA-256. A server-side filesystem path is meaningless
to a remote host, so the bytes — not the path — are the primary result.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from epi_mcp.records import SCOPE_NOTE, export_summary, seal_record, verify_artifact

NOT_CAPTURED = [
    "content the caller did not supply",
    "system state not visible to the caller",
    "unobserved external actions",
]

REDACTED_MARKER = "[REDACTED]"

# Step kinds counted as tool activity in seal summaries.
TOOL_KINDS = {"tool.call", "tool.response"}

# Step kinds counted as artifacts in seal summaries.
ARTIFACT_KINDS = {"artifact.attached", "artifact.produced"}

# Declared omissions are not redactions: they say what was left out, in words.
OMISSION_KIND = "redaction.omitted"


def _count_occurrences(value: Any, marker: str) -> int:
    if isinstance(value, str):
        return value.count(marker)
    if isinstance(value, dict):
        return sum(_count_occurrences(v, marker) for v in value.values())
    if isinstance(value, (list, tuple)):
        return sum(_count_occurrences(v, marker) for v in value)
    return 0

# In-process registry of sealed artifacts, so the HTTP layer can serve
# them back as downloads. Maps artifact_id -> absolute .epi path.
ARTIFACTS: dict[str, str] = {}

# Unguessable, expiring capability tokens for human download links. A person
# clicking a link in a chat has no Bearer token, and the artifact can hold a
# whole conversation, so the link carries its own secret instead of a
# guessable id.
DOWNLOAD_TTL_SECONDS = 24 * 3600
_DOWNLOAD_TOKENS: dict[str, tuple[str, float]] = {}


# artifact_id -> expiry (epoch seconds) for files the sealer wrote into its own
# temp directory. Those files can hold a whole conversation, so they are
# deleted when the link expires instead of living on the host forever.
_ARTIFACT_EXPIRY: dict[str, float] = {}
# artifact_id -> (owner hash, size in bytes) for retention-managed files, so one
# caller cannot fill the host's disk.
_ARTIFACT_OWNER: dict[str, tuple[str, int]] = {}
MAX_LIVE_ARTIFACTS_PER_CALLER = 50
MAX_LIVE_BYTES_PER_CALLER = 200 * 1024 * 1024
MAX_LIVE_BYTES_TOTAL = 1024 * 1024 * 1024
_SEAL_DIR_PREFIX = "epi_mcp_seal_"


def purge_expired_artifacts(now: float | None = None) -> int:
    """Delete sealed files (and their temp dirs) past their retention. Returns count."""
    import shutil
    import time

    now = time.time() if now is None else now
    purged = 0
    for aid, expires in list(_ARTIFACT_EXPIRY.items()):
        if expires > now:
            continue
        path = ARTIFACTS.pop(aid, None)
        _ARTIFACT_EXPIRY.pop(aid, None)
        _ARTIFACT_OWNER.pop(aid, None)
        purged += 1
        if not path:
            continue
        parent = Path(path).parent
        try:
            if parent.name.startswith(_SEAL_DIR_PREFIX):
                shutil.rmtree(parent, ignore_errors=True)
            else:
                Path(path).unlink(missing_ok=True)
        except OSError:
            pass
    return purged


def _check_quota(owner: str) -> None:
    """Refuse a new seal when the caller (or the whole server) holds too much live data."""
    mine = [size for o, size in _ARTIFACT_OWNER.values() if o == owner]
    total = sum(size for _, size in _ARTIFACT_OWNER.values())
    if len(mine) >= MAX_LIVE_ARTIFACTS_PER_CALLER or sum(mine) >= MAX_LIVE_BYTES_PER_CALLER:
        raise ValueError(
            "Storage quota reached for this caller. Nothing was sealed. Download your existing "
            "files; the server removes them 24 h after sealing, which frees space."
        )
    if total >= MAX_LIVE_BYTES_TOTAL:
        raise ValueError(
            "The server's temporary storage is full. Nothing was sealed. Try again later."
        )


def _issue_download_token(artifact_id: str) -> str:
    import secrets
    import time

    now = time.time()
    for tok, (_, exp) in list(_DOWNLOAD_TOKENS.items()):
        if exp < now:
            del _DOWNLOAD_TOKENS[tok]
    token = secrets.token_urlsafe(24)
    _DOWNLOAD_TOKENS[token] = (artifact_id, now + DOWNLOAD_TTL_SECONDS)
    return token


def download_token_valid(artifact_id: str, token: str | None) -> bool:
    import hmac
    import time

    if not token:
        return False
    rec = _DOWNLOAD_TOKENS.get(token)
    if rec is None or rec[1] < time.time():
        return False
    return hmac.compare_digest(rec[0], artifact_id)


def _stable_signer() -> bool:
    import os as _os

    return bool(
        (_os.environ.get("EPI_SIGNING_SEED") or _os.environ.get("EPI_OAUTH_SECRET") or "").strip()
    )


def _resolve_epi_path(epi_path: str) -> str:
    """Accept a sealed artifact_id (as returned by epi_seal_record) or a path."""
    return ARTIFACTS.get(epi_path.strip(), epi_path)

# Caller identity for the current seal operation. The HTTP layer sets
# this from the verified credential; stdio runs are the server operator.
# Bindings stay honest: a seal is always attributable to someone.
from contextvars import ContextVar as _ContextVar

_current_subject: _ContextVar[str | None] = _ContextVar("epi_mcp_subject", default=None)
_current_identity: _ContextVar[dict | None] = _ContextVar("epi_mcp_identity", default=None)


def get_current_subject() -> str | None:
    """Subject bound to this call, or None for anonymous/operator use."""
    return _current_subject.get()


def _artifact_payload(epi_path: str | Path) -> dict[str, Any]:
    raw = Path(epi_path).read_bytes()
    return {
        "filename": Path(epi_path).name,
        "epi_b64": base64.b64encode(raw).decode("ascii"),
        "size_bytes": len(raw),
    }


# Largest base64 payload returned inline; leaves room under the 1 MiB MCP event limit.
MAX_INLINE_B64 = 700_000
MAX_EVENTS = 5000
MAX_RECORD_BYTES = 8 * 1024 * 1024


def _check_size(events: list[dict[str, Any]]) -> None:
    """Refuse records the host cannot reliably deliver, with a way forward."""
    import json

    if len(events) > MAX_EVENTS:
        raise ValueError(
            f"Too many events ({len(events)} > {MAX_EVENTS}). Seal the conversation in "
            "parts, or send long tool output as fidelity=hash_only with its sha256."
        )
    size = len(json.dumps(events, default=str).encode("utf-8"))
    if size > MAX_RECORD_BYTES:
        raise ValueError(
            f"Record too large ({size // (1024 * 1024)} MB > {MAX_RECORD_BYTES // (1024 * 1024)} MB). "
            "Seal in parts, or send large attachments and tool output as "
            "fidelity=hash_only with their sha256."
        )


def epi_seal_record_tool(
    events: list[dict[str, Any]],
    goal: str = "MCP caller-provided record",
    output_path: str | None = None,
    include_bytes: bool = True,
) -> dict[str, Any]:
    """Seal caller-provided observable events. Returns file bytes + verdicts.

    Sealing requires an authenticated caller: the seal is bound to the
    caller's subject via a per-subject key (auto-created on first use),
    so identity is attributable instead of anonymous server-key LOW.
    """
    from epi_mcp.auth import subject_key

    _check_size(events)
    subject = get_current_subject()
    if subject is None:
        raise PermissionError(
            "Sealing requires an authenticated caller. Anonymous callers "
            "may verify and export, but not seal."
        )
    owner = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:16]
    purge_expired_artifacts()
    if output_path is None:
        _check_quota(owner)
    sealed = seal_record(
        events,
        goal=goal,
        output_path=output_path,
        key_name=subject_key(subject),
        identity=_current_identity.get(),
    )
    sealed["sealed_for_subject"] = owner
    from epi_mcp.idp import describe_identity as _describe

    _who = _describe(_current_identity.get())
    sealed["sealer_identity"] = (
        {"verified": True,
         "who": _who.get("email")
         or (f"@{_who['username']}" if _who.get("username") else "")
         or f"account {_who.get('account_id', '')[:8]}",
         "via": _who.get("verified_by"), "note": _who["statement"]}
        if _who.get("verified")
        else {"verified": False, "note": _who["statement"]}
    )
    check = verify_artifact(sealed["epi_path"])
    sealed["seal_check"] = {
        "integrity_ok": check["integrity_ok"],
        "signature_valid": check["signature_valid"],
        "trust_level": check["trust_level"],
    }
    payload = _artifact_payload(sealed["epi_path"])
    # MCP clients cap a single event at 1 MiB. The file travels as base64 (+33%),
    # so past this size it is not inlined: the download link (and the server path
    # on stdio) carry it instead. Keeps every response deliverable.
    inline = include_bytes and len(payload["epi_b64"]) <= MAX_INLINE_B64
    if inline:
        sealed.update(payload)
    else:
        sealed.update({k: v for k, v in payload.items() if k != "epi_b64"})
        if include_bytes:
            sealed["bytes_omitted"] = (
                "The file is too large to include in this response. "
                "Use download_url (or epi_path when running locally)."
            )
    sealed["artifact_id"] = sealed["sha256"][:16]
    purge_expired_artifacts()
    _epi = Path(sealed["epi_path"]).resolve()
    ARTIFACTS[sealed["artifact_id"]] = str(_epi)
    if output_path is None and _epi.parent.name.startswith(_SEAL_DIR_PREFIX):
        import time as _time

        _ARTIFACT_EXPIRY[sealed["artifact_id"]] = _time.time() + DOWNLOAD_TTL_SECONDS
        _ARTIFACT_OWNER[sealed["artifact_id"]] = (owner, _epi.stat().st_size)
        sealed["retention"] = (
            "The server deletes this file when the download link expires "
            f"({DOWNLOAD_TTL_SECONDS // 3600} h). Download it now; after that only your copy exists."
        )
    sealed["download_path"] = f"/artifacts/{sealed['artifact_id']}"
    import os as _os

    _public = (_os.environ.get("EPI_MCP_PUBLIC_URL") or "").strip().rstrip("/")
    if _public:
        token = _issue_download_token(sealed["artifact_id"])
        sealed["download_url"] = f"{_public}{sealed['download_path']}?t={token}"
        sealed["view_url"] = f"{_public}/view/{sealed['artifact_id']}?t={token}"
        sealed["download_expires_in_seconds"] = DOWNLOAD_TTL_SECONDS
        sealed["how_to_view"] = (
            "Open view_url in any browser to read and check the sealed record now; nothing "
            "needs installing. Use download_url to keep the file. Anyone can also check a "
            "downloaded file by uploading it at https://epilabs.org/verify. Installing "
            "epi-recorder is optional and only needed for command-line checks."
        )
    else:
        sealed["download_url"] = None
        sealed["view_url"] = None
    sealed["warnings"] = list(sealed.get("fidelity", {}).get("warnings", []))
    sealed["trust_command"] = (
        f"epi keys trust {sealed['filename']} --name <label>" if "filename" in sealed else None
    )
    sealed["signer_stability"] = (
        "stable: signing key is derived from a server seed, so this signer is the same "
        "after restarts and can be pinned with `epi keys trust`"
        if _stable_signer()
        else "not stable: the signing key lives on the server's disk and changes if the "
        "disk is reset, so pinning it will not last. Set EPI_OAUTH_SECRET or EPI_SIGNING_SEED."
    )
    sealed["how_to_verify"] = (
        "Independent check, no connector needed: download the file and run "
        f"`epi verify {sealed['filename']}`. Editing any byte makes it fail."
        if "filename" in sealed
        else "Download the file and run `epi verify <file>.epi`."
    )
    sealed["summary_counts"] = summarize_steps(events)
    sealed["sealed_at"] = datetime.now(timezone.utc).isoformat()
    sealed["not_captured"] = NOT_CAPTURED
    return sealed


def get_artifact_path(artifact_id: str) -> Path | None:
    """Resolve a download id to its sealed file, or None."""
    purge_expired_artifacts()
    raw = (artifact_id or "").strip()
    if not raw or "/" in raw or "\\" in raw or ".." in raw:
        return None
    hit = ARTIFACTS.get(raw)
    if not hit:
        return None
    path = Path(hit)
    return path if path.is_file() else None


def epi_verify_tool(epi_path: str) -> dict[str, Any]:
    """Verify a sealed file by artifact_id (from epi_seal_record) or server path."""
    epi_path = _resolve_epi_path(epi_path)
    return verify_artifact(epi_path)


def epi_export_summary_tool(epi_path: str, max_steps: int = 50) -> dict[str, Any]:
    """Read back a sealed timeline (artifact_id or server path)."""
    epi_path = _resolve_epi_path(epi_path)
    return export_summary(epi_path, max_steps=max_steps)


def summarize_steps(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Server-computed counts for the sealed summary block.

    Counts are derived from sealed step kinds, never narrated by the
    caller: tool activity, artifacts, and redaction markers.
    """
    kinds: dict[str, int] = {}
    for step in steps:
        kind = str(step.get("kind", "custom"))
        kinds[kind] = kinds.get(kind, 0) + 1
    redactions = sum(_count_occurrences(s.get("content"), REDACTED_MARKER) for s in steps)
    return {
        "events": len(steps),
        "tool_calls": sum(kinds.get(k, 0) for k in TOOL_KINDS),
        "artifacts": sum(kinds.get(k, 0) for k in ARTIFACT_KINDS),
        "redactions": redactions,
        "omissions_declared": kinds.get(OMISSION_KIND, 0),
        "by_kind": kinds,
    }


def _semantic(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop per-run sealer metadata (``_epi_*``) so two runs are compared on
    what the caller recorded, not on when each was sealed."""
    out = []
    for step in timeline:
        content = step.get("content")
        if isinstance(content, dict):
            content = {k: v for k, v in content.items() if not str(k).startswith("_epi_")}
        out.append({**step, "content": content})
    return out


def _decisions(timeline: list[dict[str, Any]]) -> list[Any]:
    out = []
    for step in timeline:
        if str(step.get("kind", "")).endswith("decision"):
            content = step.get("content")
            out.append(content.get("decision") if isinstance(content, dict) else content)
    return out


def compare_runs(epi_path_a: str | Path, epi_path_b: str | Path) -> dict[str, Any]:
    """Compare two sealed timelines: deltas, decisions, first divergence.

    Compares sealed records only — never the runs behind them.
    """
    from epi_mcp.records import export_summary

    epi_path_a = _resolve_epi_path(str(epi_path_a))
    epi_path_b = _resolve_epi_path(str(epi_path_b))
    a = export_summary(epi_path_a, max_steps=100000)
    b = export_summary(epi_path_b, max_steps=100000)
    ta, tb = _semantic(a["timeline"]), _semantic(b["timeline"])
    kinds_a = sorted({str(s.get("kind")) for s in ta})
    kinds_b = sorted({str(s.get("kind")) for s in tb})
    decisions_a, decisions_b = _decisions(ta), _decisions(tb)
    first_divergence: int | None = None
    for i, (sa, sb) in enumerate(zip(ta, tb)):
        if sa.get("kind") != sb.get("kind") or sa.get("content") != sb.get("content"):
            first_divergence = i
            break
    if first_divergence is None and len(ta) != len(tb):
        first_divergence = min(len(ta), len(tb))
    return {
        "run_a": {"steps": a["steps_total"], "kinds": kinds_a, "decisions": decisions_a},
        "run_b": {"steps": b["steps_total"], "kinds": kinds_b, "decisions": decisions_b},
        "delta_steps": b["steps_total"] - a["steps_total"],
        "kinds_only_in_b": sorted(set(kinds_b) - set(kinds_a)),
        "kinds_only_in_a": sorted(set(kinds_a) - set(kinds_b)),
        "decisions_match": decisions_a == decisions_b,
        "first_divergence_index": first_divergence,
        "scope_note": "Compares sealed records only, not the runs behind them.",
    }
