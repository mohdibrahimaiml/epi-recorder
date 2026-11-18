"""WP-SEC-3: security headers + enforcing CSP.

Requires:
  1. website/_headers exists with HSTS, nosniff, Referrer-Policy,
     Permissions-Policy, X-Frame-Options and one enforcing CSP.
  2. No inline event-handler attributes (onclick=, onload=, ...) anywhere in
     website/ — CSP hashes cannot cover them; they must use addEventListener.
  3. Every executable inline <script> block's sha256 hash is allowlisted in
     the enforcing CSP (hashes are computed over the exact served bytes).
  4. _headers is synced byte-identical into the deploy mirrors.

The policy used to ship a Report-Only twin because jszip's `new Function`
polyfill was assumed to need 'unsafe-eval', and because the ~100 font-src
violations per page made a "clean report" impossible. Both turned out to be
fixable (the polyfill branch is unreachable, and the fonts are now self-hosted),
so a second policy line is not just redundant — it is a place for the real
policy to quietly drift. These tests fail if one comes back.
"""

import base64
import hashlib
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]
WEBSITE = REPO / "website"
HEADERS = WEBSITE / "_headers"
MIRRORS = [REPO / "site", REPO / "epi-official", REPO / "verify_portal" / "static"]

# Script types the browser executes (CSP applies). Data blocks
# (application/json, text/plain, templates) are not executed.
EXECUTABLE_TYPES = {None, "text/javascript", "module", "application/ld+json"}

REQUIRED_DIRECTIVES = (
    "default-src 'self'",
    "font-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
    "report-uri /csp-report",
)


def inline_scripts(path: pathlib.Path):
    """Yield (opentag, body) for every inline <script> (no src=) in a file,
    pairing each opening tag with the next closing tag exactly like the
    HTML parser does (first </script> wins, even inside strings).
    Bodies are LF-normalized text: the HTML parser normalizes CRLF to LF
    before CSP hashing, so raw CRLF bytes would produce wrong hashes."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", text, re.S | re.I):
        attrs, body = m.group(1), m.group(2)
        tm = re.search(r'type\s*=\s*["\']?([^"\'\s>]+)', attrs, re.I)
        stype = tm.group(1).lower() if tm else None
        yield stype, body


def enforcing_policy(text: str) -> str:
    m = re.search(r"^  Content-Security-Policy:[ \t]*(.+)$", text, re.M)
    assert m, "no enforcing Content-Security-Policy line"
    return m.group(1)


def test_headers_file_has_required_headers():
    assert HEADERS.is_file(), "website/_headers missing"
    text = HEADERS.read_text(encoding="utf-8", errors="ignore")
    for required in [
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "X-Frame-Options",
        "Content-Security-Policy:",
    ]:
        assert required in text, f"_headers missing {required}"


def test_csp_is_enforced_not_report_only():
    """One policy line, and it enforces.

    A Report-Only twin next to an enforcing policy is worse than either alone:
    the browser intersects them, so a directive fixed in one place can still be
    blocked by the other, and reviewers read the wrong line.
    """
    text = HEADERS.read_text(encoding="utf-8", errors="ignore")
    assert "Content-Security-Policy-Report-Only" not in text, (
        "Report-Only policy is back; the site enforces one policy"
    )
    policy = enforcing_policy(text)
    directives = {d.strip().split(" ")[0] for d in policy.split(";") if d.strip()}
    for required in ("script-src", "style-src", "font-src", "connect-src", "img-src"):
        assert required in directives, f"{required} missing from the enforcing policy"
    for needle in REQUIRED_DIRECTIVES:
        assert needle in policy, f"enforcing policy missing {needle!r}"


def test_no_unsafe_eval_and_no_unsafe_inline_scripts():
    """The script-src relaxation jszip was blamed for is not needed.

    jszip's setImmediate polyfill calls `new Function` only when handed a
    string; JSZip's own call passes a function, so nothing is evaluated. A
    browser run of generateAsync/loadAsync/.async() under
    `default-src 'none'; script-src 'self'` showed zero violations while a
    control `new Function("return 1")` threw EvalError.
    """
    policy = enforcing_policy(HEADERS.read_text(encoding="utf-8", errors="ignore"))
    script_src = next(
        (d.strip() for d in policy.split(";") if d.strip().startswith("script-src")), ""
    )
    assert script_src, "no script-src directive"
    assert "'unsafe-eval'" not in script_src, "script-src must not allow 'unsafe-eval'"
    assert "'unsafe-inline'" not in script_src, (
        "script-src must rely on hashes, not 'unsafe-inline'"
    )


def test_no_inline_event_handlers():
    violations = []
    for path in sorted(WEBSITE.rglob("*.html")):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            for m in re.findall(r"\son\w+\s*=\s*\"[^\"]*\"|\son\w+\s*=\s*'[^']*'", line):
                violations.append(f"{path.relative_to(WEBSITE)}:{lineno}: {m[:100]}")
    assert not violations, (
        "inline event handlers (CSP cannot hash these; use addEventListener):\n"
        + "\n".join(violations)
    )


def test_no_javascript_urls():
    violations = []
    for path in sorted(WEBSITE.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in re.findall(r'javascript\s*:', text, re.I):
            violations.append(f"{path.relative_to(WEBSITE)}: {m}")
    assert not violations, "javascript: URLs:\n" + "\n".join(violations)


def test_every_inline_script_hash_allowlisted():
    text = HEADERS.read_text(encoding="utf-8", errors="ignore")
    policy = enforcing_policy(text)
    allowed = set(re.findall(r"'sha256-([A-Za-z0-9+/=]+)'", policy))
    assert allowed, "no script hashes in the enforcing CSP line"
    # Hashes must live in the CSP directive, not in comments.
    total = set(re.findall(r"'sha256-([A-Za-z0-9+/=]+)'", text))
    assert total == allowed, "hashes found outside the CSP line"
    missing = []
    for path in sorted(WEBSITE.rglob("*.html")):
        for stype, body in inline_scripts(path):
            if stype not in EXECUTABLE_TYPES:
                continue
            digest = base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
            if digest not in allowed:
                missing.append(
                    f"{path.relative_to(WEBSITE)} type={stype} sha256-{digest[:16]}..."
                )
    assert not missing, (
        "inline scripts without a CSP hash (add the hash or move to a file):\n"
        + "\n".join(missing)
    )


def test_fonts_are_self_hosted():
    """font-src 'self' is only honest if no stylesheet pulls a font CDN in.

    Bunny Fonts' CSS declared 50 @font-face rules, all resolving to
    cdn.jsdelivr.net (woff + woff2): ~100 blocked requests per page view.
    """
    offenders = []
    for path in sorted(WEBSITE.rglob("*.css")):
        # Comments explain the migration and name the old hosts; only real
        # declarations can cause a request.
        text = re.sub(
            r"/\*.*?\*/", "", path.read_text(encoding="utf-8", errors="ignore"), flags=re.S
        )
        for host in ("fonts.bunny.net", "fonts.googleapis.com", "fonts.gstatic.com"):
            if host in text:
                offenders.append(f"{path.relative_to(WEBSITE)}: {host}")
    for path in sorted(WEBSITE.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for host in ("fonts.bunny.net", "fonts.googleapis.com", "fonts.gstatic.com"):
            if host in text:
                offenders.append(f"{path.relative_to(WEBSITE)}: {host}")
    assert not offenders, "third-party font hosts remain:\n" + "\n".join(offenders)

    fonts_dir = WEBSITE / "fonts"
    assert (fonts_dir / "OFL.txt").is_file(), "fonts/OFL.txt missing (licence notice)"
    woff2 = list(fonts_dir.glob("*.woff2"))
    assert len(woff2) >= 10, f"expected the self-hosted font files, found {len(woff2)}"
    css = (WEBSITE / "css" / "fonts.css").read_text(encoding="utf-8")
    for name in ("Inter", "JetBrains Mono", "Fraunces", "Instrument Serif"):
        assert f"font-family: '{name}'" in css, f"{name} missing from css/fonts.css"


def test_headers_synced_to_mirrors():
    wanted = HEADERS.read_bytes()
    for mirror in MIRRORS:
        candidate = mirror / "_headers"
        assert candidate.is_file(), f"_headers missing in mirror {mirror.name}"
        assert candidate.read_bytes() == wanted, f"_headers differs in {mirror.name}"
