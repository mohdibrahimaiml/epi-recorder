"""Normalize logo paths to match homepage (assets/logo.png)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def logo_for(path: Path) -> str:
    rel = path.relative_to(ROOT)
    depth = len(rel.parts) - 1
    return "../assets/logo.png" if depth >= 1 else "assets/logo.png"


def fix_html(path: Path) -> None:
    t = path.read_text(encoding="utf-8")
    orig = t
    logo = logo_for(path)
    # Any logo.png / logo.svg in src=
    t = re.sub(
        r'src=(["\'])(?:\.\./)*(?:/)?assets/logo\.(?:png|svg)\1',
        f'src="{logo}"',
        t,
    )
    if t != orig:
        path.write_text(t, encoding="utf-8")
        print(f"fixed {path.relative_to(ROOT)} -> {logo}")
    else:
        has = logo in t or "assets/logo.png" in t
        print(f"{'ok   ' if has else 'miss '} {path.relative_to(ROOT)}")


def main() -> None:
    for p in ROOT.rglob("*.html"):
        if any(x in p.parts for x in ("node_modules", ".git")):
            continue
        fix_html(p)


if __name__ == "__main__":
    main()
