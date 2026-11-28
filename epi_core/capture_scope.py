"""Declared capture scope — what the application said it intended to record.

A capture manifest can say what instrumentation *exists* and what this run
*observed*. Neither answers the question a reviewer actually asks: "was the
part of the application I care about inside the declared boundary?" That needs
the application owner to declare the boundary.

This module holds that declaration (sealed beside the artifact), normalises it,
and assesses it against observed evidence. Assessment is disclosure, not proof:
a declared surface that was never observed means the declaration was broader
than the run, not that evidence was lost.

Design contract: docs/rfcs/operation-identity-and-event-completeness.md (P1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCOPE_SCHEME = "epi-capture-scope/v1"

#: Artifacts sealed at or after this spec version are expected to carry a
#: declaration. Older artifacts are never failed for lacking one.
SCOPE_ENFORCED_VERSION = "4.12.0"

SCOPE_SIDECAR = Path("artifacts") / "capture_scope.json"

SOURCE_NONE = "none"
SOURCE_CALLER = "caller"

VERDICT_UNKNOWN = "unknown"
VERDICT_CONSISTENT = "consistent_with_declaration"
VERDICT_UNMET = "declaration_unmet"


def _version_tuple(value: Any) -> tuple[int, ...] | None:
    if not isinstance(value, str):
        return None
    parts: list[int] = []
    for chunk in value.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if parts else None


def is_scope_enforced(spec_version: Any) -> bool:
    """True when this artifact version is expected to declare a scope."""
    current = _version_tuple(spec_version)
    gate = _version_tuple(SCOPE_ENFORCED_VERSION)
    if current is None or gate is None:
        return False
    width = max(len(current), len(gate))
    current += (0,) * (width - len(current))
    gate += (0,) * (width - len(gate))
    return current >= gate


def normalize_declaration(value: Any) -> dict[str, Any] | None:
    """Accept a list of surfaces or a declaration dict; return a sealed form.

    Returns ``None`` for malformed input rather than inventing a boundary.
    """
    if value is None:
        return None

    if isinstance(value, (list, tuple)):
        surfaces = value
        exclusions: list[Any] = []
        enforcement = "self_attested"
    elif isinstance(value, dict):
        surfaces = value.get("declared") or value.get("surfaces") or []
        exclusions = value.get("exclusions") or []
        enforcement = str(value.get("enforcement") or "self_attested")
    else:
        return None

    if isinstance(surfaces, str):
        surfaces = [surfaces]
    if isinstance(exclusions, str):
        exclusions = [exclusions]
    if not isinstance(surfaces, (list, tuple)) or not isinstance(
        exclusions, (list, tuple)
    ):
        return None

    clean_surfaces = sorted({str(item) for item in surfaces if str(item).strip()})
    clean_exclusions = sorted({str(item) for item in exclusions if str(item).strip()})
    if not clean_surfaces:
        return None

    return {
        "scheme": SCOPE_SCHEME,
        "declaration_source": SOURCE_CALLER,
        "declared": clean_surfaces,
        "exclusions": clean_exclusions,
        "enforcement": enforcement,
    }


def write_declaration(source_dir: Path, declaration: dict[str, Any]) -> Path:
    """Seal the declaration in the workspace so packing carries it."""
    path = Path(source_dir) / SCOPE_SIDECAR
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(declaration, indent=2, sort_keys=True), encoding="utf-8"
    )
    return path


def read_declaration(source_dir: Path) -> dict[str, Any] | None:
    """Read and re-validate a sealed declaration; ``None`` when absent/bad."""
    path = Path(source_dir) / SCOPE_SIDECAR
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("scheme") != SCOPE_SCHEME:
        return None
    declared = raw.get("declared")
    if not isinstance(declared, list) or not declared:
        return None
    return {
        "scheme": SCOPE_SCHEME,
        "declaration_source": str(raw.get("declaration_source") or SOURCE_CALLER),
        "declared": [str(item) for item in declared],
        "exclusions": [str(item) for item in (raw.get("exclusions") or [])],
        "enforcement": str(raw.get("enforcement") or "self_attested"),
    }


def _canonical_surface(surface: str) -> str:
    """Strip the ``capture_path:`` prefix so declarations and evidence compare.

    Observed surfaces are ``"<capture_path>:<surface>"`` (for example
    ``sdk_wrapper:openai.chat.completions``); a caller declares the surface name.
    """
    return surface.split(":", 1)[1] if ":" in surface else surface


def assess_capture_scope(
    capture_manifest: dict | None,
    spec_version: Any = None,
) -> dict[str, Any]:
    """Assess a sealed declaration against what this run actually observed.

    Never raises: a missing or malformed declaration is reported as
    ``unknown``, which is the honest answer, not a failure.
    """
    enforced = is_scope_enforced(spec_version)
    observed: list[str] = []
    declared: list[str] = []
    exclusions: list[str] = []
    source = SOURCE_NONE
    enforcement = "not_applicable"

    if isinstance(capture_manifest, dict):
        raw_observed = capture_manifest.get("active_surfaces") or []
        if isinstance(raw_observed, list):
            observed = sorted({str(item) for item in raw_observed if str(item)})
        raw_declared = capture_manifest.get("declared_surfaces") or []
        if isinstance(raw_declared, list):
            declared = sorted({str(item) for item in raw_declared if str(item)})
        raw_exclusions = capture_manifest.get("capture_exclusions") or []
        if isinstance(raw_exclusions, list):
            exclusions = sorted({str(item) for item in raw_exclusions if str(item)})
        source = str(capture_manifest.get("declaration_source") or SOURCE_NONE)
        enforcement = str(capture_manifest.get("enforcement") or "not_applicable")

    if source == SOURCE_NONE or not declared:
        return {
            "status": "unknown",
            "scheme": None,
            "declaration_source": SOURCE_NONE,
            "declared": [],
            "observed": observed,
            "declared_not_observed": [],
            "observed_not_declared": [],
            "exclusions": exclusions,
            "enforcement": enforcement,
            "verdict": VERDICT_UNKNOWN,
            "enforced": enforced,
        }

    declared_not_observed = [
        item for item in declared if _canonical_surface(item) not in {
            _canonical_surface(seen) for seen in observed
        }
    ]
    declared_canonical = {_canonical_surface(item) for item in declared}
    observed_not_declared = [
        item for item in observed if _canonical_surface(item) not in declared_canonical
    ]

    return {
        "status": "declared",
        "scheme": SCOPE_SCHEME,
        "declaration_source": source,
        "declared": declared,
        "observed": observed,
        "declared_not_observed": declared_not_observed,
        "observed_not_declared": observed_not_declared,
        "exclusions": exclusions,
        "enforcement": enforcement,
        "verdict": (
            VERDICT_UNMET if declared_not_observed else VERDICT_CONSISTENT
        ),
        "enforced": enforced,
    }
