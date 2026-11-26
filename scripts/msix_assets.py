"""Make the PNG logos an MSIX package needs from the app icon.

Usage: python scripts/msix_assets.py <icon.ico> <output-dir>

Writes Square150x150Logo.png, Square44x44Logo.png and StoreLogo.png. The
largest frame in the .ico is resized with Lanczos, on a transparent canvas.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

SIZES = {
    "Square150x150Logo.png": 150,
    "Square44x44Logo.png": 44,
    "StoreLogo.png": 50,
}


def largest_frame(icon_path: Path) -> Image.Image:
    with Image.open(icon_path) as ico:
        sizes = sorted(ico.info.get("sizes") or [ico.size], key=lambda s: s[0] * s[1])
        ico.size = sizes[-1]
        return ico.convert("RGBA")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    icon_path, out_dir = Path(argv[1]), Path(argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    source = largest_frame(icon_path)
    for name, size in SIZES.items():
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(source.resize((size, size), Image.LANCZOS), (0, 0))
        canvas.save(out_dir / name)
        print(f"{name}: {size}x{size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
