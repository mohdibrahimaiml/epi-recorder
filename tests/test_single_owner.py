"""Single-owner enforcement: one behavior, one owner.

Regression net for a bug class that has bitten three times, each time as
N writers silently disagreeing about one shared thing:

- hamburger menu: the page inline script AND theme.js both toggled
  ``mmenu.open`` -- two toggles per tap cancel out, menu looked dead.
- AGT mapping report: the writer wrote ``content.agt_entry_id`` while the
  report claimed ``governance.agt_entry_id`` -- two sources of truth drifted.
- canonical dispatch: sign, signature-verify, and chain-verify each parsed
  ``spec_version`` differently -- one input, three preimages.

Rule: every shared behavior names exactly one owning location. Anything
else *calls* it. These tests fail when the ACTING construct (not prose
about it -- comments explaining ownership are fine) appears anywhere else.

Sibling coverage, deliberately not duplicated here:
- ``test_runtime_code_has_no_hardcoded_current_release_literal`` (versions)
- ``tests/integrations/agt_adapter/test_mapping_report_paths_resolve.py``
  (report claims vs writer behavior, both directions)
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class AbsentOutsideRule:
    """An acting construct that may appear ONLY in the allowed locations.

    Default-deny: any file under the scanned roots that matches and is not
    explicitly allowed fails. A new file introducing a second owner breaks
    the build instead of shipping a silent contradiction.
    """

    name: str
    why: str
    pattern: str
    roots: tuple
    extensions: tuple
    allowed: tuple  # fnmatch patterns, repo-root-relative, ** supported


@dataclass(frozen=True)
class PresentInRule:
    """A hardening that every listed mirror must contain.

    For behaviors that legitimately exist in several deploy targets
    (browser verifiers), the rule is not "one copy" but "no copy may lack
    it": each mirror must carry the fixed primitive.
    """

    name: str
    why: str
    pattern: str
    files: tuple  # repo-root-relative paths, each must match
ABSENT_OUTSIDE_RULES = (
    AbsentOutsideRule(
        name="menu-toggle",
        why=(
            "The mobile menu opens iff exactly one handler toggles "
            "mmenu.open per tap. A second handler (as theme.js once had) "
            "cancels the first and the hamburger looks dead."
        ),
        pattern=r"""mmenu\s*\.\s*classList\s*\.\s*toggle\s*\(\s*['"]open['"]""",
        roots=("website",),
        extensions=(".html", ".js"),
        allowed=("website/*.html", "website/*/index.html"),
    ),
    AbsentOutsideRule(
        name="version-dispatch",
        why=(
            "spec_version selects the signature preimage. Sign, verify, and "
            "chain-verify must use serialize.canonical_format_for -- a second "
            "inline parser once gave three answers for one input."
        ),
        pattern=r"""lstrip\(\s*['"]v['"]\s*\)""",
        roots=("epi_core", "epi_cli", "epi_recorder", "verify_portal"),
        extensions=(".py",),
        allowed=("epi_core/serialize.py",),
    ),
    AbsentOutsideRule(
        name="cutoff-comparison",
        why=(
            "The JCS introduction cutoff is a fact owned by _version.py and "
            "interpreted only by serialize.py. A second comparison site "
            "drifts the era boundary for old artifacts."
        ),
        pattern=r"""JCS_INTRODUCED_TUPLE""",
        roots=("epi_core", "epi_cli", "epi_recorder", "verify_portal"),
        extensions=(".py",),
        allowed=("epi_core/_version.py", "epi_core/serialize.py"),
    ),
)

PRESENT_IN_RULES = (
    PresentInRule(
        name="jcs-number-primitive",
        why=(
            "Every browser preimage must re-encode numbers per JCS "
            "(900.0 hashes as '900'). Raw preservation was the bug."
        ),
        pattern=r"""\bjcsNumberFromRaw\b|\b_jcsNumberFromRaw\b""",
        files=(
            "website/js/epi-manifest-preimage.js",
            "website/js/home-verify.js",
            "epi_viewer_static/crypto.js",
        ),
    ),
    PresentInRule(
        name="jcs-era-switch",
        why=(
            "Pre-JCS artifacts signed json.dumps float text ('900.0'), so "
            "each MANIFEST preimage must dispatch on spec_version era. "
            "home-verify.js is exempt: its own sortedJSON only hashes steps "
            "(always JCS); manifests delegate to epi-manifest-preimage.js."
        ),
        pattern=r"""\bisPreJcsSpec\b|\b_jcsNumbers\b|\b_epiJcsNumbers\b""",
        files=(
            "website/js/epi-manifest-preimage.js",
            "epi_viewer_static/crypto.js",
        ),
    ),
    PresentInRule(
        name="key-binding",
        why=(
            "Browser signature checks must bind key_name to the manifest "
            "public key (as trust.py does), or a relabeled key id verifies."
        ),
        pattern=r"""Key name does not match""",
        files=(
            "website/js/epi-manifest-preimage.js",
            "epi_viewer_static/crypto.js",
        ),
    ),
)


def _iter_files(roots, extensions):
    for root in roots:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix in extensions:
                yield path


def _matches_any(rel_posix, patterns):
    from pathlib import PurePath
    return any(
        PurePath(rel_posix).match(pat) or fnmatch.fnmatch(rel_posix, pat)
        for pat in patterns
    )


def test_single_owner_absent_outside():
    offenders = []
    for rule in ABSENT_OUTSIDE_RULES:
        rx = re.compile(rule.pattern)
        for path in _iter_files(rule.roots, rule.extensions):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if _matches_any(rel, rule.allowed):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if rx.search(text):
                offenders.append("[" + rule.name + "] " + rel)
    assert not offenders, (
        "Second owner of a single-owner behavior:\n"
        + "\n".join(offenders)
        + "\nOne behavior, one owner -- call it, don't reimplement it."
    )


def test_single_owner_present_in_mirrors():
    missing = []
    for rule in PRESENT_IN_RULES:
        rx = re.compile(rule.pattern)
        for rel in rule.files:
            path = REPO_ROOT / rel
            assert path.exists(), "[" + rule.name + "] mirror missing: " + rel
            text = path.read_text(encoding="utf-8")
            if not rx.search(text):
                missing.append("[" + rule.name + "] " + rel)
    assert not missing, (
        "Browser mirror lacking a required hardening:\n" + "\n".join(missing)
    )