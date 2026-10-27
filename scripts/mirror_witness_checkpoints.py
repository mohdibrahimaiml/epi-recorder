#!/usr/bin/env python3
"""Copy signed witness checkpoints to the public mirror repo.

Reads, per inbox id in WITNESS_MIRROR_INBOXES (comma-separated):
  {CLOUD_URL}/w/{id}/checkpoints
plus {CLOUD_URL}/.well-known/epi-witness-key.json,
and writes checkpoints/{id}.json + witness-key.json under --out
(default: ./mirror). The workflow commits and pushes when files change.

Only explicitly listed inboxes are mirrored (opt-in per customer).

Append-only: every checkpoint signature is verified with the published key, and
a day that already exists with different content is **never** overwritten — the
script exits non-zero with "history change detected" so the workflow fails loudly
instead of rewriting the mirror. Only stdlib + the `cryptography` package the
rest of EPI already requires (Ed25519 verification).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


class HistoryChangeError(Exception):
    """A mirrored day changed upstream: refuse to rewrite it."""


def _get(url: str, timeout: int) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def _canonical(inbox_id: str, cp: dict) -> bytes:
    return json.dumps(
        {
            "inbox": inbox_id,
            "day": cp.get("day"),
            "count": cp.get("count"),
            "head_hash": cp.get("head_hash"),
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _verify_checkpoint(pub_hex: str, inbox_id: str, cp: dict) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(str(pub_hex))).verify(
            bytes.fromhex(str(cp.get("signature") or "")), _canonical(inbox_id, cp)
        )
        return True
    except (InvalidSignature, ValueError):
        return False


def _merged_document(target: Path, inbox_id: str, doc: dict, pub_hex: str) -> tuple[str, bool]:
    """Append-only merge of one inbox. Returns (text, changed).

    Raises HistoryChangeError when a mirrored day would change.
    """
    existing: dict = {"inbox": inbox_id, "checkpoints": []}
    if target.is_file():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"{target} is not readable JSON: {exc}") from exc
    known = {str(cp.get("day")): cp for cp in existing.get("checkpoints", [])}
    changed = False
    for cp in doc.get("checkpoints", []):
        day = str(cp.get("day"))
        if not _verify_checkpoint(pub_hex, inbox_id, cp):
            raise ValueError(f"checkpoint {day}: Ed25519 signature INVALID — refusing to mirror")
        old = known.get(day)
        if old is None:
            known[day] = cp
            changed = True
            continue
        if (
            old.get("count"),
            old.get("head_hash"),
            old.get("signature"),
        ) != (cp.get("count"), cp.get("head_hash"), cp.get("signature")):
            raise HistoryChangeError(
                f"history change detected for {day}: mirror has {old.get('count')} entries/"
                f"{str(old.get('head_hash'))[:12]}…, live says {cp.get('count')} entries/"
                f"{str(cp.get('head_hash'))[:12]}…"
            )
    merged = {
        "inbox": inbox_id,
        "checkpoints": [known[day] for day in sorted(known)],
    }
    return json.dumps(merged, indent=2, sort_keys=True) + "\n", changed


def mirror(cloud_url: str, inbox_ids: list[str], out: Path, timeout: int = 30) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = out / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    keys = _get(f"{cloud_url}/.well-known/epi-witness-key.json", timeout)
    pub_hex = str(keys.get("witness_ed25519_pub_hex") or "")
    if not pub_hex:
        raise ValueError(
            "witness public key is not published; refusing to mirror unverifiable data"
        )

    # Build every file in memory first: a history change on any inbox must leave
    # the mirror exactly as it was.
    pending: dict[Path, str] = {}
    key_file = out / "witness-key.json"
    key_text = json.dumps(keys, indent=2, sort_keys=True) + "\n"
    if not key_file.is_file() or key_file.read_text(encoding="utf-8") != key_text:
        pending[key_file] = key_text

    for inbox_id in inbox_ids:
        doc = _get(f"{cloud_url}/w/{inbox_id}/checkpoints", timeout)
        if doc.get("inbox") != inbox_id:
            raise ValueError(f"checkpoints are for {doc.get('inbox')}, want {inbox_id}")
        target = checkpoint_dir / f"{inbox_id}.json"
        text, changed = _merged_document(target, inbox_id, doc, pub_hex)
        if changed:
            pending[target] = text

    for path, text in pending.items():
        path.write_text(text, encoding="utf-8")
    return [path.name for path in pending]


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Mirror signed checkpoints to a public repo dir.")
    parser.add_argument("--cloud-url", default=os.environ.get("EPI_CLOUD_URL", "https://cloud.epilabs.org"))
    parser.add_argument("--inboxes", default=os.environ.get("WITNESS_MIRROR_INBOXES", ""))
    parser.add_argument("--out", type=Path, default=Path("mirror"))
    args = parser.parse_args(argv)
    inbox_ids = [i.strip() for i in args.inboxes.split(",") if i.strip()]
    if not inbox_ids:
        print("WITNESS_MIRROR_INBOXES is empty — nothing to mirror.")
        return 0
    try:
        changed = mirror(args.cloud_url.rstrip("/"), inbox_ids, args.out)
    except HistoryChangeError as exc:
        print(f"history change detected: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"mirror failed: {exc}", file=sys.stderr)
        return 1
    print(f"mirrored {len(inbox_ids)} inbox(es), {len(changed)} file(s) changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
