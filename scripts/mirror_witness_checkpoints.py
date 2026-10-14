#!/usr/bin/env python3
"""Copy signed witness checkpoints to the public mirror repo (stdlib only).

Reads, per inbox id in WITNESS_MIRROR_INBOXES (comma-separated):
  {CLOUD_URL}/w/{id}/checkpoints
plus {CLOUD_URL}/.well-known/epi-witness-key.json,
and writes checkpoints/{id}.json + witness-key.json under --out
(default: ./mirror). The workflow commits and pushes when files change.

Only explicitly listed inboxes are mirrored (opt-in per customer).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


def _get(url: str, timeout: int) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def mirror(cloud_url: str, inbox_ids: list[str], out: Path, timeout: int = 30) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    changed: list[str] = []
    keys = _get(f"{cloud_url}/.well-known/epi-witness-key.json", timeout)
    key_file = out / "witness-key.json"
    key_text = json.dumps(keys, indent=2, sort_keys=True) + "\n"
    if not key_file.is_file() or key_file.read_text(encoding="utf-8") != key_text:
        key_file.write_text(key_text, encoding="utf-8")
        changed.append(key_file.name)
    for inbox_id in inbox_ids:
        doc = _get(f"{cloud_url}/w/{inbox_id}/checkpoints", timeout)
        if doc.get("inbox") != inbox_id:
            raise ValueError(f"checkpoints are for {doc.get('inbox')}, want {inbox_id}")
        target = out / f"{inbox_id}.json"
        text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")
            changed.append(target.name)
    return changed


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
    except Exception as exc:
        print(f"mirror failed: {exc}", file=sys.stderr)
        return 1
    print(f"mirrored {len(inbox_ids)} inbox(es), {len(changed)} file(s) changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
