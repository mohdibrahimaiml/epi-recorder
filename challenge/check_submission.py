#!/usr/bin/env python3
"""Check a "Break the seal" submission against the published break criteria.

    python challenge/check_submission.py <file.epi>

Prints BREAK or NO BREAK for criteria a-d from CHALLENGE.md. Criterion e
(crash / hang / code execution) needs a human; report those privately.

This only reads the file and the repository: it runs the same verification
code customers run (`epi_core`), with no network.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from epi_core.container import EPIContainer  # noqa: E402
from epi_core.review import verify_human_approvals  # noqa: E402
from epi_core.trust import verify_embedded_manifest_signature  # noqa: E402

CHALLENGE = REPO / "challenge"
ORIGINAL = CHALLENGE / "challenge-original.epi"
SIGNING_PUB = CHALLENGE / "challenge-signing-key.pub"
APPROVER_PUB = CHALLENGE / "challenge-approver-key.pub"


def _pub(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip().lower()


def _members(path: Path) -> dict[str, bytes]:
    out = {}
    for name in EPIContainer.list_members(path):
        try:
            out[name] = EPIContainer.read_member_bytes(path, name)
        except Exception:
            out[name] = b""
    return out


def _sealed_members(members: dict[str, bytes], manifest) -> dict[str, bytes]:
    return {name: members.get(name, b"") for name in manifest.file_manifest}


def _key_name_for(pub_hex: str) -> str:
    return hashlib.sha256(pub_hex.encode()).hexdigest()[:16]


def check(submission: Path, *, pin_approver: bool = True) -> tuple[dict[str, tuple[bool, str]], dict]:
    results: dict[str, tuple[bool, str]] = {}
    manifest = EPIContainer.read_manifest(submission)
    integrity_ok, mismatches = EPIContainer.verify_integrity(submission)
    signature_valid, _signer, message = verify_embedded_manifest_signature(manifest)
    sub_members = _members(submission)
    orig_members = _members(ORIGINAL) if ORIGINAL.is_file() else {}
    sub_sealed = _sealed_members(sub_members, manifest)
    orig_sealed = _sealed_members(orig_members, EPIContainer.read_manifest(ORIGINAL)) if ORIGINAL.is_file() else {}

    sealed_by_challenge = str(manifest.public_key or "").lower() == _pub(SIGNING_PUB)
    steps_differ = sub_sealed.get("steps.jsonl") != orig_sealed.get("steps.jsonl")
    any_member_differs = sub_sealed != orig_sealed

    # a. intact + signed by the challenge key, but the steps differ from the original.
    a_break = bool(integrity_ok and signature_valid is True and sealed_by_challenge and steps_differ)
    results["a"] = (
        a_break,
        "signed by the challenge key with different steps" if a_break
        else "steps match the original, or the seal/signature is not valid",
    )

    # b. --require-human-approval passes without the challenge approver's key.
    approver_hex = _pub(APPROVER_PUB)
    approval_ok = False
    why = "approval requirement not met"
    with tempfile.TemporaryDirectory() as tmp:
        import os

        os.environ["EPI_TRUSTED_APPROVERS_DIR"] = tmp
        try:
            from epi_core.approvers import ApproverRegistry

            if pin_approver:
                ApproverRegistry(Path(tmp)).add("challenge-approver", approver_hex)
            state = verify_human_approvals(submission)
            approval_ok = bool(state.get("requirement_met"))
            why = str(state.get("detail") or why)
            signed_by_challenge_approver = any(
                item.get("classification") == "human_signed"
                and item.get("key_fingerprint")
                for item in state.get("approvals") or []
            )
        finally:
            os.environ.pop("EPI_TRUSTED_APPROVERS_DIR", None)
        b_break = approval_ok and not signed_by_challenge_approver
        results["b"] = (
            b_break,
            "approved without the published approver key" if b_break else why,
        )

    # c. a tampered file the browser verifier would show as intact.
    #    The browser's integrity check is the manifest file-hash check, so a
    #    "shown as intact" tampered file is exactly one the CLI calls intact
    #    while its sealed bytes differ from the published original.
    #    It must also still claim to be the published artifact (same sealing key):
    #    a re-signed copy under a different key is a different artifact, and the
    #    browser shows it as such.
    c_break = bool(integrity_ok and sealed_by_challenge and any_member_differs)
    results["c"] = (
        c_break,
        "sealed bytes differ from the original but integrity still passes" if c_break
        else "tampering is detected (integrity fails, or the file is the original)",
    )

    # d. `epi verify` reports a signer fingerprint that does not match the key
    #    that actually signed (the signature names a key name derived from it).
    parts = str(manifest.signature or "").split(":")
    claimed_name = parts[1] if len(parts) == 3 else ""
    expected = _key_name_for(str(manifest.public_key or "").lower())
    d_break = bool(signature_valid is True and claimed_name and claimed_name != expected)
    results["d"] = (
        d_break,
        f"signature names key {claimed_name!r}, public key derives {expected!r}" if d_break
        else "reported signer matches the key that signed",
    )

    meta = {
        "integrity_ok": integrity_ok,
        "signature_valid": signature_valid,
        "message": message,
        "mismatches": list(mismatches),
    }
    return results, meta


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python challenge/check_submission.py <file.epi>", file=sys.stderr)
        return 2
    submission = Path(argv[1])
    if not submission.is_file():
        print(f"no such file: {submission}", file=sys.stderr)
        return 2
    try:
        results, meta = check(submission)
    except Exception as exc:
        print(f"could not read the submission: {exc}", file=sys.stderr)
        return 2

    broke = False
    for criterion in ("a", "b", "c", "d"):
        is_break, detail = results[criterion]
        broke = broke or is_break
        print(f"{'BREAK   ' if is_break else 'NO BREAK'}  ({criterion}) {detail}")
    print("NOT CHECKED  (e) crash / hang / code execution — report privately")
    print(f"         file: {json.dumps(meta)}")
    print()
    print("RESULT: BREAK" if broke else "RESULT: NO BREAK")
    return 0 if not broke else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
