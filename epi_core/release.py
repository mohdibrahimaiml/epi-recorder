"""Signed release records: pin what was approved, compare what ran.

A **release** is a sealed ``.epi`` whose signed manifest carries
``record_kind="release"`` and a ``release`` block. It pins exact components
(files by SHA-256, models/code by identifier) and a ``release_digest`` over
the canonical component list plus name, version and the required approval
count. A **decision** artifact carries ``release_ref = {release_id,
release_digest}`` in its signed manifest, and ``runtime_components`` for what
EPI actually observed while the decision ran.

Honest limits (docs/RELEASES.md): EPI can only compare what it observed. The
``policy`` component is the ``epi_policy.json`` EPI loaded, not the vendor's
business logic unless they pass it in. An unobserved component is shown as
"not observed (declared only)", never as a match. Ordering falls back through
independent time sources and prints which one it used.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

COMPONENT_TYPES = ("policy", "prompt", "model", "tool_schema", "code", "config")
FILE_TYPES = ("policy", "prompt", "tool_schema", "config")
RELEASE_KIND = "release"

APPROVAL_ENTRY_TYPE = "release_approval"
APPROVAL_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    import rfc8785

    return rfc8785.dumps(value)


def _logical_name(spec: str) -> str:
    """``credit=policies/x.yaml`` -> ``credit``; a bare path -> its basename."""
    if "=" in spec:
        name, _, _path = spec.partition("=")
        if name.strip():
            return name.strip()
    return Path(spec).name


def _split_spec(spec: str) -> tuple[str, str]:
    if "=" in spec:
        name, _, path = spec.partition("=")
        if name.strip():
            return name.strip(), path
    return Path(spec).name, spec


def parse_component_specs(
    values: Iterable[str] | dict[str, str] | None,
    component_type: str,
    *,
    base_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Turn CLI/SDK declarations into components, rejecting name collisions.

    A bare value keeps the file's basename as the logical name. Two
    declarations with the same ``(type, logical name)`` are an error: the
    caller must name them (``--prompt system_a=...``).
    """
    specs: list[tuple[str, str]] = []
    if isinstance(values, str):
        values = [values]
    if isinstance(values, dict):
        specs = [(str(name), str(path)) for name, path in values.items()]
    else:
        for raw in values or []:
            if raw is None:
                continue
            text = str(raw).strip()
            if text:
                specs.append(_split_spec(text))

    components: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for name, raw_path in specs:
        path = Path(raw_path).expanduser()
        if not path.is_absolute() and base_dir is not None:
            candidate = Path(base_dir) / path
            if candidate.exists():
                path = candidate
        if not path.is_file():
            raise FileNotFoundError(
                f"{component_type} file not found: {raw_path} (logical name {name!r})"
            )
        key = (component_type, name)
        if key in seen:
            raise ValueError(
                f"duplicate {component_type} logical name {name!r}: two different "
                f"files cannot share it. Name them explicitly, e.g. "
                f"--{component_type} {name}_a=<file> --{component_type} {name}_b=<file>."
            )
        seen.add(key)
        components.append(
            {
                "type": component_type,
                "name": name,
                "sha256": sha256_file(path),
                "path": str(path),
            }
        )
    return components


def model_components(values: Iterable[str] | None) -> list[dict[str, Any]]:
    """``anthropic:claude-x`` is both the identifier and the logical name."""
    components: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(values, str):
        values = [values]
    for raw in values or []:
        identifier = str(raw or "").strip()
        if not identifier:
            continue
        if identifier in seen:
            raise ValueError(f"duplicate model identifier {identifier!r}")
        seen.add(identifier)
        components.append(
            {"type": "model", "name": identifier, "identifier": identifier}
        )
    return components


def code_component(commit: str | None) -> dict[str, Any] | None:
    if not commit:
        return None
    identifier = str(commit).strip()
    dirty = False
    if identifier == "auto":
        identifier, dirty = git_head()
    if not identifier:
        return None
    return {
        "type": "code",
        "name": "git",
        "identifier": identifier,
        "dirty": bool(dirty),
    }


def git_head(cwd: Path | None = None) -> tuple[str | None, bool]:
    """``git rev-parse HEAD`` plus whether the tree has uncommitted changes."""
    import subprocess

    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd or Path.cwd()),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if head.returncode != 0:
            return None, False
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(cwd or Path.cwd()),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return head.stdout.strip() or None, bool(status.stdout.strip())
    except Exception:
        return None, False


# ---------------------------------------------------------------------------
# Release document and digest
# ---------------------------------------------------------------------------


def _digest_component(component: dict[str, Any]) -> dict[str, Any]:
    """Only the fields that identify the component go into the digest.

    ``path`` is deliberately excluded: the same bytes checked out at a
    different absolute path are the same component.
    """
    ctype = str(component.get("type") or "")
    out: dict[str, Any] = {"type": ctype, "name": str(component.get("name") or "")}
    if component.get("sha256"):
        out["sha256"] = str(component["sha256"]).lower()
    if component.get("identifier"):
        out["identifier"] = str(component["identifier"])
    if ctype == "code":
        out["dirty"] = bool(component.get("dirty"))
    return out


def canonical_components(components: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (_digest_component(component) for component in components),
        key=lambda item: (item.get("type", ""), item.get("name", "")),
    )


def compute_release_digest(
    *,
    name: str,
    version: str,
    required_approvals: int,
    components: Iterable[dict[str, Any]],
) -> str:
    """SHA-256 over name, version, threshold and the canonical components.

    The threshold is inside the digest on purpose: a second artifact with the
    same components but ``required_approvals=1`` gets a different digest (and
    id), so it cannot be substituted for a 2-approval release.
    """
    body = {
        "name": str(name),
        "version": str(version),
        "required_approvals": int(required_approvals),
        "components": canonical_components(components),
    }
    return _sha256_bytes(_canonical(body))


def compute_release_id(release_digest: str) -> str:
    return "rel_" + str(release_digest)[:16]


def reject_duplicate_components(components: Iterable[dict[str, Any]]) -> None:
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for component in components:
        key = (str(component.get("type")), str(component.get("name")))
        if key in seen:
            raise ValueError(
                f"duplicate {key[0]} logical name {key[1]!r}: name each one "
                f"explicitly (for example --{key[0]} {key[1]}_a=<file>)."
            )
        seen[key] = component


def build_release_document(
    *,
    name: str,
    version: str,
    required_approvals: int,
    components: Iterable[dict[str, Any]],
    created_at: str | None = None,
) -> dict[str, Any]:
    items = [dict(component) for component in components]
    reject_duplicate_components(items)
    digest = compute_release_digest(
        name=name,
        version=version,
        required_approvals=int(required_approvals),
        components=items,
    )
    return {
        "release_id": compute_release_id(digest),
        "name": str(name),
        "version": str(version),
        "created_at": created_at or _now(),
        "required_approvals": int(required_approvals),
        "components": items,
        "release_digest": digest,
    }


def document_digest(document: dict[str, Any]) -> str:
    """Recompute the digest from a signed release block."""
    return compute_release_digest(
        name=str(document.get("name") or ""),
        version=str(document.get("version") or ""),
        required_approvals=int(document.get("required_approvals") or 1),
        components=document.get("components") or [],
    )


def is_dirty(document: dict[str, Any]) -> bool:
    return any(
        str(component.get("type")) == "code" and component.get("dirty")
        for component in document.get("components") or []
    )


# ---------------------------------------------------------------------------
# Loading and resolving a release artifact
# ---------------------------------------------------------------------------


def load_release(path: Path) -> dict[str, Any]:
    """Read and verify one release artifact. Raises ``ReleaseError``."""
    from epi_core.container import EPIContainer
    from epi_core.trust import verify_embedded_manifest_signature

    path = Path(path)
    if not path.is_file():
        raise ReleaseError(f"release artifact not found: {path}")
    integrity_ok, mismatches = EPIContainer.verify_integrity(path)
    if not integrity_ok:
        raise ReleaseError(f"release artifact failed integrity: {mismatches}")
    manifest = EPIContainer.read_manifest(path)
    valid, _name, message = verify_embedded_manifest_signature(manifest)
    if valid is not True:
        raise ReleaseError(f"release artifact signature is not valid: {message}")
    if getattr(manifest, "record_kind", None) != RELEASE_KIND or getattr(manifest, "release", None) is None:
        raise ReleaseError(f"{path} is not a release record")
    document = manifest.release.model_dump()
    recomputed = document_digest(document)
    if recomputed != str(document.get("release_digest")):
        raise ReleaseError(
            "release_digest does not match the signed components "
            f"(stored {str(document.get('release_digest'))[:12]}…, "
            f"recomputed {recomputed[:12]}…)"
        )
    return {
        "path": path,
        "manifest": manifest,
        "document": document,
        "release_id": str(document.get("release_id")),
        "release_digest": str(document.get("release_digest")),
        "sealed_at": manifest.created_at.isoformat() if manifest.created_at else None,
        "seal_chain": getattr(manifest, "seal_chain", None),
    }


class ReleaseError(RuntimeError):
    pass


def _release_candidates(directory: Path) -> list[Path]:
    try:
        return sorted(path for path in Path(directory).rglob("*.epi") if path.is_file())
    except OSError:
        return []


def resolve_release(
    release_ref: dict[str, Any] | Any | None,
    *,
    release_path: Path | str | None = None,
    release_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Find the release named by ``release_ref``. Never guesses."""
    if release_ref is None:
        return {"status": "not_declared", "detail": "this decision declares no release"}
    if hasattr(release_ref, "model_dump"):
        release_ref = release_ref.model_dump()
    want_id = str(release_ref.get("release_id") or "")
    want_digest = str(release_ref.get("release_digest") or "")

    if release_path:
        candidates = [Path(release_path)]
    else:
        base = Path(release_dir or os.environ.get("EPI_RELEASE_DIR") or ".")
        candidates = _release_candidates(base)

    matches: list[dict[str, Any]] = []
    mismatched: list[str] = []
    for path in candidates:
        try:
            loaded = load_release(path)
        except ReleaseError:
            continue
        if loaded["release_id"] != want_id:
            continue
        if want_digest and loaded["release_digest"] != want_digest:
            mismatched.append(str(path))
            continue
        matches.append(loaded)

    if not matches:
        detail = f"no release {want_id or '(no id)'} with the pinned digest was supplied"
        if mismatched:
            detail += f"; {len(mismatched)} file(s) share the id but not the digest"
        return {"status": "not_found", "detail": detail}
    if len(matches) > 1:
        return {
            "status": "ambiguous",
            "detail": (
                f"{len(matches)} release artifacts have id {want_id}; refusing to "
                "pick one: " + ", ".join(str(item["path"]) for item in matches)
            ),
            "paths": [str(item["path"]) for item in matches],
        }
    return {"status": "found", **matches[0]}


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------


def _approver_fingerprint(signature: str) -> str | None:
    parts = str(signature or "").split(":", 2)
    if len(parts) != 3 or parts[0] != "ed25519":
        return None
    try:
        from epi_core.keys import key_fingerprint

        return key_fingerprint(parts[1], grouped=False)
    except Exception:
        return None


def release_approvals(epi_path: Path, release_digest: str, *, registry: Any = None) -> list[dict[str, Any]]:
    """Valid ``release_approval`` records that name this exact digest."""
    from epi_core.review import ReviewRecord, _verify_review_signature, read_review_records

    if registry is None:
        try:
            from epi_core.approvers import ApproverRegistry

            registry = ApproverRegistry()
        except Exception:
            registry = None

    found: list[dict[str, Any]] = []
    for record in read_review_records(Path(epi_path)):
        if not isinstance(record, ReviewRecord):
            continue
        entry = next(
            (
                item
                for item in (record.reviews or [])
                if isinstance(item, dict)
                and item.get("entry_type") == APPROVAL_ENTRY_TYPE
            ),
            None,
        )
        if entry is None:
            continue
        if str(entry.get("release_digest") or "") != str(release_digest):
            continue
        if str(entry.get("decision") or "approve") != "approve":
            continue
        signature_ok, _why = _verify_review_signature(record, record.review_hash or "")
        if signature_ok is not True:
            continue
        parts = str(record.review_signature or "").split(":", 2)
        public_hex = parts[1] if len(parts) == 3 else ""
        fingerprint = _approver_fingerprint(str(record.review_signature or ""))
        pinned = False
        if registry is not None and public_hex:
            try:
                pinned = bool(registry.is_approver(public_hex))
            except Exception:
                pinned = False
        found.append(
            {
                "review_id": record.review_id,
                "approval_hash": record.review_hash,
                "approver": str((entry.get("approver") or {}).get("name") or record.reviewed_by or ""),
                "key_fingerprint": fingerprint,
                "public_key": public_hex,
                "pinned": pinned,
                "signed_at": entry.get("signed_at") or record.reviewed_at,
                "decision": entry.get("decision"),
                "path": str(epi_path),
            }
        )
    # One approval per approver key: the latest in the review chain wins.
    by_key: dict[str, dict[str, Any]] = {}
    for approval in found:
        key = str(approval.get("public_key") or approval.get("key_fingerprint") or "")
        by_key[key] = approval
    return list(by_key.values())


def _approval_tsa_time(epi_path: Path, review_id: str | None) -> str | None:
    try:
        from epi_core.review import read_approval_timestamp, verify_approval_timestamp

        stamp = read_approval_timestamp(Path(epi_path), review_id)
        if not isinstance(stamp, dict):
            return None
        return str(stamp.get("gen_time") or "") or None
    except Exception:
        return None


def _approval_witness_time(entries: Iterable[dict[str, Any]], approval_hash: str | None) -> str | None:
    if not approval_hash:
        return None
    times = [
        str(entry.get("received_at") or "")
        for entry in entries
        if str(entry.get("type") or "") == "epi.release_approval"
        and str(entry.get("approval_hash") or "") == str(approval_hash)
        and entry.get("received_at")
    ]
    return min(times) if times else None


def witness_time_for(entries: Iterable[dict[str, Any]], *, workflow_id: str | None = None, release_id: str | None = None) -> str | None:
    """First ``received_at`` for a decision or release report in a witness log."""
    times: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if release_id:
            if str(entry.get("type") or "") == "epi.release" and str(entry.get("release_id") or "") == release_id:
                times.append(str(entry.get("received_at") or ""))
        elif workflow_id:
            if str(entry.get("type") or "") in ("epi.sealed", "") and str(
                entry.get("workflow_id") or ""
            ) == workflow_id:
                times.append(str(entry.get("received_at") or ""))
    times = [time for time in times if time]
    return min(times) if times else None


def _parse_time(value: str | None) -> datetime | None:
    try:
        text = str(value or "").replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Component comparison
# ---------------------------------------------------------------------------


def _component_value(component: dict[str, Any]) -> tuple[str, str]:
    sha = str(component.get("sha256") or "").lower()
    ident = str(component.get("identifier") or "")
    return sha, ident


def compare_components(
    release_components: Iterable[dict[str, Any]],
    runtime_components: Iterable[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Match on ``(type, logical name)``; never call an unseen component a match."""
    release_items = [dict(item) for item in release_components]
    runtime_items = [dict(item) for item in (runtime_components or [])]

    used_runtime: set[int] = set()
    results: list[dict[str, Any]] = []
    for release_component in release_items:
        ctype = str(release_component.get("type"))
        name = str(release_component.get("name"))
        match_index = next(
            (
                index
                for index, runtime in enumerate(runtime_items)
                if str(runtime.get("type")) == ctype
                and str(runtime.get("name")) == name
                and index not in used_runtime
            ),
            None,
        )
        matched_by = "logical name"
        if match_index is None:
            # A single component of a type can only mean one thing (common for
            # the policy: the release names it "credit", EPI observes the file
            # it loaded). With two or more, names are required.
            release_of_type = [item for item in release_items if str(item.get("type")) == ctype]
            runtime_of_type = [
                (index, item)
                for index, item in enumerate(runtime_items)
                if str(item.get("type")) == ctype and index not in used_runtime
            ]
            if len(release_of_type) == 1 and len(runtime_of_type) == 1:
                match_index = runtime_of_type[0][0]
                matched_by = "single component of type"

        if match_index is None:
            results.append(
                {
                    "type": ctype,
                    "name": name,
                    "status": "not_observed",
                    "detail": "not observed (declared only)",
                }
            )
            continue

        used_runtime.add(match_index)
        runtime = runtime_items[match_index]
        observed = bool(runtime.get("observed", True))
        wanted_sha, wanted_id = _component_value(release_component)
        got_sha, got_id = _component_value(runtime)
        status = "match"
        detail = ""
        if not observed:
            status = "not_observed"
            detail = "not observed (declared only)"
        elif runtime.get("drift"):
            status = "drift"
            detail = str(runtime.get("drift_reason") or "changed during the run")
        elif wanted_sha and (got_sha != wanted_sha):
            status = "drift"
            detail = f"sha256 served {got_sha or '(none)'}, release pins {wanted_sha}"
        elif wanted_id and (got_id != wanted_id):
            status = "drift"
            detail = f"served {got_id or '(none)'}, release pins {wanted_id}"
        results.append(
            {
                "type": ctype,
                "name": name,
                "status": status,
                "detail": detail,
                "matched_by": matched_by,
                "expected": wanted_sha or wanted_id,
                "observed": got_sha or got_id,
            }
        )

    undeclared = []
    for index, runtime in enumerate(runtime_items):
        if index in used_runtime:
            continue
        if not bool(runtime.get("observed", True)):
            continue
        value = str(runtime.get("identifier") or runtime.get("sha256") or "")
        undeclared.append(
            {
                "type": str(runtime.get("type")),
                "name": str(runtime.get("name")),
                "value": value,
                "detail": (
                    f"{runtime.get('type')} {runtime.get('name')} ran but isn't "
                    "in the release"
                ),
            }
        )

    return {
        "components": results,
        "undeclared": undeclared,
        "drift": [item for item in results if item["status"] == "drift"],
        "not_observed": [item for item in results if item["status"] == "not_observed"],
        "matched": [item for item in results if item["status"] == "match"],
    }


# ---------------------------------------------------------------------------
# The verify-time decision check
# ---------------------------------------------------------------------------


def check_decision_release(
    *,
    decision_manifest: Any,
    release_path: Path | str | None = None,
    release_dir: Path | str | None = None,
    min_approvals: int | None = None,
    witness_entries: Iterable[dict[str, Any]] | None = None,
    registry: Any = None,
    decision_tsa_time: str | None = None,
    release_tsa_time: str | None = None,
) -> dict[str, Any]:
    """Compare one decision against its release. Never raises."""
    report: dict[str, Any] = {
        "status": "not_declared",
        "present": False,
        "detail": "this decision declares no release (`release=` was not used)",
        "components": [],
        "undeclared": [],
        "approvals": {"have": 0, "required": 0, "approvers": []},
    }
    release_ref = getattr(decision_manifest, "release_ref", None)
    if release_ref is None:
        return report
    report["present"] = True
    report["release_id"] = getattr(release_ref, "release_id", None)
    report["release_digest"] = getattr(release_ref, "release_digest", None)

    resolved = resolve_release(
        release_ref, release_path=release_path, release_dir=release_dir
    )
    report["resolution"] = resolved.get("status")
    if resolved["status"] != "found":
        report["status"] = resolved["status"]
        report["detail"] = resolved.get("detail")
        return report

    document = resolved["document"]
    release_id = resolved["release_id"]
    report.update(
        {
            "path": str(resolved["path"]),
            "name": document.get("name"),
            "version": document.get("version"),
            "release_sealed_at": resolved.get("sealed_at"),
            "release_digest": resolved["release_digest"],
            "required_approvals": int(document.get("required_approvals") or 1),
        }
    )

    if is_dirty(document):
        report["status"] = "dirty"
        report["detail"] = "built from uncommitted code (the release pins a dirty git tree)"
        # Still compare components below so the user sees the drift too.

    dirty_release = is_dirty(document)

    effective_required = max(
        int(document.get("required_approvals") or 1), int(min_approvals or 0)
    )
    approvals = release_approvals(
        resolved["path"], resolved["release_digest"], registry=registry
    )
    approvals = [approval for approval in approvals if approval.get("pinned")]
    report["approvals"] = {
        "have": len(approvals),
        "required": effective_required,
        "vendor_required": int(document.get("required_approvals") or 1),
        "verifier_minimum": int(min_approvals or 0),
        "approvers": [
            {
                "name": item.get("approver"),
                "key_fingerprint": item.get("key_fingerprint"),
                "signed_at": item.get("signed_at"),
            }
            for item in approvals
        ],
    }

    # --- components -------------------------------------------------------
    comparison = compare_components(
        document.get("components") or [],
        getattr(decision_manifest, "runtime_components", None),
    )
    report.update(comparison)
    if comparison["drift"]:
        report["status"] = "drift"
        report["detail"] = "; ".join(
            f"DRIFT: {item['type']} {item['name']} — {item['detail']}"
            for item in comparison["drift"]
        )
    elif comparison["undeclared"]:
        report["status"] = "undeclared"
        report["detail"] = "; ".join(
            f"UNDECLARED: {item['detail']}" for item in comparison["undeclared"]
        )
    elif comparison["not_observed"]:
        report["status"] = "not_observed"
        report["detail"] = "; ".join(
            f"{item['type']} {item['name']}: not observed (declared only)"
            for item in comparison["not_observed"]
        )

    if dirty_release:
        # Never MATCHES: the release pins code that is not in any commit.
        report["status"] = "dirty"
        report["detail"] = (
            "built from uncommitted code (the release pins a dirty git tree)"
        )

    if len(approvals) < effective_required:
        report["status"] = "unapproved"
        report["detail"] = (
            f"approved by {len(approvals)}/{effective_required}"
            + (
                f" (release required {document.get('required_approvals')}, "
                f"verifier minimum {int(min_approvals or 0)})"
                if min_approvals and int(min_approvals) > int(document.get("required_approvals") or 1)
                else ""
            )
        )
        return report

    if report["status"] == "not_declared":
        # Resolution, components and approvals all passed: start from MATCH.
        report["status"] = "match"

    # --- order ------------------------------------------------------------
    entries = list(witness_entries or [])
    decision_created = getattr(decision_manifest, "created_at", None)
    decision_created_iso = decision_created.isoformat() if decision_created else None
    decision_witness = witness_time_for(
        entries, workflow_id=str(getattr(decision_manifest, "workflow_id", "") or "")
    )
    release_witness = witness_time_for(entries, release_id=release_id)

    decision_chain = getattr(decision_manifest, "seal_chain", None)
    release_chain = resolved.get("seal_chain")
    same_ledger = (
        decision_chain is not None
        and release_chain is not None
        and str(getattr(decision_chain, "ledger_id", "")) == str(getattr(release_chain, "ledger_id", ""))
    )

    if decision_tsa_time and release_tsa_time:
        basis = "time-stamp"
        release_time, decision_time = release_tsa_time, decision_tsa_time
        independent = True
    elif decision_witness and release_witness:
        basis = "witness received_at"
        release_time, decision_time = release_witness, decision_witness
        independent = True
    elif same_ledger:
        basis = "seal sequence"
        release_time = str(getattr(release_chain, "seq", ""))
        decision_time = str(getattr(decision_chain, "seq", ""))
        independent = False
    else:
        basis = "vendor clock"
        release_time, decision_time = resolved.get("sealed_at"), decision_created_iso
        independent = False

    order_ok = True
    if basis == "seal sequence":
        try:
            order_ok = int(release_time) < int(decision_time)
        except (TypeError, ValueError):
            order_ok = True
    else:
        left, right = _parse_time(release_time), _parse_time(decision_time)
        if left and right:
            order_ok = left <= right

    report["order"] = {
        "status": "release_before_decision" if order_ok else "release_after_decision",
        "basis": basis,
        "independent": independent,
        "release_time": release_time,
        "decision_time": decision_time,
    }
    if not order_ok and report["status"] == "match":
        report["status"] = "release_after_decision"
        report["detail"] = (
            f"the release was sealed after this decision (basis: {basis})"
        )

    # --- approvals before use --------------------------------------------
    # Ordering may have used the seal sequence (not a time), so the approval
    # comparison always uses a real timestamp: TSA, then witness, then the
    # decision's signed clock. A sequence number can never date an approval.
    if decision_tsa_time:
        decision_instant = _parse_time(decision_tsa_time)
        approval_basis = "time-stamp"
    elif decision_witness:
        decision_instant = _parse_time(decision_witness)
        approval_basis = "witness received_at"
    else:
        decision_instant = _parse_time(decision_created_iso)
        approval_basis = "vendor clock"
    approvals_before = 0
    for approval in approvals:
        stamp = _approval_tsa_time(resolved["path"], approval.get("review_id"))
        if not stamp:
            stamp = _approval_witness_time(entries, approval.get("approval_hash"))
        basis_used = "time-stamp" if stamp and stamp == _approval_tsa_time(
            resolved["path"], approval.get("review_id")
        ) else ("witness received_at" if stamp else "approver clock")
        approval_time = _parse_time(stamp or approval.get("signed_at"))
        approval["time"] = stamp or approval.get("signed_at")
        approval["time_basis"] = basis_used
        approval["before_decision"] = bool(
            decision_instant and approval_time and approval_time <= decision_instant
        )
        if approval["before_decision"]:
            approvals_before += 1

    report["approvals_before_decision"] = approvals_before
    if approvals_before < effective_required and report["status"] == "match":
        report["status"] = "approved_after_use"
        report["detail"] = (
            f"the approvals that meet the threshold were signed after this decision "
            f"was sealed ({approvals_before}/{effective_required} before use)"
        )

    if report["status"] == "match":
        report["detail"] = "every observed component matches the approved release"
    report["basis"] = basis
    report["independent"] = independent
    return report


def approvals_for_release(
    release_path: Path, release_digest: str, *, registry: Any = None
) -> list[dict[str, Any]]:
    return release_approvals(Path(release_path), release_digest, registry=registry)
