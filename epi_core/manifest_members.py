"""Signed manifest data that must not sit at the manifest top level.

The 4.9.0 verifier parses ``manifest.json`` into its own ``ManifestModel``,
drops fields it does not know, and hashes what remains.  A new *top-level*
field therefore changes the preimage for every older verifier and makes a
genuine file read as ``SIGNATURE INVALID``.

Data added after 4.9.0 is written as a normal ZIP member instead, listed in
``file_manifest`` (which is inside the signature and the witness content
digest).  Older verifiers hash the member like any other file and the new
verifier reads it back.  ``release.json`` already worked this way.

Member layout (stable; each file is a JSON object with one named key):

* ``artifacts/seal_chain.json``      -> ``{"seal_chain": {...}}``
* ``artifacts/case_id.json``         -> ``{"case_id": "..."}``
* ``artifacts/record_kind.json``     -> ``{"record_kind": "release"}``
* ``artifacts/release_ref.json``     -> ``{"release_ref": {...}, "runtime_components": [...]}``
* ``release.json``                   -> the release document (already written by the release command)

``MANIFEST_MEMBER_FIELDS`` is the single list used by the writer, the reader,
the Python hash and (mirrored) the browser preimage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

# Fields that are stored as members, never at the manifest top level.  This is
# exactly the set of ManifestModel fields 4.9.0 does not know (plus case_id,
# which was added on this branch and is also unknown to 4.9.0).
MANIFEST_MEMBER_FIELDS: frozenset[str] = frozenset(
    {
        "case_id",
        "seal_chain",
        "record_kind",
        "release",
        "release_ref",
        "runtime_components",
    }
)

# field -> member path for the one-field members.  release_ref and
# runtime_components share artifacts/release_ref.json; release uses the
# release document already written by `epi release create`.
_MEMBER_PATHS: dict[str, str] = {
    "seal_chain": "artifacts/seal_chain.json",
    "case_id": "artifacts/case_id.json",
    "record_kind": "artifacts/record_kind.json",
    "release_ref": "artifacts/release_ref.json",
    "runtime_components": "artifacts/release_ref.json",
    "release": "release.json",
}

# Keys inside each member file.  A single-key wrapper keeps the member
# self-describing and lets release_ref.json carry two fields.
_MEMBER_KEYS: dict[str, tuple[str, ...]] = {
    "artifacts/seal_chain.json": ("seal_chain",),
    "artifacts/case_id.json": ("case_id",),
    "artifacts/record_kind.json": ("record_kind",),
    "artifacts/release_ref.json": ("release_ref", "runtime_components"),
    "release.json": ("release",),
}


def member_path(field: str) -> str | None:
    return _MEMBER_PATHS.get(field)


def _json_dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def _field_value(manifest: Any, field: str) -> Any:
    value = getattr(manifest, field, None)
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def write_manifest_members(
    source_dir: Path,
    manifest: Any,
    *,
    include: Iterable[str] | None = None,
) -> list[Path]:
    """Write the signed member files before the file_manifest walk.

    ``include`` limits which fields are written (used for the seal chain,
    which is allocated before the walk but may not exist on older re-sign
    paths).  Returns the paths written.
    """
    wanted = set(MANIFEST_MEMBER_FIELDS if include is None else include)
    written: list[Path] = []

    # Group by member file so release_ref.json writes both keys at once.
    by_path: dict[str, dict[str, Any]] = {}
    for field in MANIFEST_MEMBER_FIELDS:
        if field not in wanted:
            continue
        value = _field_value(manifest, field)
        if value is None:
            continue
        path = _MEMBER_PATHS[field]
        by_path.setdefault(path, {})[field] = value

    for rel_path, payload in by_path.items():
        target = source_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_json_dump(payload) + "\n", encoding="utf-8")
        written.append(target)
    return written


def manifest_storage_dict(manifest: Any) -> dict[str, Any]:
    """The manifest exactly as it is stored and signed.

    Member-backed fields are removed here (and from the Python hash) so the
    top level contains only fields 4.9.0's ManifestModel knows.
    """
    data = manifest.model_dump(mode="json")
    for field in MANIFEST_MEMBER_FIELDS:
        data.pop(field, None)
    return data


def manifest_storage_json(manifest: Any, *, indent: int = 2) -> str:
    return json.dumps(
        manifest_storage_dict(manifest),
        indent=indent,
        ensure_ascii=False,
    )


def _read_member(epi_path: Path, rel_path: str) -> dict[str, Any] | None:
    from epi_core.container import EPIContainer

    try:
        payload = EPIContainer.read_member_json(epi_path, rel_path)
    except (ValueError, FileNotFoundError):
        return None
    return payload if isinstance(payload, dict) else None


def load_manifest_members(epi_path: Path, manifest_dict: dict[str, Any]) -> dict[str, Any]:
    """Rehydrate member-backed fields from the archive into ``manifest_dict``.

    Missing members are simply absent: that is every artifact sealed before
    this format, and every artifact whose optional field was None.
    """
    for rel_path, keys in _MEMBER_KEYS.items():
        payload = _read_member(epi_path, rel_path)
        if payload is None:
            continue
        for key in keys:
            if key in payload and payload[key] is not None:
                manifest_dict[key] = payload[key]
    return manifest_dict
