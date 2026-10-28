"""Ensure website/ is the single source of truth and sync works.

The two tests that *run* the sync must operate on an isolated copy of the tree:
`sync_website.sync()` copies into the real deploy targets (site/, epi-official/,
verify_portal/static/), which used to leave tracked files modified after a test
run. Everything here now works under tmp_path.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _isolated_sync_module(tmp_path: Path):
    """Load sync_website.py and point its ROOT/SOURCE/TARGETS at tmp_path."""
    import importlib.util

    script = ROOT / "scripts" / "sync_website.py"
    spec = importlib.util.spec_from_file_location("sync_website_isolated", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    source = tmp_path / "website"
    shutil.copytree(ROOT / "website", source)

    mod.ROOT = tmp_path
    mod.SOURCE = source
    mod.TARGETS = [
        tmp_path / "verify_portal" / "static",
        tmp_path / "epi-official",
        tmp_path / "site",
    ]
    return mod, source


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
    # Single account system: website Sign In points to EPI Cloud, no Render login.
    assert "cloud.epilabs.org" in text
    assert "epi-verify-portal.onrender.com" not in text
    assert "/api/auth" not in text


def test_site_mirror_exists_for_cloudflare():
    """Cloudflare Pages output directory is configured as site/."""
    site = ROOT / "site"
    assert (site / "index.html").is_file()
    assert (site / "account.html").is_file()


def test_sync_never_ships_internal_markdown(tmp_path: Path):
    """Internal *.md (e.g. outreach.md sales templates) must never reach public outputs.

    Plants a website/outreach.md source plus stale outreach.md copies in every
    target, runs the real sync against an isolated tree, and asserts none
    survive — while the public website/README.md still syncs through.
    """
    mod, source = _isolated_sync_module(tmp_path)
    targets = mod.TARGETS

    (source / "outreach.md").write_text("# internal sales templates (test fixture)\n", encoding="utf-8")
    (source / "INTERNAL_TEST_NOTE.md").write_text("# internal note (test fixture)\n", encoding="utf-8")
    for target in targets:
        target.mkdir(parents=True, exist_ok=True)
        (target / "outreach.md").write_text("# stale copy (test fixture)\n", encoding="utf-8")

    mod.sync()

    for target in targets:
        assert not (target / "outreach.md").exists(), f"internal file shipped to {target}"
        assert not (target / "INTERNAL_TEST_NOTE.md").exists(), f"internal note shipped to {target}"
    # The public README.md must still sync through.
    assert (tmp_path / "site" / "README.md").is_file()


def test_sync_website_script(tmp_path: Path):
    mod, source = _isolated_sync_module(tmp_path)
    mod.sync()

    web = (source / "account.html").read_bytes()
    assert web == (tmp_path / "verify_portal" / "static" / "account.html").read_bytes()
    assert web == (tmp_path / "site" / "account.html").read_bytes()
