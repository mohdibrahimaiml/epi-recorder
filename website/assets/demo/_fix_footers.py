"""Replace all main-page footers with one canonical instrument footer."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FOOTER = """
<footer class="site-footer">
  <div class="container">
    <div class="footer-inner">
      <div class="footer-left">
        <img src="{logo}" alt="EPI Labs" class="footer-logo">
        <span class="footer-copy">&copy; 2026 EPI LABS. Apache-2.0. Built in India. Engineered for the world.</span>
      </div>
      <ul class="footer-links">
        <li><a href="/verify/">Verify</a></li>
        <li><a href="/pricing">Pricing</a></li>
        <li><a href="/enterprise">Enterprise</a></li>
        <li><a href="/account">Account</a></li>
        <li><a href="/how-it-works">Docs</a></li>
        <li><a href="/trust">Trust</a></li>
        <li><a href="/integrations">Integrations</a></li>
        <li><a href="/use-cases">Use cases</a></li>
        <li><a href="/status">Status</a></li>
        <li><a href="https://github.com/mohdibrahimaiml/epi-recorder" target="_blank" rel="noopener">GitHub</a></li>
        <li><a href="/terms">Terms</a></li>
        <li><a href="/privacy">Privacy</a></li>
        <li><a href="/refund">Refunds</a></li>
        <li><a href="mailto:mohdibrahim@epilabs.org">Contact</a></li>
      </ul>
    </div>
  </div>
</footer>
"""

# Pages to standardize (not app shells)
INCLUDE = {
    "index.html",
    "pricing.html",
    "account.html",
    "enterprise.html",
    "how-it-works.html",
    "integrations.html",
    "trust.html",
    "use-cases.html",
    "status.html",
    "privacy.html",
    "terms.html",
    "refund.html",
    "welcome.html",
    "verify.html",
}


def logo_for(path: Path) -> str:
    rel = path.relative_to(ROOT)
    depth = len(rel.parts) - 1
    return "../assets/logo.png" if depth >= 1 else "assets/logo.png"


def replace_footers(html: str, logo: str) -> str:
    footer = FOOTER.format(logo=logo)
    # Remove all existing footers
    html2 = re.sub(r"<footer\b[\s\S]*?</footer>\s*", "", html, flags=re.I)
    # Insert before first script that looks like end-of-page, or before </body>
    # Prefer insert before theme.js / instrument / closing body
    m = re.search(
        r'(<script[^>]+src="[^"]*(?:theme|instrument-nav|auth-ui|home-verify)\.js"[^>]*>\s*</script>\s*)+</body>',
        html2,
        flags=re.I,
    )
    if m:
        # insert footer before the last block of scripts before body
        # simpler: insert before </body>
        pass
    if "</body>" in html2:
        html2 = html2.replace("</body>", footer + "\n</body>", 1)
    else:
        html2 += footer
    return html2


def main() -> None:
    for path in ROOT.rglob("*.html"):
        if path.name not in INCLUDE and path.parent.name not in ("verify",):
            # also do verify/index.html
            if not (path.parent.name == "verify" and path.name == "index.html"):
                if path.parent.name == "enterprise" and path.name == "index.html":
                    pass  # include enterprise/index
                else:
                    continue
        if path.name not in INCLUDE and not (
            (path.parent.name == "verify" and path.name == "index.html")
            or (path.parent.name == "enterprise" and path.name == "index.html")
        ):
            continue

        html = path.read_text(encoding="utf-8")
        logo = logo_for(path)
        new = replace_footers(html, logo)
        # Ensure footer CSS cache bump on epi.css if linked
        new = re.sub(r"epi\.css\?v=\d+", "epi.css?v=27", new)
        new = re.sub(r"epi-v2\.css\?v=\d+", "epi-v2.css?v=7", new)
        path.write_text(new, encoding="utf-8")
        n = len(re.findall(r"<footer\b", new, flags=re.I))
        print(f"{path.relative_to(ROOT)}: {n} footer(s)")


if __name__ == "__main__":
    main()
