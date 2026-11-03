"""The site sells one thing, at a price, without the earlier overclaims."""

from __future__ import annotations

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SITE = REPO / "website"
PRICE = "\u20ac4,500"
FULL = "\u20ac9,500"
STANDARD = "\u20ac15,000"


def _pyproject_version() -> str:
    import tomllib

    with (REPO / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def _html(name: str) -> str:
    return (SITE / name).read_text(encoding="utf-8")


def _all_html() -> dict[str, str]:
    return {
        str(path.relative_to(SITE)): path.read_text(encoding="utf-8", errors="ignore")
        for path in SITE.rglob("*.html")
    }


def test_design_partner_is_gone_everywhere():
    offenders = [name for name, text in _all_html().items() if "Design Partner" in text]
    assert not offenders, offenders


def test_insurability_claim_is_gone():
    offenders = [
        name
        for name, text in _all_html().items()
        if "insurability" in text.lower() or "insurable" in text.lower()
    ]
    assert not offenders, offenders


def test_there_is_one_paid_offer_and_it_has_a_price():
    index = _html("index.html")
    plans = _html("plans.html")
    assert "AI vendor review" in index and PRICE in index
    assert "AI vendor review" in plans and PRICE in plans
    assert FULL in plans and STANDARD in plans
    assert "one workflow" in plans.lower()
    assert "your customer keeps their own witness log" in plans.lower()
    assert "first 3 customers" in plans.lower()


def test_the_three_offers_are_distinct():
    plans = _html("plans.html")
    for name in ("Open Source", "EPI Cloud", "AI vendor review"):
        assert name in plans, name
    # Open Source is complete, not a trial; Cloud is optional; the engagement is a service.
    assert "not a trial" in plans.lower()
    assert "Not required to record or verify" in plans
    assert "A service, not software access" in plans
    assert "Verification" in plans
    # The at-a-glance table must state the price of each layer.
    assert "€0 forever" in plans
    assert "€4,500 assessment" in plans


def test_the_footer_shows_the_version_once():
    index = _html("index.html")
    footer = index[index.rindex("<footer"): index.rindex("</footer>")]
    version = _pyproject_version()
    assert footer.count(f"v{version}") == 1, footer.count(f"v{version}")


def test_standards_moved_to_its_own_page_linked_from_the_footer():
    index = _html("index.html")
    assert "Annex IV" not in index and "AIUC-1" not in index
    standards = _html("standards.html")
    assert "Annex IV" in standards and "AIUC-1" in standards
    footer = index[index.rindex("<footer"): index.rindex("</footer>")]
    assert 'href="/standards"' in footer
    assert (SITE / "sitemap.xml").read_text(encoding="utf-8").count("/standards") == 1


def _js_list(script: str, name: str) -> list[str]:
    match = re.search(rf"const {name} = \[(.*?)\];", script, re.S)
    assert match, f"{name} missing from scripts/cf-pages-build.mjs"
    return re.findall(r'"([^"]+)"', match.group(1))


def test_the_pages_build_checks_the_offer_that_actually_exists():
    """The build guard must test for the page we ship, not a retired one."""
    script = (REPO / "scripts" / "cf-pages-build.mjs").read_text(encoding="utf-8")
    plans = _html("plans.html")
    for needle in _js_list(script, "PLANS_PAGE_REQUIRED"):
        assert needle in plans, f"cf-pages-build.mjs requires {needle!r}, plans.html lacks it"
    for needle in _js_list(script, "PLANS_PAGE_RETIRED"):
        assert needle not in plans, f"cf-pages-build.mjs still expects retired {needle!r}"


def test_the_mirrors_serve_the_same_pages():
    for mirror in ("site", "epi-official"):
        for name in ("index.html", "plans.html", "standards.html"):
            source = (SITE / name).read_bytes()
            served = (REPO / mirror / name).read_bytes()
            assert served == source, f"{mirror}/{name} differs from website/{name}"
