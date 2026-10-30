"""Refresh `claimed_sha256` in every copy of the DEMO trust page data.

Run after `python scripts/reseal_demo_epis.py --refresh-viewer`: re-sealing
changes the shipped bytes, so the hashes the DEMO page pins go stale
(`tests/test_demo_trust_page.py` compares them to the shipped file).

Only the hash strings are rewritten, so the diff stays three lines per copy.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"
COPIES = [
    WEBSITE / "t" / "acme-demo" / "demo-data.json",
    ROOT / "site" / "t" / "acme-demo" / "demo-data.json",
    ROOT / "verify_portal" / "static" / "t" / "acme-demo" / "demo-data.json",
    ROOT / "epi-official" / "t" / "acme-demo" / "demo-data.json",
]


def main() -> int:
    canonical = json.loads(COPIES[0].read_text(encoding="utf-8"))
    replacements: list[tuple[str, str]] = []
    for item in canonical.get("files") or []:
        rel = str(item["path"]).lstrip("/")
        digest = hashlib.sha256((WEBSITE / rel).read_bytes()).hexdigest()
        old = str(item.get("claimed_sha256") or "")
        if old != digest:
            print(f"{rel}: {old} -> {digest}")
            replacements.append((old, digest))
    if not replacements:
        print("pinned hashes already current")
        return 0

    for path in COPIES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for old, new in replacements:
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
