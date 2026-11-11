"""The blog must be a real page on epilabs.org, not only in the old portal."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"
BLOG = WEBSITE / "blog"
POSTS = ROOT / "blog" / "posts"


def _slugs() -> list[str]:
    return sorted(path.stem for path in POSTS.glob("*.md"))


def test_blog_is_generated_into_the_site_source():
    assert (BLOG / "index.html").is_file(), "run python scripts/build_blog.py"
    index = (BLOG / "index.html").read_text(encoding="utf-8")
    for slug in _slugs():
        assert f"/blog/posts/{slug}.html" in index, slug
        assert (BLOG / "posts" / f"{slug}.html").is_file(), slug


def test_every_post_carries_search_and_social_metadata():
    for slug in _slugs():
        page = (BLOG / "posts" / f"{slug}.html").read_text(encoding="utf-8")
        assert "<title>" in page
        assert 'rel="canonical"' in page
        assert 'property="og:title"' in page
        assert 'property="og:image"' in page
        assert 'name="twitter:card"' in page
        assert len(re.findall(r"<h1[ >]", page)) == 1, slug
        match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', page, re.S
        )
        assert match, slug
        data = json.loads(match.group(1))
        assert data["@type"] == "Article"
        assert data["headline"]


def test_blog_is_in_the_sitemap_and_nav():
    sitemap = (WEBSITE / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://epilabs.org/blog/" in sitemap
    for slug in _slugs():
        assert f"https://epilabs.org/blog/posts/{slug}.html" in sitemap
    nav = (WEBSITE / "_nav.html").read_text(encoding="utf-8")
    assert nav.count('href="/blog/"') == 2, "desktop and mobile nav need Blog"


def test_cloudflare_build_regenerates_the_blog():
    build = (ROOT / "scripts" / "cf-pages-build.mjs").read_text(encoding="utf-8")
    assert "scripts/build_blog.py" in build
    assert '"blog"' in build and "index.html" in build


def test_blog_builder_needs_no_extra_packages():
    source = (ROOT / "scripts" / "build_blog.py").read_text(encoding="utf-8")
    assert "import jinja2" not in source
    assert "import markdown" not in source
