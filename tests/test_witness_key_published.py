"""The witness key must read the same in every place a reviewer can check it."""

from __future__ import annotations

import json
from pathlib import Path

from epi_core.witness_keys import pinned_witness_pubkeys

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "website"


def test_site_copy_matches_the_package_pin() -> None:
    doc = json.loads((SITE / ".well-known" / "epi-witness-key.json").read_text(encoding="utf-8"))
    assert doc["witness_ed25519_pub_hex"] in pinned_witness_pubkeys()


def test_trust_page_shows_the_same_key_and_where_to_check() -> None:
    page = (SITE / "trust.html").read_text(encoding="utf-8")
    assert 'id="witness-key"' in page
    for key in pinned_witness_pubkeys():
        assert key in page
    assert "cloud.epilabs.org/.well-known/epi-witness-key.json" in page
    assert "/.well-known/epi-witness-key.json" in page


def test_trust_page_names_the_first_release_that_pins_the_key() -> None:
    # Releases before 4.6.2 do not contain the witness key; do not claim "every release".
    page = (SITE / "trust.html").read_text(encoding="utf-8")
    assert "pinned in every epi-recorder release since 4.6.2" in page
