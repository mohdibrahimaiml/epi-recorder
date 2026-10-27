"""Step 6: the challenge artifacts are safe to publish and the checker is honest.

Runs the published checker against the original and against re-signed, edited
and forged variants: none of them may report BREAK.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now
from epi_core.trust import sign_manifest

REPO = Path(__file__).resolve().parents[1]
CHALLENGE = REPO / "challenge"
ORIGINAL = CHALLENGE / "challenge-original.epi"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "challenge_check", CHALLENGE / "check_submission.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker():
    if not ORIGINAL.is_file():
        pytest.skip("challenge artifacts are not generated")
    return _load_checker()


def _rewrite(epi: Path, replacements: dict[str, bytes]) -> None:
    import shutil
    import zipfile

    fmt = EPIContainer.detect_container_format(epi)
    temp = epi.parent / f".{epi.name}.tmp"
    temp.mkdir(parents=True, exist_ok=True)
    payload, nxt = temp / "p.zip", temp / "n.zip"
    try:
        EPIContainer.extract_inner_payload(epi, payload)
        with zipfile.ZipFile(payload) as src, zipfile.ZipFile(nxt, "w") as dst:
            for item in src.infolist():
                if item.filename in replacements:
                    continue
                dst.writestr(item, src.read(item.filename))
            for name, data in replacements.items():
                dst.writestr(name, data)
        EPIContainer.write_from_payload(nxt, epi, container_format=fmt)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def _ledger(epi: Path) -> str:
    return sorted(
        name for name in EPIContainer.list_members(epi)
        if name.startswith("reviews/") and name.endswith(".json")
    )[-1]


def _broke(results: dict) -> list[str]:
    return [key for key, (is_break, _detail) in results.items() if is_break]


def test_no_private_key_material_is_published():
    pem = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")
    hex64 = re.compile(rb"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
    for path in sorted(CHALLENGE.rglob("*")):
        if not path.is_file():
            continue
        blob = path.read_bytes()
        assert not pem.search(blob), f"private key PEM marker in {path}"
        if path.suffix == ".pub":
            # A published key IS 64 hex; anything more means something leaked.
            assert len(hex64.findall(blob)) == 1, f"unexpected 64-hex content in {path}"
        elif path.suffix not in {".epi", ".pyc"}:
            # .epi legitimately holds hex hashes and the public key.
            assert not hex64.search(blob), f"64-hex (possible seed) in {path}"


def test_original_is_no_break(checker):
    results, meta = checker.check(ORIGINAL)
    assert _broke(results) == [], results
    assert meta["integrity_ok"] is True
    assert meta["signature_valid"] is True


def test_one_step_edited_is_no_break(checker, tmp_path):
    target = tmp_path / "edited.epi"
    target.write_bytes(ORIGINAL.read_bytes())
    steps = EPIContainer.read_member_text(target, "steps.jsonl").splitlines()
    first = json.loads(steps[0])
    first["content"]["tampered"] = True
    steps[0] = json.dumps(first)
    _rewrite(target, {"steps.jsonl": ("\n".join(steps) + "\n").encode()})
    results, meta = checker.check(target)
    assert _broke(results) == [], results
    assert meta["integrity_ok"] is False


def test_approval_record_edited_is_no_break(checker, tmp_path):
    target = tmp_path / "approval-edited.epi"
    target.write_bytes(ORIGINAL.read_bytes())
    member = _ledger(target)
    payload = EPIContainer.read_member_json(target, member)
    payload["reviews"][0]["decision"] = "deny"
    _rewrite(target, {member: json.dumps(payload).encode()})
    results, _meta = checker.check(target)
    assert _broke(results) == [], results


def test_resigned_with_a_random_key_is_no_break(checker, tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "steps.jsonl").write_text(
        EPIContainer.read_member_text(ORIGINAL, "steps.jsonl"), encoding="utf-8"
    )
    key = Ed25519PrivateKey.generate()
    target = tmp_path / "resigned.epi"
    EPIContainer.pack(
        source,
        ManifestModel(workflow_id=__import__("uuid").uuid4(), created_at=utc_now(), cli_command="pytest"),
        target,
        signer_function=lambda manifest: sign_manifest(manifest, key, "someone-else"),
        preserve_generated=True,
        generate_analysis=False,
    )
    results, meta = checker.check(target)
    assert _broke(results) == [], results
    assert meta["integrity_ok"] is True


def test_forged_approval_signed_by_a_random_key_is_no_break(checker, tmp_path):
    from epi_core.keys import key_fingerprint
    from epi_core.review import ReviewRecord, add_review_to_artifact, make_approval_entry

    target = tmp_path / "forged-approval.epi"
    target.write_bytes(ORIGINAL.read_bytes())
    rogue = Ed25519PrivateKey.generate()
    rogue_pub = rogue.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    entry = make_approval_entry(
        approval_id="refund-7",
        decision="approve",
        action="refund REF-7",
        reason="forged",
        approver_name="challenge-approver",
        key_fingerprint_hex=key_fingerprint(rogue_pub, grouped=False),
    )
    record = ReviewRecord(
        reviewed_by="challenge-approver",
        reviews=[entry],
        reviewer_identity={"type": "name", "value": "challenge-approver", "verified": False},
    )
    add_review_to_artifact(target, record, private_key=rogue)
    results, _meta = checker.check(target)
    assert _broke(results) == [], results


def test_approver_not_pinned_reports_not_met_not_break(checker):
    results, _meta = checker.check(ORIGINAL, pin_approver=False)
    assert _broke(results) == [], results
    assert results["b"][0] is False
