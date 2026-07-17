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
    # Cloudflare rejects absolute external proxy (200) redirects
    for rule in rules:
        parts = rule.split()
        if len(parts) >= 3 and parts[-1] == "200" and parts[1].startswith("https://"):
            pytest.fail(
                f"Cloudflare rejects absolute proxy 200 rules: {rule!r}. "
                "Use functions/ API proxy instead."
            )


def test_cloudflare_functions_proxy_api():
    """API proxy must live in Pages Functions, not Netlify-style _redirects."""
    assert (ROOT / "functions" / "api" / "[[path]].js").is_file()
    assert (ROOT / "functions" / "scitt" / "[[path]].js").is_file()
    assert (ROOT / "functions" / "_proxy.js").is_file()
    proxy = (ROOT / "functions" / "_proxy.js").read_text(encoding="utf-8")
    assert "epi-verify-portal.onrender.com" in proxy


def test_account_auth_entrypoints():
    text = (ROOT / "website" / "account.html").read_text(encoding="utf-8")
    # Fallback Render URL and/or same-origin API_BASE helper
    assert "epi-verify-portal.onrender.com" in text or "API_BASE" in text
    assert "startLogin" in text
    assert "logout" in text
    assert "establishSession" in text or "/api/auth" in text


def test_site_mirror_exists_for_cloudflare():
    """Cloudflare Pages output directory is configured as site/."""
    site = ROOT / "site"
    assert (site / "index.html").is_file()
    assert (site / "account.html").is_file()


def test_sync_website_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Run sync against real tree — should not raise
    import importlib.util

    script = ROOT / "scripts" / "sync_website.py"
    spec = importlib.util.spec_from_file_location("sync_website", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.sync()
    # After sync, static + site account match website
    web = (ROOT / "website" / "account.html").read_bytes()
    static = (ROOT / "verify_portal" / "static" / "account.html").read_bytes()
    site = (ROOT / "site" / "account.html").read_bytes()
    assert web == static
    assert web == site
