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


def test_sync_never_ships_internal_markdown():
    """Internal *.md (e.g. outreach.md sales templates) must never reach public outputs.

    Plants a website/outreach.md source plus stale outreach.md copies in every
    target, runs the real sync, and asserts none survive — while the public
    website/README.md still syncs through.
    """
    import importlib.util

    script = ROOT / "scripts" / "sync_website.py"
    spec = importlib.util.spec_from_file_location("sync_website_internal_md", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    planted_source = ROOT / "website" / "outreach.md"
    planted_generic = ROOT / "website" / "INTERNAL_TEST_NOTE.md"
    planted_targets = [
        ROOT / "site" / "outreach.md",
        ROOT / "verify_portal" / "static" / "outreach.md",
        ROOT / "epi-official" / "outreach.md",
    ]
    planted_source.write_text("# internal sales templates (test fixture)\n", encoding="utf-8")
    planted_generic.write_text("# internal note (test fixture)\n", encoding="utf-8")
    for p in planted_targets:
        p.write_text("# stale copy (test fixture)\n", encoding="utf-8")
    try:
        mod.sync()
        for p in planted_targets:
            assert not p.exists(), f"internal file shipped to public output: {p}"
        assert not (ROOT / "site" / "INTERNAL_TEST_NOTE.md").exists()
        assert not (ROOT / "verify_portal" / "static" / "INTERNAL_TEST_NOTE.md").exists()
        assert not (ROOT / "epi-official" / "INTERNAL_TEST_NOTE.md").exists()
    finally:
        planted_source.unlink(missing_ok=True)
        planted_generic.unlink(missing_ok=True)
        for p in planted_targets:
            p.unlink(missing_ok=True)
        (ROOT / "site" / "INTERNAL_TEST_NOTE.md").unlink(missing_ok=True)
        (ROOT / "verify_portal" / "static" / "INTERNAL_TEST_NOTE.md").unlink(missing_ok=True)
        (ROOT / "epi-official" / "INTERNAL_TEST_NOTE.md").unlink(missing_ok=True)
    # The public README.md must still sync through.
    assert (ROOT / "site" / "README.md").is_file()


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
