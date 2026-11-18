#!/usr/bin/env python3
"""Build the script-src hash list for website/_headers (WP-SEC-3).

Every executable inline <script> block (no src=) is hashed over its exact
served bytes; the hashes go into the script-src directive of the enforcing
Content-Security-Policy line. Mirrors pick the file up via
scripts/sync_website.py; Cloudflare Pages serves it as HTTP headers.

The builder rewrites only the 'sha256-...' tokens of script-src, so the rest
of the policy stays exactly as written by hand.

Run after any website/ change that touches inline scripts:
  python scripts/build_csp_hashes.py && python scripts/sync_website.py
"""

from __future__ import annotations

import base64
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"
HEADERS = WEBSITE / "_headers"

PLACEHOLDER = "__SCRIPT_SRC_HASHES__"

# Script types the browser executes (CSP applies). Data blocks
# (application/json, text/plain, templates) are not executed.
EXECUTABLE_TYPES = {None, "text/javascript", "module", "application/ld+json"}

SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", re.S | re.I)
TYPE_RE = re.compile(r'type\s*=\s*["\']?([^"\'\s>]+)', re.I)
CSP_RE = re.compile(r"^  Content-Security-Policy:[ \t]*(.+)$", re.M)
HASH_RE = re.compile(r"'sha256-[A-Za-z0-9+/=]+'")


def iter_inline_scripts():
    # Text mode (universal newlines): the HTML parser normalizes CRLF to LF
    # before hashing, so hashes must be computed over LF-normalized text —
    # never over raw CRLF bytes.
    for path in sorted(WEBSITE.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in SCRIPT_RE.finditer(text):
            tm = TYPE_RE.search(m.group(1))
            stype = tm.group(1).lower() if tm else None
            if stype in EXECUTABLE_TYPES:
                yield path.relative_to(WEBSITE).as_posix(), m.group(2)


def main() -> int:
    hashes: set[str] = set()
    per_file: dict[str, int] = {}
    for rel, body in iter_inline_scripts():
        digest = base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
        hashes.add(digest)
        per_file[rel] = per_file.get(rel, 0) + 1
    if not HEADERS.is_file():
        print(f"ERROR: {HEADERS} missing", file=sys.stderr)
        return 1
    text = HEADERS.read_text(encoding="utf-8", errors="ignore")
    m = CSP_RE.search(text)
    if not m:
        print("ERROR: expected exactly one enforcing Content-Security-Policy line", file=sys.stderr)
        return 1

    policy = m.group(1)
    directives = [d.strip() for d in policy.split(";") if d.strip()]
    script_idx = next(
        (i for i, d in enumerate(directives) if d.split(" ")[0] == "script-src"), None
    )
    if script_idx is None:
        print("ERROR: no script-src directive in the enforcing policy", file=sys.stderr)
        return 1

    tokens = [
        t
        for t in HASH_RE.sub(" ", directives[script_idx]).split()
        if t and t != PLACEHOLDER
    ]
    directives[script_idx] = " ".join(tokens + [f"'sha256-{h}'" for h in sorted(hashes)])

    text = text[: m.start(1)] + "; ".join(directives) + text[m.end(1) :]
    stray = [
        n for n, line in enumerate(text.splitlines()) if line.startswith("#") and "sha256" in line
    ]
    if stray or PLACEHOLDER in text:
        print(f"ERROR: corrupt _headers after build (stray={stray})", file=sys.stderr)
        return 1
    HEADERS.write_text(text, encoding="utf-8")
    print(f"{len(hashes)} distinct hashes over {sum(per_file.values())} blocks")
    for f, n in sorted(per_file.items()):
        print(f"  {f}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
