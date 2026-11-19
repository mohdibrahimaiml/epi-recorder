"""Inject mobile.css + nav.js across website HTML pages."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # website/


def patch(text: str, rel: Path) -> str:
    t = text
    t = t.replace("css/epi.css?v=29", "css/epi.css?v=30")
    t = t.replace("css/epi-v2.css?v=9", "css/epi-v2.css?v=10")
    t = t.replace("css/polish.css?v=3", "css/polish.css?v=4")
    t = t.replace("css/wow.css?v=2", "css/wow.css?v=3")

    # Detect CSS path prefix used on this page
    if 'href="/css/' in t or "href='/css/" in t:
        css_prefix = "/css/"
        js_prefix = "/js/"
    elif "../css/" in t:
        css_prefix = "../css/"
        js_prefix = "../js/"
    else:
        css_prefix = "css/"
        js_prefix = "js/"

    mobile_href = f'{css_prefix}mobile.css?v=1'
    if "mobile.css" not in t:
        for wow_v in ("wow.css?v=3", "wow.css?v=2", "wow.css"):
            needle = f'href="{css_prefix}{wow_v}"'
            if needle in t:
                t = t.replace(
                    needle,
                    f'{needle}>\n<link rel="stylesheet" href="{mobile_href}"',
                    1,
                )
                # fix double >> if original had >
                t = t.replace('"">', '">')  # no-op safety
                break
            # tag already closed: href="...">
            needle2 = f'href="{css_prefix}{wow_v}">'
            if needle2 in t:
                t = t.replace(
                    needle2,
                    f'{needle2}\n<link rel="stylesheet" href="{mobile_href}">',
                    1,
                )
                break
        # fallback: after epi-v2
        if "mobile.css" not in t:
            for key in ("epi-v2.css?v=10", "epi-v2.css?v=9", "epi.css?v=30", "epi.css?v=29"):
                needle2 = f'href="{css_prefix}{key}">'
                if needle2 in t:
                    t = t.replace(
                        needle2,
                        f'{needle2}\n<link rel="stylesheet" href="{mobile_href}">',
                        1,
                    )
                    break

    # Fix accidental double closing from first branch
    t = t.replace('.css?v=3">>', '.css?v=3">')
    t = t.replace('.css?v=2">>', '.css?v=2">')

    if ('id="mobBtn"' in t or "id='mobBtn'" in t) and "nav.js" not in t:
        script = f'<script src="{js_prefix}nav.js?v=2"></script>\n'
        inserted = False
        for marker in (
            f'<script src="{js_prefix}theme.js"',
            f'<script src="{js_prefix}auth-ui.js"',
            f'<script src="{js_prefix}instrument-nav.js"',
        ):
            if marker in t:
                t = t.replace(marker, script + marker, 1)
                inserted = True
                break
        if not inserted and "</body>" in t:
            t = t.replace("</body>", script + "</body>", 1)

    t = t.replace('id="mobMenu" style="display:none"', 'id="mobMenu" hidden')
    t = t.replace("id='mobMenu' style='display:none'", "id='mobMenu' hidden")
    return t


def main() -> None:
    n = 0
    for p in sorted(ROOT.rglob("*.html")):
        if "assets/demo" in str(p).replace("\\", "/"):
            continue
        orig = p.read_text(encoding="utf-8", errors="replace")
        new = patch(orig, p.relative_to(ROOT))
        if new != orig:
            p.write_text(new, encoding="utf-8")
            n += 1
            print("updated", p.relative_to(ROOT))
    print("total", n)


if __name__ == "__main__":
    main()
