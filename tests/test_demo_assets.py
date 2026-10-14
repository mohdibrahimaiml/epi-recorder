"""WP-DEMO-REFRESH item 2d: every .epi shipped under website/ is sealed by
the current release (spec_version == pyproject version), so the site never
again advertises one version while its samples say another. New .epi files
sealed from now on carry the current version automatically (get_version)."""

from __future__ import annotations

import json
import tomllib
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _version() -> str:
    with (REPO / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def test_website_epis_match_current_spec():
    version = _version()
    files = sorted((REPO / "website").rglob("*.epi"))
    assert files, "no shipped .epi files found"
    stale = []
    for f in files:
        with zipfile.ZipFile(f) as z:
            manifest = json.loads(z.read("manifest.json"))
        if manifest.get("spec_version") != version:
            stale.append(f"{f.relative_to(REPO)}: spec={manifest.get('spec_version')}")
    assert not stale, (
        f"shipped samples older than {version} (re-seal with the current release):\n"
        + "\n".join(stale)
    )


def test_demo_goals_marked_simulated():
    unmarked = []
    for f in sorted((REPO / "website" / "assets" / "demo").glob("demo-*.epi")):
        with zipfile.ZipFile(f) as z:
            manifest = json.loads(z.read("manifest.json"))
        text = f"{manifest.get('goal') or ''} {manifest.get('notes') or ''}"
        if "SIMULATED" not in text:
            unmarked.append(f.name)
    # website sample.epi is a functional sample (says UNVERIFIED itself).
    assert not unmarked, f"demo files without SIMULATED marking: {unmarked}"


def test_no_duplicate_refund_demo():
    assert not (REPO / "website" / "assets" / "demo" / "demo_refund_site.epi").exists()


def test_refund_demo_has_goal():
    with zipfile.ZipFile(REPO / "website" / "assets" / "demo" / "demo_refund.epi") as z:
        manifest = json.loads(z.read("manifest.json"))
    assert (manifest.get("goal") or "").strip(), "demo_refund needs a goal/title"
