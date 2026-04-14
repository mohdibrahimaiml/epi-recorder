#!/usr/bin/env python3
"""Create a demo bundle containing the demo .epi and AGT export.

Usage:
  python scripts/package_demo.py --out release/demo_refund_demo.zip
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
import zipfile


def find_demo_epi(preferred: str | None = None) -> Path | None:
    # Prefer the canonical demo recording location
    cand = Path.cwd() / "epi-recordings" / "demo_refund.epi"
    if cand.exists():
        return cand

    # Fallback: newest .epi in workspace
    cands = list(Path.cwd().rglob("*.epi"))
    if not cands:
        return None
    return sorted(cands, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def package_demo(out_path: Path) -> int:
    epi = find_demo_epi()
    if not epi:
        print("No .epi artifact found in workspace. Run demo_refund.py first.", file=sys.stderr)
        return 2

    agt = epi.with_suffix(".agt.json")
    readme = Path.cwd() / "demo_assets" / "README.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(epi, arcname=epi.name)
        if agt.exists():
            zf.write(agt, arcname=agt.name)
        if readme.exists():
            zf.write(readme, arcname="README.md")

    print(f"Created demo bundle: {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package demo .epi and AGT export into a zip")
    parser.add_argument("--out", help="Output zip path", default="release/demo_refund_demo.zip")
    args = parser.parse_args(argv)
    return package_demo(Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
