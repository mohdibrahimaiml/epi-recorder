"""Telemetry aggregation for the EPI admin dashboard.

Reads the append-only telemetry files written by verify_portal and computes
DAU/WAU/MAU, command breakdown, version distribution, and detected organizations.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


_CACHE: dict[str, Any] = {}
_CACHE_TTL_SECONDS = 60


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_ts(value: str) -> datetime | None:
    """Best-effort ISO timestamp parser."""
    try:
        # Handle trailing 'Z' and offsets.
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except Exception:
        return None


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []
    return records


def compute_telemetry_metrics(storage_dir: Path | str) -> dict[str, Any]:
    """Compute dashboard metrics from telemetry event and pilot signup logs."""
    global _CACHE
    cache_key = str(storage_dir)
    now = _utc_now().timestamp()
    cached = _CACHE.get(cache_key)
    if cached and (now - cached["cached_at"]) < _CACHE_TTL_SECONDS:
        return cached["metrics"]

    storage = Path(storage_dir)
    events = _read_jsonl_records(storage / "telemetry" / "events.jsonl")
    signups = _read_jsonl_records(storage / "telemetry" / "pilot_signups.jsonl")

    install_ids: set[str] = set()
    install_days: dict[str, set[str]] = {}
    last_seen: dict[str, datetime] = {}
    command_counter: Counter = Counter()
    version_counter: Counter = Counter()
    org_domains: set[str] = set()
    org_githubs: set[str] = set()

    cutoff_dau = _utc_now() - timedelta(days=1)
    cutoff_wau = _utc_now() - timedelta(days=7)
    cutoff_mau = _utc_now() - timedelta(days=30)

    for record in events:
        payload = record.get("payload") if isinstance(record, dict) else record
        if not isinstance(payload, dict):
            continue

        install_id = str(payload.get("install_id") or "")
        if not install_id:
            continue

        ts = _parse_ts(payload.get("timestamp", "")) or _parse_ts(record.get("ts", ""))
        if ts is None:
            ts = _utc_now()

        install_ids.add(install_id)
        if ts > last_seen.get(install_id, datetime.min.replace(tzinfo=UTC)):
            last_seen[install_id] = ts
        install_days.setdefault(install_id, set()).add(ts.strftime("%Y-%m-%d"))

        version = str(payload.get("epi_version") or "unknown")
        if version:
            version_counter[version] += 1

        metadata = payload.get("metadata") or {}
        if isinstance(metadata, dict):
            command = str(metadata.get("command") or "unknown")
            if command:
                command_counter[command] += 1
            domain = metadata.get("email_domain")
            if domain:
                org_domains.add(str(domain).lower())
            github = metadata.get("github_org")
            if github:
                org_githubs.add(str(github).lower())

    dau = {iid for iid, ts in last_seen.items() if ts >= cutoff_dau}
    wau = {iid for iid, ts in last_seen.items() if ts >= cutoff_wau}
    mau = {iid for iid, ts in last_seen.items() if ts >= cutoff_mau}
    returning = {iid for iid, days in install_days.items() if len(days) >= 2}

    metrics = {
        "generated_at": _utc_now().isoformat(),
        "total_installs": len(install_ids),
        "active_installs": {
            "dau": len(dau),
            "wau": len(wau),
            "mau": len(mau),
        },
        "returning_users": len(returning),
        "organizations_detected": {
            "email_domains": sorted(org_domains),
            "github_orgs": sorted(org_githubs),
            "total": len(org_domains | org_githubs),
        },
        "pilot_signups": len(signups),
        "top_commands": dict(command_counter.most_common(20)),
        "version_distribution": dict(version_counter.most_common(20)),
    }

    _CACHE[cache_key] = {"metrics": metrics, "cached_at": now}
    return metrics


def invalidate_cache(storage_dir: Path | str) -> None:
    _CACHE.pop(str(storage_dir), None)
