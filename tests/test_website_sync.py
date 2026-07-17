"""Ensure website/ is the single source of truth and sync works."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_website_source_exists():
    website = ROOT / "website"
    assert (website / "index.html").is_file()
    assert (website / "account.html").is_file()
    assert (website / "CNAME").is_file()
    assert (website / "_redirects").is_file()
    assert (website / ".nojekyll").is_file()


def test_redirects_have_no_html_pretty_url_rewrites():
    text = (ROOT / "website" / "_redirects").read_text(encoding="utf-8")
    # Only active rules (non-comment lines)
    rules = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    joined = "\n".join(rules)
    # These rules cause Cloudflare infinite 308 loops
    assert "/account /account.html" not in joined
    assert "/pricing /pricing.html" not in joined
    assert "/* /index.html 200" not in joined
    assert any(r.startswith("/api/*") for r in rules)


def test_account_points_at_render_api():
    text = (ROOT / "website" / "account.html").read_text(encoding="utf-8")
    assert "epi-verify-portal.onrender.com" in text
    assert "startLogin" in text
    assert "logout" in text


def test_sync_website_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Run sync against real tree — should not raise
    import importlib.util

    script = ROOT / "scripts" / "sync_website.py"
    spec = importlib.util.spec_from_file_location("sync_website", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.sync()
    # After sync, static account matches website
    web = (ROOT / "website" / "account.html").read_bytes()
    static = (ROOT / "verify_portal" / "static" / "account.html").read_bytes()
    assert web == static
