"""Patch remaining website pages with instrument chrome (nav + CSS)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

NAV = """<nav id="nav">
  <div class="nav-inner">
    <a href="/" class="nav-logo"><img src="/assets/logo.png" alt="EPI Labs"></a>
    <ul class="nav-links" id="navLinks">
      <li><a href="/verify/">Verify</a></li>
      <li><a href="/how-it-works">Docs</a></li>
      <li><a href="/pricing">Pricing</a></li>
      <li><a href="/enterprise">Enterprise</a></li>
      <li><a href="https://github.com/mohdibrahimaiml/epi-recorder" target="_blank" rel="noopener">GitHub</a></li>
      <li id="nav-auth-slot"></li>
      <li><a href="/account" class="nav-link-cta">Sign in</a></li>
    </ul>
    <button type="button" class="nav-mob" id="mobBtn" aria-label="Menu" aria-expanded="false"><span></span><span></span><span></span></button>
  </div>
</nav>
<div class="mob-menu" id="mobMenu" style="display:none">
  <a href="/verify/">Verify</a>
  <a href="/how-it-works">Docs</a>
  <a href="/pricing">Pricing</a>
  <a href="/enterprise">Enterprise</a>
  <a href="https://github.com/mohdibrahimaiml/epi-recorder" target="_blank" rel="noopener">GitHub</a>
  <a href="/account">Sign in</a>
</div>"""

# account uses relative logo path
NAV_REL = NAV.replace('src="/assets/logo.png"', 'src="assets/logo.png"')

FOOTER = """
<footer>
  <div class="container"><div class="footer-inner">
    <div class="footer-left">
      <img src="/assets/logo.png" alt="EPI Labs" class="footer-logo">
      <span class="footer-copy">&copy; 2026 EPI LABS. Apache-2.0.</span>
    </div>
    <ul class="footer-links">
      <li><a href="/verify/">Verify</a></li>
      <li><a href="/pricing">Pricing</a></li>
      <li><a href="/enterprise">Enterprise</a></li>
      <li><a href="/how-it-works">Docs</a></li>
      <li><a href="/integrations">Integrations</a></li>
      <li><a href="/trust">Trust</a></li>
      <li><a href="/use-cases">Use cases</a></li>
      <li><a href="/status">Status</a></li>
      <li><a href="/terms">Terms</a></li>
      <li><a href="/privacy">Privacy</a></li>
      <li><a href="mailto:mohdibrahim@epilabs.org">Contact</a></li>
    </ul>
  </div></div>
</footer>
<script src="/js/instrument-nav.js"></script>
<script src="/js/auth-ui.js"></script>
"""

FOOTER_REL = FOOTER.replace('src="/assets/logo.png"', 'src="assets/logo.png"').replace(
    'src="/js/', 'src="js/'
)


def ensure_css(html: str) -> str:
    if "epi-v2.css" not in html:
        html = html.replace(
            'href="css/epi.css',
            'href="css/epi.css',
        )
        # inject after epi.css link
        html = re.sub(
            r'(<link rel="stylesheet" href="css/epi\.css[^"]*">)',
            r'\1\n<link rel="stylesheet" href="css/epi-v2.css?v=4">',
            html,
            count=1,
        )
        html = re.sub(
            r'(<link rel="stylesheet" href="/css/epi\.css[^"]*">)',
            r'\1\n<link rel="stylesheet" href="/css/epi-v2.css?v=4">',
            html,
            count=1,
        )
    # bump epi.css version lightly
    html = re.sub(r'css/epi\.css\?v=\d+', "css/epi.css?v=26", html)
    html = re.sub(r"/css/epi\.css\?v=\d+", "/css/epi.css?v=26", html)
    return html


def replace_nav(html: str, rel: bool = False) -> str:
    nav = NAV_REL if rel else NAV
    # Replace from <nav to end of mob-menu or just </nav>
    if re.search(r"<nav\b", html):
        html = re.sub(
            r"<nav\b[\s\S]*?</nav>\s*(?:<div class=\"mob-menu\"[\s\S]*?</div>\s*)?",
            nav + "\n",
            html,
            count=1,
        )
    return html


def set_body_instrument(html: str) -> str:
    if re.search(r"<body[^>]*class=", html):
        html = re.sub(
            r"<body([^>]*)class=\"([^\"]*)\"",
            lambda m: f'<body{m.group(1)}class="{m.group(2)} epi-instrument"'
            if "epi-instrument" not in m.group(2)
            else m.group(0),
            html,
            count=1,
        )
        if "data-theme" not in html.split("<body", 1)[1][:200]:
            html = re.sub(r"<body([^>]*)>", r'<body\1 data-theme="dark">', html, count=1)
    else:
        html = re.sub(r"<body>", '<body class="epi-instrument" data-theme="dark">', html, count=1)
    return html


def ensure_footer_scripts(html: str, rel: bool = False) -> str:
    footer = FOOTER_REL if rel else FOOTER
    if "instrument-nav.js" in html:
        return html
    if "</body>" in html:
        # remove duplicate auth-ui if we re-add - keep one
        html = re.sub(r'<script src="[^"]*auth-ui\.js"></script>\s*', "", html)
        html = html.replace("</body>", footer + "\n</body>")
    return html


def patch_file(path: Path, rel: bool = False) -> None:
    html = path.read_text(encoding="utf-8")
    html = ensure_css(html)
    html = replace_nav(html, rel=rel)
    html = set_body_instrument(html)
    html = ensure_footer_scripts(html, rel=rel)
    path.write_text(html, encoding="utf-8")
    print("patched", path.name)


def main() -> None:
    # relative asset pages
    for name in ("account.html", "status.html", "privacy.html", "terms.html", "refund.html"):
        p = ROOT / name
        if p.exists():
            patch_file(p, rel=True)
    # portal: dark message only
    portal = ROOT / "portal.html"
    if portal.exists():
        portal.write_text(
            """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Redirecting to Verify…</title>
<meta http-equiv="refresh" content="0;url=/verify/?mode=server">
<link rel="canonical" href="https://epilabs.org/verify/?mode=server">
<link rel="stylesheet" href="/css/epi.css?v=26">
<link rel="stylesheet" href="/css/epi-v2.css?v=4">
<script>location.replace('/verify/?mode=server');</script>
</head>
<body class="epi-instrument" data-theme="dark" style="font-family:system-ui,sans-serif;padding:2rem;background:#0B0D10;color:#C8CDD6">
  <p>This page moved into <strong style="color:#F2F4F7">one Verify page</strong>.</p>
  <p>Opening <a href="/verify/?mode=server" style="color:#3DDC97">full report mode</a>
  (file will be uploaded). Private check: <a href="/verify/" style="color:#5B8CFF">/verify/</a>.</p>
</body>
</html>
""",
            encoding="utf-8",
        )
        print("patched portal.html")


if __name__ == "__main__":
    main()
