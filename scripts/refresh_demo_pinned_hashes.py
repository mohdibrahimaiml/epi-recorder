"""Refresh `claimed_sha256` and `size_bytes` in every copy of the DEMO data.

Run after `python scripts/reseal_demo_epis.py`: re-sealing changes the shipped
bytes, so both the hash and the byte count the DEMO page prints go stale
(`tests/test_demo_trust_page.py` compares each to the served file).
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
    changed = False
    for item in canonical.get("files") or []:
        rel = str(item["path"]).lstrip("/")
        path = WEBSITE / rel
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        size = path.stat().st_size
        if str(item.get("claimed_sha256") or "") != digest:
            print(f"{rel}: sha256 {item.get('claimed_sha256')} -> {digest}")
            item["claimed_sha256"] = digest
            changed = True
        if item.get("size_bytes") != size:
            print(f"{rel}: size {item.get('size_bytes')} -> {size}")
            item["size_bytes"] = size
            changed = True
    if not changed:
        print("pinned hashes and sizes already current")
        return 0

    text = json.dumps(canonical, indent=2, ensure_ascii=False) + "\n"
    for path in COPIES:
        if not path.exists():
            continue
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
