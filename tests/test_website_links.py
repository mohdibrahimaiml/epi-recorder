"""WP-FIX-1: no dead links or missing assets on the site.

Parses every href/src in website/**/*.html and requires:
  - internal targets exist (honouring _redirects exact rules and pretty URLs:
    /foo -> foo.html, /foo/ -> foo/index.html, /foo.html direct);
  - /api/*, /scitt/*, /.well-known/* resolve to Functions routes or files;
  - github.com blob/main/... links point at paths that exist in this repo.
External links (other hosts, mailto:, fragments) are out of scope.
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]
WEBSITE = REPO / "website"
GITHUB_BLOB = "https://github.com/mohdibrahimaiml/epi-recorder/blob/"

HREF_RE = re.compile(r'''(?:href|src)\s*=\s*"([^"]+)"|(?:href|src)\s*=\s*'([^']+)' ''')


def _redirects() -> dict[str, str]:
    rules: dict[str, str] = {}
    text = (WEBSITE / "_redirects").read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and "*" not in parts[0]:
            rules[parts[0]] = parts[1]
    return rules


def _functions_route(path: str) -> bool:
    # /api/a/b -> functions/api/[[path]].js ; same for /scitt, /.well-known.
    for base in ("api", "scitt", ".well-known"):
        if path == f"/{base}" or path.startswith(f"/{base}/"):
            return (REPO / "functions" / base / "[[path]].js").is_file()
    return False


def _internal_exists(url_path: str, redirects: dict[str, str]) -> bool:
    if url_path in redirects:
        target = redirects[url_path]
        if target.startswith("http"):
            return True
        url_path = target
    if _functions_route(url_path):
        return True
    candidates = [WEBSITE / url_path.lstrip("/")]
    stripped = url_path.rstrip("/")
    candidates.append(WEBSITE / stripped.lstrip("/") )
    candidates.append(WEBSITE / (stripped.lstrip("/") + ".html"))
    candidates.append(WEBSITE / stripped.lstrip("/") / "index.html")
    return any(c.is_file() for c in candidates)


def _targets_in(path: pathlib.Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    for m in HREF_RE.finditer(text):
        yield m.group(1) if m.group(1) is not None else m.group(2)


def test_no_dead_internal_links_or_assets():
    redirects = _redirects()
    dead: list[str] = []
    pages = sorted(WEBSITE.rglob("*.html"))
    assert pages, "no pages found"
    for page in pages:
        rel = page.relative_to(WEBSITE).as_posix()
        for raw in _targets_in(page):
            if not raw or raw.startswith(
                ("mailto:", "tel:", "javascript:", "data:", "#")
            ):
                continue
            if raw.startswith(("http://", "https://", "//")):
                if raw.startswith(GITHUB_BLOB):
                    rest = raw[len(GITHUB_BLOB):]
                    branch, _, repo_path = rest.partition("/")
                    candidate = REPO / repo_path.split("#")[0].split("?")[0]
                    if not candidate.exists():
                        dead.append(f"{rel}: {raw}")
                continue
            url_path = raw.split("#")[0].split("?")[0]
            if not url_path:
                continue
            if not _internal_exists(url_path, redirects):
                dead.append(f"{rel}: {raw}")
    assert not dead, "dead links or missing assets:\n" + "\n".join(sorted(set(dead)))
