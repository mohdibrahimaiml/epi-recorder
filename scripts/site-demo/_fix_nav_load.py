from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

for p in sorted(ROOT.rglob("*.html")):
    if "assets" in p.parts:
        continue
    t = p.read_text(encoding="utf-8", errors="replace")
    if 'id="mobBtn"' not in t and "id='mobBtn'" not in t:
        continue

    orig = t

    # strip forced dark theme line
    t = re.sub(
        r"document\.documentElement\.setAttribute\('data-theme','dark'\);\s*",
        "",
        t,
    )
    # strip broken one-liner burger toggles
    t = re.sub(
        r"var mb=document\.getElementById\('mobBtn'\),mm=document\.getElementById\('mobMenu'\);\s*"
        r"if\(mb&&mm\)\{mb\.addEventListener\('click',function\(\)\{mm\.style\.display=mm\.style\.display==='none'\|\|!mm\.style\.display\?'block':'none';\}\);\}",
        "",
        t,
    )

    if "nav.js" not in t:
        if 'href="/css/' in t or "href='/css/" in t:
            js = "/js/"
        elif "../css/" in t or "../js/" in t:
            js = "../js/"
        else:
            js = "js/"
        script = f'<script src="{js}nav.js?v=2"></script>\n'
        inserted = False
        for marker in (
            f'<script src="{js}theme.js"',
            f'<script src="{js}auth-ui.js"',
            f'<script src="{js}instrument-nav.js"',
        ):
            if marker in t:
                t = t.replace(marker, script + marker, 1)
                inserted = True
                break
        if not inserted and "</body>" in t:
            t = t.replace("</body>", script + "</body>", 1)

    if t != orig:
        p.write_text(t, encoding="utf-8")
        print("fixed", p.relative_to(ROOT))
