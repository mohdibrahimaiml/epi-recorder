"""Add theme toggle, single auth slot, theme.js to all instrument pages."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FOUC = """<script>
(function(){try{var t=localStorage.getItem('epi-theme');if(t!=='light'&&t!=='dark'){t=window.matchMedia&&window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'}document.documentElement.setAttribute('data-theme',t)}catch(e){document.documentElement.setAttribute('data-theme','dark')}})();
</script>
"""

TOGGLE_LI = """      <li><button type="button" class="theme-toggle-nav" id="themeToggleNav" data-theme-toggle aria-label="Toggle color theme" title="Toggle theme">&#9788;</button></li>
"""

SCRIPTS_TAIL = """
<script src="{prefix}js/theme.js"></script>
<script src="{prefix}js/instrument-nav.js"></script>
<script src="{prefix}js/auth-ui.js"></script>
"""


def depth_prefix(path: Path) -> str:
    rel = path.relative_to(ROOT)
    return "../" * (len(rel.parts) - 1)


def ensure_fouc(html: str) -> str:
    if "epi-theme" in html and "localStorage.getItem('epi-theme')" in html:
        return html
    if "</head>" in html:
        return html.replace("</head>", FOUC + "</head>", 1)
    return html


def ensure_css_v(html: str) -> str:
    return re.sub(r"epi-v2\.css\?v=\d+", "epi-v2.css?v=6", html)


def fix_body(html: str) -> str:
    # Keep classes, remove forced data-theme="dark" (theme.js owns it)
    html = re.sub(
        r'(<body[^>]*)\s+data-theme="dark"',
        r"\1",
        html,
        count=1,
    )
    # Ensure epi-instrument or v2-home class present on main pages
    return html


def fix_nav(html: str) -> str:
    # Remove hard-coded Sign in CTA list items
    html = re.sub(
        r'\s*<li>\s*<a href="/account" class="nav-link-cta">[^<]*</a>\s*</li>',
        "",
        html,
        flags=re.I,
    )
    html = re.sub(
        r'\s*<a href="/account" class="nav-link-cta">Sign in</a>\s*',
        "",
        html,
        flags=re.I,
    )
    # Ensure nav-auth-slot exists once inside nav-links
    if 'id="nav-auth-slot"' not in html and "nav-links" in html:
        html = re.sub(
            r'(</ul>\s*(?:<!--|</div>|<button[^>]*nav-mob))',
            r'      <li id="nav-auth-slot"></li>\n    \1',
            html,
            count=1,
        )
    # Insert theme toggle before closing nav-links ul if missing
    if "themeToggleNav" not in html and "nav-links" in html:
        html = re.sub(
            r'(id="nav-auth-slot"></li>)',
            r'\1\n' + TOGGLE_LI,
            html,
            count=1,
        )
        if "themeToggleNav" not in html:
            html = re.sub(
                r'(id="nav-auth-slot"[^>]*>\s*</li>)',
                r'\1\n' + TOGGLE_LI,
                html,
                count=1,
            )
    # Mobile: remove duplicate Sign in lines; theme is desktop for now
    html = re.sub(
        r'(<div class="mob-menu"[^>]*>)([\s\S]*?)(</div>)',
        lambda m: m.group(1)
        + re.sub(
            r'\s*<a href="/account"[^>]*>Sign in</a>\s*',
            "\n  ",
            m.group(2),
            flags=re.I,
        )
        + m.group(3),
        html,
        count=1,
    )
    return html


def fix_scripts(html: str, prefix: str) -> str:
    # Remove broken theme.js/nav.js duplicates and bare force-dark scripts later
    # Ensure our triad before </body>
    for s in ("js/theme.js", "js/instrument-nav.js", "js/auth-ui.js"):
        # leave existing if present with any path
        pass
    # Strip old broken refs that 404
    html = re.sub(r'<script src="[^"]*js/nav\.js"></script>\s*', "", html)
    # Remove inline force-dark blocks that fight theme
    html = re.sub(
        r"document\.documentElement\.setAttribute\('data-theme','dark'\);\s*"
        r"document\.body\.setAttribute\('data-theme','dark'\);?",
        "",
        html,
    )
    html = re.sub(
        r'document\.documentElement\.setAttribute\("data-theme","dark"\);\s*',
        "",
        html,
    )

    tail = SCRIPTS_TAIL.format(prefix=prefix)
    if "js/theme.js" not in html:
        html = html.replace("</body>", tail + "</body>")
    else:
        # ensure instrument-nav + auth-ui
        if "instrument-nav.js" not in html:
            html = html.replace("</body>", f'<script src="{prefix}js/instrument-nav.js"></script>\n</body>')
        if "auth-ui.js" not in html:
            html = html.replace("</body>", f'<script src="{prefix}js/auth-ui.js"></script>\n</body>')
    return html


def patch(path: Path) -> None:
    html = path.read_text(encoding="utf-8")
    prefix = depth_prefix(path)
    html = ensure_css_v(html)
    html = ensure_fouc(html)
    html = fix_body(html)
    html = fix_nav(html)
    html = fix_scripts(html, prefix)
    path.write_text(html, encoding="utf-8")
    print("patched", path.relative_to(ROOT))


def main() -> None:
    pages = list(ROOT.glob("*.html")) + list((ROOT / "verify").glob("*.html"))
    for p in pages:
        if p.name in ("portal.html",):  # still patch lightly
            pass
        if p.name.endswith(".dualmode"):
            continue
        try:
            patch(p)
        except Exception as e:
            print("fail", p, e)


if __name__ == "__main__":
    main()
