from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: sqlite_snapshot.py <source_db> <destination_db>", file=sys.stderr)
        return 1

    source_path = Path(sys.argv[1]).resolve()
    destination_path = Path(sys.argv[2]).resolve()
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        print(f"Source database not found: {source_path}", file=sys.stderr)
        return 1

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
