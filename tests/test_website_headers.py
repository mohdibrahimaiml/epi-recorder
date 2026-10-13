"""WP-SEC-3: security headers + CSP groundwork.

Requires:
  1. website/_headers exists with HSTS, nosniff, Referrer-Policy,
     Permissions-Policy, X-Frame-Options and a Report-Only CSP.
  2. No inline event-handler attributes (onclick=, onload=, ...) anywhere in
     website/ — CSP hashes cannot cover them; they must use addEventListener.
  3. Every executable inline <script> block's sha256 hash is allowlisted in
     the _headers CSP (hashes are computed over the exact served bytes).
  4. _headers is synced byte-identical into the deploy mirrors.
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


def csp_hashes(headers_text: str) -> set[str]:
    return set(re.findall(r"'sha256-([A-Za-z0-9+/=]+)'", headers_text))


def test_headers_file_has_required_headers():
    assert HEADERS.is_file(), "website/_headers missing"
    text = HEADERS.read_text(encoding="utf-8", errors="ignore")
    for required in [
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "X-Frame-Options",
        "Content-Security-Policy-Report-Only",
    ]:
        assert required in text, f"_headers missing {required}"
    # Report-Only first: enforcing comes as a separate step after a clean run.
    assert "Content-Security-Policy:" not in text.replace(
        "Content-Security-Policy-Report-Only:", ""
    ), "must ship Report-Only first, not enforcing"


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
    m = re.search(r"Content-Security-Policy-Report-Only:\s*(.+)", text)
    assert m, "no Report-Only CSP line in _headers"
    csp_line = m.group(1)
    allowed = set(re.findall(r"'sha256-([A-Za-z0-9+/=]+)'", csp_line))
    assert allowed, "no script hashes in the _headers CSP line"
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


def test_headers_synced_to_mirrors():
    wanted = HEADERS.read_bytes()
    for mirror in MIRRORS:
        candidate = mirror / "_headers"
        assert candidate.is_file(), f"_headers missing in mirror {mirror.name}"
        assert candidate.read_bytes() == wanted, f"_headers differs in {mirror.name}"
