import re, os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import markdown

REPO = Path(__file__).resolve().parent.parent
BLOG = REPO / "blog"
OUT = REPO / "verify_portal" / "static" / "blog"

def main():
    posts = []
    for f in sorted(os.listdir(str(BLOG / "posts")), reverse=True):
        if not f.endswith(".md"):
            continue
        text = open(str(BLOG / "posts" / f), encoding="utf-8").read()
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        fm = {}
        for line in parts[1].strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
        slug = f[:-3]
        body = markdown.markdown(parts[2].strip())
        posts.append({"slug": slug, "title": fm.get("title", "?"), "date": fm.get("date", ""), "description": fm.get("description", ""),
        "excerpt": fm.get("excerpt", parts[2][:100]), "content": body})
    env = Environment(loader=FileSystemLoader(str(BLOG / "templates")))
    os.makedirs(str(OUT / "posts"), exist_ok=True)
    for p in posts:
        html = env.get_template("post.html").render(p)
        open(str(OUT / "posts" / (p["slug"] + ".html")), "w", encoding="utf-8").write(html)
    open(str(OUT / "index.html"), "w", encoding="utf-8").write(env.get_template("listing.html").render(posts=posts))
    print("Built " + str(len(posts)) + " posts")

if __name__ == "__main__":
    main()
