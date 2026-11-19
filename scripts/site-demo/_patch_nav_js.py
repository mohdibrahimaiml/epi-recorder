"""Ensure every HTML page with mobBtn loads nav.js before instrument-nav."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def patch(text: str) -> str:
    t = text
    # cache busts
    t = t.replace("js/nav.js?v=2", "js/nav.js?v=3")
    t = t.replace("/js/nav.js?v=2", "/js/nav.js?v=3")
    t = t.replace("css/mobile.css?v=1", "css/mobile.css?v=2")
    t = t.replace("/css/mobile.css?v=1", "/css/mobile.css?v=2")
    t = t.replace("css/wow.css?v=4", "css/wow.css?v=5")
    t = t.replace("/css/wow.css?v=4", "/css/wow.css?v=5")
    t = t.replace("css/wow.css?v=3", "css/wow.css?v=5")
    t = t.replace("/css/wow.css?v=3", "/css/wow.css?v=5")

    if 'id="mobBtn"' not in t and "id='mobBtn'" not in t:
        return t
    if "nav.js" in t:
        return t

    if 'href="/css/' in t or "href='/css/" in t:
        js = "/js/"
    elif "../js/" in t or "../css/" in t:
        js = "../js/"
    else:
        js = "js/"

    script = f'<script src="{js}nav.js?v=3"></script>\n'
    for marker in (
        f'<script src="{js}instrument-nav.js"',
        f'<script src="{js}theme.js"',
        f'<script src="{js}auth-ui.js"',
    ):
        if marker in t:
            return t.replace(marker, script + marker, 1)
    if "</body>" in t:
        return t.replace("</body>", script + "</body>", 1)
    return t


def main() -> None:
    n = 0
    for p in sorted(ROOT.rglob("*.html")):
        if "assets" in p.parts and p.name.startswith("_"):
            continue
        orig = p.read_text(encoding="utf-8", errors="replace")
        new = patch(orig)
        if new != orig:
            p.write_text(new, encoding="utf-8")
            n += 1
            print("patched", p.relative_to(ROOT))
    print("total", n)


if __name__ == "__main__":
    main()
