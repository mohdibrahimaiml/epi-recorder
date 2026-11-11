#!/usr/bin/env python3
"""Build the public blog for the site and the legacy portal.

Canonical output: ``website/blog/`` (index.html + posts/<slug>.html). That is
copied to the Cloudflare Pages output and to every sync target by
``scripts/sync_website.py``. The previous output, ``verify_portal/static/blog``,
is still written so the legacy portal keeps working.

``scripts/cf-pages-build.mjs`` runs this before copying ``website/``, so the
blog is generated on every deploy. It deliberately uses only the Python
standard library: the Cloudflare build image has Python but not the optional
``jinja2``/``markdown`` packages that the first version of this script needed.

Templates live in ``blog/templates/`` and use ``{{ name }}`` placeholders.
"""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BLOG = REPO / "blog"
WEBSITE = REPO / "website"
OUTPUTS = [WEBSITE / "blog", REPO / "verify_portal" / "static" / "blog"]

SITE = "https://epilabs.org"
DEFAULT_IMAGE = f"{SITE}/assets/epi-walkthrough-og.jpg"

DATE_FORMATS = ("%B %d, %Y", "%B %Y", "%d %B %Y", "%Y-%m-%d")


def _version() -> str:
    try:
        import tomllib

        with (REPO / "pyproject.toml").open("rb") as handle:
            return str(tomllib.load(handle)["project"]["version"])
    except Exception:
        return ""


def _parse_date(value: str) -> tuple[str, datetime]:
    text = (value or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return text, datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return text, datetime.min.replace(tzinfo=UTC)


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict[str, str] = {}
    for index in range(1, len(lines)):
        line = lines[index]
        if line.strip() == "---":
            return meta, "\n".join(lines[index + 1 :])
        if ":" in line:
            key, value = line.split(":", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            meta[key.strip()] = value
    return {}, text


def _inline(text: str) -> str:
    text = html.escape(text, quote=False)

    codes: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        codes.append(match.group(1))
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", _stash, text)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    for index, code in enumerate(codes):
        text = text.replace(f"\x00{index}\x00", f'<code class="k">{code}</code>')
    return text


def _is_block_start(line: str) -> bool:
    return bool(
        re.match(r"^(#{1,6})\s+", line)
        or line.startswith("```")
        or line.startswith("> ")
        or re.match(r"^[-*]\s+", line)
        or re.match(r"^\d+\.\s+", line)
    )


def markdown_to_html(text: str) -> str:
    """Small, deterministic Markdown subset used by the posts.

    Headings, paragraphs, ordered/unordered lists, blockquotes, fenced code
    and inline code/bold/italic/links. No raw HTML passthrough.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    index = 0
    first_heading_skipped = False

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        fence = re.match(r"^```\s*([\w+-]*)", line)
        if fence:
            language = fence.group(1)
            index += 1
            body: list[str] = []
            while index < len(lines) and not lines[index].startswith("```"):
                body.append(lines[index])
                index += 1
            index += 1
            css = f' class="language-{html.escape(language)}"' if language else ""
            out.append(f"<pre><code{css}>{html.escape(chr(10).join(body))}</code></pre>")
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            if level == 1 and not first_heading_skipped:
                first_heading_skipped = True
                index += 1
                continue
            first_heading_skipped = True
            out.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
            index += 1
            continue

        if line.startswith("> "):
            body = []
            while index < len(lines) and lines[index].startswith("> "):
                body.append(lines[index][2:].strip())
                index += 1
            out.append(f"<blockquote><p>{_inline(' '.join(body))}</p></blockquote>")
            continue

        unordered = re.match(r"^[-*]\s+(.*)$", line)
        if unordered:
            items = []
            while index < len(lines):
                match = re.match(r"^[-*]\s+(.*)$", lines[index])
                if not match:
                    break
                items.append(f"<li>{_inline(match.group(1).strip())}</li>")
                index += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        ordered = re.match(r"^\d+\.\s+(.*)$", line)
        if ordered:
            items = []
            while index < len(lines):
                match = re.match(r"^\d+\.\s+(.*)$", lines[index])
                if not match:
                    break
                items.append(f"<li>{_inline(match.group(1).strip())}</li>")
                index += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue

        paragraph = [line.strip()]
        index += 1
        while index < len(lines):
            candidate = lines[index]
            if not candidate.strip() or _is_block_start(candidate):
                break
            paragraph.append(candidate.strip())
            index += 1
        out.append(f"<p>{_inline(' '.join(paragraph))}</p>")

    return "\n".join(out)


def _render(template: str, values: dict[str, str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return values.get(key, match.group(0))

    return re.sub(r"\{\{\s*([\w_]+)\s*\}\}", _replace, template)


def _load_template(name: str) -> str:
    return (BLOG / "templates" / name).read_text(encoding="utf-8")


def _nav() -> str:
    try:
        return (WEBSITE / "_nav.html").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _footer() -> str:
    version = _version()
    stamp = f"v{version}" if version else ""
    return f"""<footer style="border-top:1px solid var(--line);padding:44px 0;background:var(--bg)">
  <div class="wrap fbot" style="border:0;padding-top:0">
    <span>&copy; 2026 EPI LABS &middot; MIT License &middot; {stamp}</span>
    <span>
      <a href="/" style="color:var(--acc)">epilabs.org</a> &middot;
      <a href="https://github.com/mohdibrahimaiml/epi-recorder"
         target="_blank" rel="noopener"
         style="color:var(--mut)">GitHub</a>
    </span>
  </div>
<p style="text-align:center;font-size:0.75rem;margin:1rem 0 0;opacity:0.8">
  <a href="/about" style="color:inherit">About</a> &middot;
  <a href="/privacy" style="color:inherit">Privacy</a> &middot;
  <a href="/terms" style="color:inherit">Terms</a> &middot;
  <a href="mailto:mohdibrahim@epilabs.org" style="color:inherit">mohdibrahim@epilabs.org</a>
</p>
</footer>"""


def _load_posts() -> list[dict[str, str]]:
    posts: list[dict[str, str]] = []
    for path in sorted((BLOG / "posts").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta, body = _split_front_matter(text)
        display_date, parsed = _parse_date(meta.get("date", ""))
        slug = path.stem
        posts.append(
            {
                "slug": slug,
                "title": meta.get("title", slug.replace("-", " ").title()),
                "date": display_date,
                "date_iso": parsed.date().isoformat() if parsed.year > 1 else "",
                "description": meta.get("description", ""),
                "excerpt": meta.get("excerpt", ""),
                "content": markdown_to_html(body),
                "_sort": parsed.timestamp(),
            }
        )
    posts.sort(key=lambda item: item["_sort"], reverse=True)
    return posts


def _card(post: dict[str, str]) -> str:
    return f"""<article class="blog-card">
  <time class="blog-date" datetime="{html.escape(post['date_iso'])}">
    {html.escape(post['date'])}
  </time>
  <h2>
    <a href="/blog/posts/{html.escape(post['slug'])}.html">{html.escape(post['title'])}</a>
  </h2>
  <p>{html.escape(post['excerpt'] or post['description'])}</p>
  <a class="blog-more" href="/blog/posts/{html.escape(post['slug'])}.html">
    Read the article &rarr;
  </a>
</article>"""


def _json_ld(post: dict[str, str]) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post["title"],
        "description": post["description"] or post["excerpt"],
        "datePublished": post["date_iso"],
        "dateModified": post["date_iso"],
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": f"{SITE}/blog/posts/{post['slug']}.html",
        },
        "image": [DEFAULT_IMAGE],
        "author": {"@type": "Organization", "name": "EPI Labs", "url": SITE},
        "publisher": {
            "@type": "Organization",
            "name": "EPI Labs",
            "url": SITE,
            "logo": {"@type": "ImageObject", "url": f"{SITE}/assets/logo.png"},
        },
    }
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def build() -> int:
    posts = _load_posts()
    nav = _nav()
    footer = _footer()
    listing = _load_template("listing.html")
    post_template = _load_template("post.html")

    shared = {"nav": nav, "footer": footer}
    listing_html = _render(
        listing,
        {
            **shared,
            "cards": "\n".join(_card(post) for post in posts),
        },
    )

    rendered_posts: list[tuple[str, str]] = []
    for post in posts:
        canonical = f"{SITE}/blog/posts/{post['slug']}.html"
        page = _render(
            post_template,
            {
                **shared,
                "title": html.escape(post["title"]),
                "description": html.escape(post["description"] or post["excerpt"]),
                "canonical": canonical,
                "date": html.escape(post["date"]),
                "date_iso": post["date_iso"],
                "image": DEFAULT_IMAGE,
                "json_ld": _json_ld(post),
                "content": post["content"],
            },
        )
        rendered_posts.append((post["slug"], page))

    for output in OUTPUTS:
        (output / "posts").mkdir(parents=True, exist_ok=True)
        (output / "index.html").write_text(listing_html, encoding="utf-8")
        for slug, page in rendered_posts:
            (output / "posts" / f"{slug}.html").write_text(page, encoding="utf-8")

    print(f"Built {len(posts)} posts -> {', '.join(str(o.relative_to(REPO)) for o in OUTPUTS)}")
    return len(posts)


if __name__ == "__main__":
    build()
