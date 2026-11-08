"""Ensure only website/js/epi-verify-core.js is the source of truth.

Six copies diverged (js/, website/js/, site/js/, verify_portal/static/js/,
epi-official/js/, website-v2/js/) with different crypto implementations.
This test fails if any epi-verify-core.js in the repo differs from
website/js/epi-verify-core.js after CRLF normalization.

Canonical source: website/js/epi-verify-core.js (GitHub Pages deploys website/ only).
Other trees are generated mirrors via scripts/sync_website.py and must not be
hand-maintained duplicates.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "website" / "js" / "epi-verify-core.js"

# Paths that were previously hand-copied duplicates and are now deleted/generated.
# If any of these reappear, they must byte-match the canonical file.
LEGACY_COPIES = [
    ROOT / "js" / "epi-verify-core.js",
    ROOT / "site" / "js" / "epi-verify-core.js",
    ROOT / "verify_portal" / "static" / "js" / "epi-verify-core.js",
    ROOT / "epi-official" / "js" / "epi-verify-core.js",
    ROOT / "website-v2" / "js" / "epi-verify-core.js",
]


def _norm(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def test_canonical_exists():
    assert CANONICAL.is_file(), f"canonical verifier missing: {CANONICAL}"


def test_embedded_viewer_matches_canonical_logic():
    """The pack-time embedded viewer (epi_viewer_static/crypto.js) must contain the same fix as the canonical site verifier.

    This is the seventh copy that was missed: baked into every .epi at seal time via
    epi_core/viewer_assets.py. If it diverges, double-click (file://) shows INVALID while
    website/js shows valid — the product thesis break.
    """
    embedded = ROOT / "epi_viewer_static" / "crypto.js"
    assert embedded.is_file(), f"embedded viewer missing: {embedded}"
    canon_text = CANONICAL.read_text(encoding="utf-8", errors="ignore")
    emb_text = embedded.read_text(encoding="utf-8", errors="ignore")
    for marker in ("isPreJcsSpec", "prepareManifestCopy", "content_truncated", "policy_load_status"):
        assert marker in canon_text, f"canonical missing {marker} — fix not deployed to site"
        assert marker in emb_text, f"embedded crypto.js missing {marker} — patch epi_viewer_static/crypto.js from website/js/epi-verify-core.js"


def test_no_divergent_copies():
    assert CANONICAL.is_file(), "canonical missing"
    canon_norm = _norm(CANONICAL.read_bytes())
    canon_hash = hashlib.sha256(canon_norm).hexdigest()

    # Check legacy copies if they exist on disk (they should not, but if they do they must match)
    for p in LEGACY_COPIES:
        if not p.is_file():
            continue
        h = hashlib.sha256(_norm(p.read_bytes())).hexdigest()
        assert h == canon_hash, (
            f"{p.relative_to(ROOT)} differs from {CANONICAL.relative_to(ROOT)} "
            f"(after CRLF normalization). Run: python scripts/sync_website.py "
            f"or delete the duplicate and use website/js/ as single source. "
            f"canonical={canon_hash[:12]} copy={h[:12]}"
        )

    # Also walk the whole repo for any stray epi-verify-core.js not in the allowlist
    found = []
    for path in ROOT.rglob("epi-verify-core.js"):
        # ignore hidden/venv/build dirs
        parts = {part for part in path.relative_to(ROOT).parts}
        if any(x in parts for x in {".git", ".venv", ".venv-311-test", "node_modules", "__pycache__", ".pytest_cache", "htmlcov", "dist", "dist-test", "dist-verifier"}):
            continue
        if path == CANONICAL:
            continue
        if path in LEGACY_COPIES:
            continue
        found.append(path)
    assert not found, (
        f"Unexpected epi-verify-core.js copies found (should not exist outside website/js/): {found}. "
        "Keep website/js/epi-verify-core.js as single source; generate others via scripts/sync_website.py"
    )
