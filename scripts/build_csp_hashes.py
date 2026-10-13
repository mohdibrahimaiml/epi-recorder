#!/usr/bin/env python3
"""Build the script-src hash list for website/_headers (WP-SEC-3).

Every executable inline <script> block (no src=) is hashed over its exact
served bytes; the hashes replace the __SCRIPT_SRC_HASHES__ placeholder in
the Content-Security-Policy line of website/_headers (single line — header
continuation lines cannot hold comments). Mirrors pick the file up via
scripts/sync_website.py; Cloudflare Pages serves it as HTTP headers.

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
    replacement = " ".join(f"'sha256-{h}'" for h in sorted(hashes))
    lines = text.splitlines(keepends=True)
    csp_idx = [i for i, l in enumerate(lines) if "Content-Security-Policy-Report-Only" in l]
    if len(csp_idx) != 1:
        print("ERROR: expected exactly one Report-Only CSP line", file=sys.stderr)
        return 1
    i = csp_idx[0]
    if PLACEHOLDER in lines[i]:
        lines[i] = lines[i].replace(PLACEHOLDER, replacement)
    else:
        # Re-run: refresh ONLY the hash run inside the CSP line. Never touch
        # anything else (a naive whole-file split once scattered hashes into
        # a comment — see WP-SEC-3 notes).
        lines[i] = re.sub(r"'sha256-[A-Za-z0-9+/=]+' ?", "", lines[i]).replace(
            "  ", " "
        )
        anchor = "https://public.profitwell.com"
        assert anchor in lines[i], "script-src anchor missing"
        lines[i] = lines[i].replace(anchor, anchor + " " + replacement, 1)
    text = "".join(lines)
    stray = [
        n for n, l in enumerate(text.splitlines()) if l.startswith("#") and "sha256" in l
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
