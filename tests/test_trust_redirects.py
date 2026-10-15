"""Redirect precedence: /t/acme-demo/ and its assets must never rewrite to /t/app/.

Cloudflare Pages evaluates website/_redirects top-down, first match wins,
and rewrites beat static files. If the /t/* splat ever moves above the demo
identity rules, the demo page silently becomes the real trust shell.
"""
from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]


def _rules():
    rules = []
    for line in (REPO / "website" / "_redirects").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            rules.append((parts[0], parts[1]))
    return rules


def _apply(rules, path: str) -> str:
    for source, target in rules:
        if source.endswith("/*"):
            prefix = source[:-1]
            if path == prefix.rstrip("/") or path.startswith(prefix):
                splat = path[len(prefix):] if path.startswith(prefix) else ""
                return target.replace(":splat", splat)
        elif path == source:
            return target
    return path


def test_demo_beats_splat():
    rules = _rules()
    assert _apply(rules, "/t/acme-demo/") == "/t/acme-demo/"
    assert _apply(rules, "/t/acme-demo/demo.js") == "/t/acme-demo/demo.js"
    assert _apply(rules, "/t/acme-demo/demo-data.json") == "/t/acme-demo/demo-data.json"
    assert _apply(rules, "/t/app.js") == "/t/app.js"


def test_real_slugs_rewrite_to_shell():
    rules = _rules()
    assert _apply(rules, "/t/sh_abc123") == "/t/app/"
    assert _apply(rules, "/t/app/") == "/t/app/"
