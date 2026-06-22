import os, sys, subprocess
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

BLOG_DIR = Path(__file__).resolve().parent.parent / "blog"
BUILD_SCRIPT = BLOG_DIR.parent / "scripts" / "build_blog.py"

class BlogPost(BaseModel):
    title: str
    date: str = ""
    description: str = ""
    excerpt: str = ""
    body: str = ""
    secret: str = ""

router = APIRouter(prefix="/api/blog", tags=["blog"])
@router.post("/publish")
def publish_post(post: BlogPost):
    expected = os.environ.get("EPI_BLOG_SECRET", "")
    if not expected or post.secret != expected:
        raise HTTPException(403, "Invalid or missing blog secret")
    slug = "".join(c if c.isalnum() or c=="-" else "-" for c in post.title.lower()).strip("-")
    if not slug:
        raise HTTPException(400, "Title is required")
    md = f"---\ntitle: {post.title}\ndate: {post.date}\ndescription: {post.description}\nexcerpt: {post.excerpt}\n---\n\n{post.body}\n"
    posts_dir = BLOG_DIR / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    open(posts_dir / f"{slug}.md", "w", encoding="utf-8").write(md)
    result = subprocess.run([sys.executable, str(BUILD_SCRIPT)], capture_output=True, text=True)
    return {"ok": True, "slug": slug, "url": f"/blog/posts/{slug}.html", "build": result.stdout.strip()}
