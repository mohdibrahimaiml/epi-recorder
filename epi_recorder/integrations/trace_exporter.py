"""
TRACE exporter — convert a sealed .epi into a Level 0 log-import TRACE Trust Record.

Uses ONLY shipped TRACE v0.2 fields (tool_transcript, origin log-import,
enforcement_mode declared, software-only). Validated via agentrust_trace.iter_errors
before signing.

Spec: trace-v0.2.json, with optional `references` / `behavior-trace`
forward-compat (trace-spec main, issue #241). Validated at runtime via
agentrust_trace.SCHEMA inspection, not version strings.

`references` sub-schema (from https://raw.githubusercontent.com/agentrust-io/trace-spec/main/schema/trace-claim.json):
{
  "type": "array",
  "description": "Facts outside this record that it points at. Spec section 3.1.2. An entry is a pointer, not evidence: the signature attests that this record points there, not the truth of what it points at. The block is assurance-neutral and does not affect runtime.platform. Two further rules in 3.1.2 bind verifiers rather than records, so this schema cannot express them: a verifier MUST NOT reject a record because an entry cannot be resolved, and MUST NOT treat a resolved entry as attested evidence.",
  "items": {
    "type": "object",
    "required": ["rel", "id", "resolver"],
    "properties": {
      "rel": {"type": "string", "minLength": 1, "description": "Relationship type. The registered values are a registry that grows, so this is not a closed set. authorized-intent: an authorization decided before execution, held in another system. approval-outcome: an attributable human approval attached to a step-up or defer decision. behavior-trace: a behavioural record of what the agent did, of which this record is the environment evidence."},
      "id": {"type": "string", "minLength": 1, "description": "Identifier of the referenced fact within the resolver's system."},
      "resolver": {"type": "string", "minLength": 1, "description": "Identifier of the party obliged to resolve id. A producer that cannot name one omits the entry. Which identifiers are self-asserted is not decidable from the record, so this constrains the field's presence and not its value."},
      "retention": {"type": "string", "pattern": "^P(\\d+W|(\\d+Y(\\d+M)?(\\d+D)?|\\d+M(\\d+D)?|\\d+D)(T(\\d+H(\\d+M)?(\\d+S)?|\\d+M(\\d+S)?|\\d+S))?|T(\\d+H(\\d+M)?(\\d+S)?|\\d+M(\\d+S)?|\\d+S))$", "description": "Period for which resolver undertakes to keep id resolvable, as an ISO 8601 duration. An undertaking only: nothing in this specification enforces it."},
      "digest": {"type": "string", "pattern": "^sha(256:[0-9a-f]{64}|384:[0-9a-f]{96})$", "description": "SHA-256 or SHA-384 digest of the referenced object, when the producer holds it at issue time."}
    },
    "additionalProperties": false
  }
}
Required: rel, id, resolver. Allowed rel (open registry): authorized-intent, approval-outcome, behavior-trace.
Two verifier obligations (from description, not schema-enforceable):
  - verifier MUST NOT reject a record because an entry cannot be resolved
  - verifier MUST NOT treat a resolved entry as attested evidence
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from epi_core._version import get_version
from epi_core.container import EPIContainer


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _epi_file_hash(epi_path: Path) -> str:
    # Prefer hash of canonical transcript (steps.jsonl) not whole envelope, for per-step audit
    try:
        steps_bytes = EPIContainer.read_member_bytes(epi_path, "steps.jsonl")
        return f"sha256:{_sha256_hex(steps_bytes)}"
    except Exception:
        h = hashlib.sha256()
        with open(epi_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"


def _count_steps(epi_path: Path) -> int:
    try:
        return EPIContainer.count_steps(epi_path)
    except Exception:
        try:
            return len(list(EPIContainer.read_steps(epi_path)))
        except Exception:
            return 0


def _schema_supports_references() -> bool:
    """Return True iff the installed agentrust_trace.SCHEMA declares `references`.

    Inspects the schema itself, never a version string, so the same code
    works before and after the upstream release (trace-spec issue #241).
    """
    try:
        import agentrust_trace

        schema = getattr(agentrust_trace, "SCHEMA", None)
        if not isinstance(schema, dict):
            return False
        props = schema.get("properties") or {}
        return "references" in props
    except Exception:
        return False


def _build_references_entry(
    epi_path: Path,
    transcript_uri: str,
    epi_hash: str,
    workflow_id: str,
) -> dict | None:
    """Build one behavior-trace references entry pointing at the .epi.

    Field names verbatim from trace-spec main schema/trace-claim.json:
      rel, id, resolver, digest (retention optional, omitted).

    resolver is the party obliged to resolve `id` per §3.1.2.
    A producer that cannot name one MUST omit the entry — never emit a
    placeholder like https://example.com or epilabs.org for artifacts we
    do not host.
    """
    try:
        from urllib.parse import urlparse

        parsed = urlparse(transcript_uri)
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            return None
        # Do not invent a resolver for placeholder artifact URLs we did not
        # provide. If the transcript is not hosted, we cannot name the party
        # obliged to resolve it, so we omit per spec.
        resolver = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return None
    ref_id = transcript_uri if transcript_uri else (workflow_id or epi_path.name)
    if not ref_id or not str(ref_id).strip():
        return None
    return {
        "rel": "behavior-trace",
        "id": ref_id,
        "resolver": resolver,
        "digest": epi_hash,
    }


_PLACEHOLDER_TRANSCRIPT_HOST = "epilabs.org/artifacts"
_PLACEHOLDER_TRANSPARENCY = "https://epilabs.org/transparency/receipt"


def _is_placeholder_transcript_uri(uri: str) -> bool:
    return _PLACEHOLDER_TRANSCRIPT_HOST in (uri or "")


def _is_placeholder_transparency(uri: str) -> bool:
    return (uri or "") == _PLACEHOLDER_TRANSPARENCY


def epi_to_trace_record(
    epi_path: Path | str,
    transcript_uri: Optional[str] = None,
    *,
    subject: Optional[str] = None,
    model_provider: str = "epi-recorder",
    model_id: Optional[str] = None,
    data_class: str = "internal",
    extra_transparency: str = "https://epilabs.org/transparency/receipt",
    appraiser: str = "https://epilabs.org/verifier",
    references: str = "auto",
    strict: bool = False,
) -> Dict[str, Any]:
    """
    Build an unsigned TRACE v0.2 Trust Record from a sealed .epi.

    The .epi file is the transcript; tool_transcript.hash commits to it.
    Caller must sign via agentrust_trace.sign_record before distribution.

    references: auto | on | off
      auto (default): emit `references` with one behavior-trace entry iff the
        installed agentrust_trace.SCHEMA declares it (runtime detection).
      on: force emission (test post-release path; will fail validation on 0.9.0).
      off: force omission.

    strict: when True, fail-closed (ValueError) on placeholder transcript_uri
      or transparency instead of attaching soft _epi_warnings. CLI passes
      strict=True when --sign is used so signed records never carry
      non-resolvable placeholder URLs.
    """
    epi_path = Path(epi_path)
    if not epi_path.exists():
        raise FileNotFoundError(f".epi not found: {epi_path}")

    manifest = EPIContainer.read_manifest(epi_path)
    # Derive fields from manifest
    workflow_id = str(getattr(manifest, "workflow_id", ""))
    # model_id fallback to workflow_name or file stem
    if model_id is None:
        model_id = getattr(manifest, "workflow_name", None) or epi_path.stem or get_version()
    if subject is None:
        # SPIFFE or DID URI required — use spiffe with artifact UUID
        subject = f"spiffe://epilabs.org/epi-recorder/{workflow_id}" if workflow_id else "spiffe://epilabs.org/epi-recorder/unknown"

    # Data classification: prefer governance.data_class if present
    gov = getattr(manifest, "governance", None) or {}
    if isinstance(gov, dict) and gov.get("data_class"):
        data_class = str(gov["data_class"])

    now = int(time.time())
    digest_zero = "sha256:" + "00" * 32
    epi_hash = _epi_file_hash(epi_path)
    call_count = _count_steps(epi_path)
    # Transcript URI: require explicit for production; default is a placeholder that warns
    transcript_uri_provided = transcript_uri is not None
    if transcript_uri is None:
        # Use manifest governance URL if available, else placeholder (caller should pass real hosted URL)
        transcript_uri = f"https://epilabs.org/artifacts/{epi_path.name}"
        # Placeholder — CLI will warn that this does not resolve until hosted

    # TRACE defines policy.bundle_hash as the SHA-256 of the Cedar policy bundle.
    # We do not evaluate Cedar. We hash sealed policy.json (or policy_evaluation.json)
    # and set enforcement_mode="declared" so the field is a binding to authored
    # policy bytes, not a claim that a Cedar engine evaluated them.
    bundle_hash = digest_zero
    try:
        # Prefer policy.json (authored policy) over policy_evaluation.json
        for candidate in ("policy.json", "policy_evaluation.json"):
            try:
                pol_bytes = EPIContainer.read_member_bytes(epi_path, candidate)
                if pol_bytes and len(pol_bytes) > 10:
                    bundle_hash = f"sha256:{hashlib.sha256(pol_bytes).hexdigest()}"
                    break
            except Exception:
                continue
    except Exception:
        pass

    # Transparency: prefer SCITT receipt URL if artifact has one, else require explicit
    # If governance.scitt.service_url exists, use it; else use placeholder that CLI warns about
    transparency_uri = extra_transparency
    try:
        gov_scitt = (getattr(manifest, "governance", None) or {}).get("scitt") if isinstance(getattr(manifest, "governance", None), dict) else None
        if gov_scitt and isinstance(gov_scitt, dict) and gov_scitt.get("service_url"):
            transparency_uri = gov_scitt["service_url"]
            if gov_scitt.get("entry_id"):
                transparency_uri = f"{transparency_uri.rstrip('/')}/{gov_scitt['entry_id']}"
    except Exception:
        pass

    record: Dict[str, Any] = {
        "eat_profile": "tag:agentrust-io.com,2026:trace-v0.2",
        "iat": now,
        "subject": subject,
        "model": {
            "provider": model_provider,
            "model_id": str(model_id)[:128],
        },
        "runtime": {
            "platform": "software-only",
            "measurement": digest_zero,
        },
        "policy": {
            "bundle_hash": bundle_hash,
            "enforcement_mode": "declared",
        },
        "data_class": data_class,
        "tool_transcript": {
            "hash": epi_hash,
            "call_count": int(call_count),
            "transcript_uri": transcript_uri,
        },
        "origin": {
            "kind": "log-import",
            "producer": f"epi-recorder/{get_version()}",
            "source_event_id": workflow_id or epi_path.name,
            "ingested_at": now,
        },
        "build_provenance": {
            "slsa_level": 0,
            "digest": digest_zero,
        },
        "appraisal": {
            # TRACE appraisal.status: none | affirming | contraindicated.
            # Export is not an independent TRACE verifier judgment — always "none".
            "status": "none",
            "verifier": appraiser,
        },
        "transparency": transparency_uri,
        "cnf": {
            # Placeholder — sign_record will replace with real JWK
            "jwk": {"kty": "OKP", "crv": "Ed25519", "x": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"},
        },
    }

    # — references / behavior-trace (trace-spec §3.1.2, issue #241)
    # tool_transcript is the integrity binding (hash of the transcript).
    # references is the pointer that says "this record's environment evidence
    # lives in that behavioural record" — assurance-neutral, not evidence.
    # Both commit to the same .epi bytes (same sha256), but they assert
    # different things: tool_transcript asserts the transcript digest,
    # references asserts the existence and location of the behavior trace.
    # Two verifier rules from 3.1.2 bind verifiers, not records:
    #   a verifier MUST NOT reject a record because an entry cannot be resolved
    #   a verifier MUST NOT treat a resolved entry as attested evidence
    # Emitted only when the installed schema declares `references`; otherwise
    # omitted silently so 0.9.0 validation stays green.
    references_mode = str(references).lower().strip() if isinstance(references, str) else "auto"
    if references_mode not in ("auto", "on", "off"):
        references_mode = "auto"
    supports_refs = _schema_supports_references()
    should_emit = (references_mode == "on") or (references_mode == "auto" and supports_refs)
    if references_mode == "off":
        should_emit = False
    # Per §3.1.2: if we cannot name the party obliged to resolve `id`, omit the
    # entry entirely instead of emitting a placeholder. For auto-generated
    # placeholder transcript_uris we cannot name a resolver, so omit.
    if should_emit:
        if not transcript_uri_provided and references_mode != "on":
            # No explicit transcript_uri — cannot name resolver, omit per spec
            should_emit = False
        else:
            entry = _build_references_entry(epi_path, transcript_uri, epi_hash, workflow_id)
            if entry is None:
                should_emit = False
            else:
                record["references"] = [entry]
    # Attach warnings for placeholder URLs so CLI can surface them.
    # In strict mode (signed export) fail closed instead of warning.
    if strict:
        if not transcript_uri_provided or _is_placeholder_transcript_uri(transcript_uri):
            raise ValueError(
                "transcript_uri is required for signed TRACE export — pass --transcript-uri "
                "with the real hosted .epi URL (placeholder epilabs.org/artifacts/* does not resolve)"
            )
        if _is_placeholder_transparency(transparency_uri):
            raise ValueError(
                "transparency is required for signed TRACE export — pass a SCITT log entry "
                "or TSA receipt URL via extra_transparency (placeholder does not resolve)"
            )
    record["_epi_warnings"] = []
    if "artifacts" in transcript_uri and "epilabs.org/artifacts" in transcript_uri:
        record["_epi_warnings"].append(
            f"transcript_uri is placeholder {transcript_uri} — pass --transcript-uri with the real hosted .epi URL"
        )
    if transparency_uri == "https://epilabs.org/transparency/receipt":
        record["_epi_warnings"].append(
            "transparency is placeholder — no SCITT receipt bound; point at your SCITT log entry or TSA receipt"
        )
    return record


def _load_trace_private_key_pem() -> object | None:
    """Load Ed25519 private key from TRACE_PRIVATE_KEY_PEM if set.

    Matches the TRACE quickstart fallback (`load_signing_key` reads this env var).
    Returns None when unset or unparseable.
    """
    pem = os.environ.get("TRACE_PRIVATE_KEY_PEM")
    if not pem or not str(pem).strip():
        return None
    raw = pem.encode("utf-8") if isinstance(pem, str) else pem
    # Allow \\n-escaped PEM in env files
    if b"\\n" in raw and b"-----BEGIN" in raw:
        raw = raw.replace(b"\\n", b"\n")
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        return load_pem_private_key(raw, password=None)
    except Exception:
        return None


def _find_sealing_private_key(manifest) -> tuple[object, str] | None:
    """Find the local private key that matches the manifest's sealing public key.

    Returns (private_key, key_name) or None if not found (caller should use ephemeral).
    """
    pub_hex = getattr(manifest, "public_key", None)
    if not pub_hex:
        return None
    try:
        from epi_core.keys import KeyManager

        km = KeyManager()
        want = pub_hex.strip().lower()
        for info in km.list_keys():
            name = info.get("name") or ""
            try:
                raw = km.load_public_key(name)
                if raw.hex().lower() == want:
                    priv = km.load_private_key(name)
                    return priv, name
            except Exception:
                continue
    except Exception:
        return None
    return None
