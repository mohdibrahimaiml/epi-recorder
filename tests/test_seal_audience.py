"""Seal chains are per customer, not per signing key."""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.audience import commitment_record, derive_audiences, verify_commitment
from epi_core.container import EPIContainer
from epi_core.keys import fingerprint_for_private_key
from epi_core.schemas import ManifestModel
from epi_core.seal_ledger import analyze, allocate
from epi_core.trust import sign_manifest


def _entry(key: str, audience: str, seq: int, digest: str = "") -> dict:
    return {
        "audience": audience,
        "ledger_id": f"ledger-{audience}",
        "key_fingerprint": key,
        "seal_seq": seq,
        "prev_seq": seq - 1 if seq > 1 else 0,
        "prev_content_digest": digest or "genesis",
        "content_digest": f"digest-{audience}-{seq}",
        "workflow_id": f"wf-{seq}",
        "manifest_hash": f"m-{audience}-{seq}",
        "file_sha256": f"f-{audience}-{seq}",
    }


def test_audience_precedence_and_normalisation():
    assert derive_audiences("Acme Bank", ["https://x.test/w/1"]) == ["customer:acme-bank"]
    assert derive_audiences(None, ["https://cloud.epilabs.org/w/inb_123456"]) == ["cloud:inb_123456"]
    a = derive_audiences(None, ["https://Witness.Example.COM:443/customer/"])
    b = derive_audiences(None, ["https://witness.example.com/customer"])
    assert a == b and a[0].startswith("url:")
    assert derive_audiences(None, []) == ["local:unwitnessed"]


def test_two_customers_do_not_create_holes_for_each_other():
    key = "key1"
    a, b = "customer:bank-a", "customer:bank-b"
    # Each audience has its own 1..n. A's fifth seal is #4 in A's chain; B's
    # only seal is #1 in B's chain — neither is a hole in the other.
    a_entries = [_entry(key, a, s) for s in (1, 2, 3, 4)]
    b_entries = [_entry(key, b, 1)]
    both = analyze(a_entries + b_entries)
    assert all(not chain["missing"] for chain in both["chains"]), both
    assert analyze(a_entries)["chains"][0]["missing"] == []
    assert analyze(b_entries)["chains"][0]["missing"] == []


def test_withholding_one_seal_hits_only_that_customer():
    key = "key1"
    a, b = "customer:bank-a", "customer:bank-b"
    # A withheld its #3 but sent #4, so the gap is visible inside A's chain.
    a_sent = [_entry(key, a, s) for s in (1, 2, 4)]
    b_sent = [_entry(key, b, s) for s in (1, 2)]
    assert analyze(a_sent)["chains"][0]["missing"] == [3]
    assert analyze(b_sent)["chains"][0]["missing"] == []


def test_unwitnessed_seals_do_not_hole_a_customer_chain(tmp_path, monkeypatch):
    key = "key1"
    monkeypatch.setenv("EPI_SEAL_LEDGER_DIR", str(tmp_path / "ledger"))
    first = allocate(key, "local:unwitnessed")
    assert first and first["seq"] == 1
    a1 = allocate(key, "customer:bank-a")
    assert a1 and a1["seq"] == 1  # its own chain starts at 1


def _seal_two_audiences(tmp_path: Path, key: Ed25519PrivateKey) -> tuple[Path, dict]:
    work = tmp_path / "work"
    work.mkdir()
    (work / "steps.jsonl").write_text(
        json.dumps({"index": 0, "kind": "custom.test", "content": {"n": 1}}) + "\n",
        encoding="utf-8",
    )
    entries: dict[str, dict] = {}
    out = tmp_path / "two.epi"
    # Keep the test's ledger isolated from the developer's home.
    EPIContainer.pack(
        work,
        ManifestModel(goal="two audiences"),
        out,
        signer_function=lambda current: sign_manifest(current, key, "k"),
        seal_fingerprint=fingerprint_for_private_key(key),
        audiences=["customer:bank-a", "customer:bank-b"],
        seal_entries=entries,
        generate_analysis=False,
        embed_viewer=False,
        notarize=False,
    )
    return out, entries


def test_file_with_two_audiences_reveals_only_commitments(tmp_path):
    import os

    os.environ["EPI_SEAL_LEDGER_DIR"] = str(tmp_path / "ledger")
    out, entries = _seal_two_audiences(tmp_path, Ed25519PrivateKey.generate())
    assert set(entries) == {"customer:bank-a", "customer:bank-b"}

    manifest = EPIContainer.read_manifest(out)
    assert manifest.seal_chain is None, "a shared file must not carry a reader's chain in the clear"
    commitments = manifest.seal_chains or []
    assert len(commitments) == 2
    blob = json.dumps(commitments)
    assert "bank-a" not in blob and "bank-b" not in blob and '"seq"' not in blob

    for entry in entries.values():
        assert verify_commitment(entry, commitments)


def test_single_audience_keeps_the_plaintext_chain(tmp_path):
    import os

    os.environ["EPI_SEAL_LEDGER_DIR"] = str(tmp_path / "ledger")
    work = tmp_path / "single"
    work.mkdir()
    (work / "steps.jsonl").write_text(json.dumps({"index": 0, "kind": "x", "content": {}}) + "\n", encoding="utf-8")
    key = Ed25519PrivateKey.generate()
    entries: dict[str, dict] = {}
    out = tmp_path / "one.epi"
    EPIContainer.pack(
        work,
        ManifestModel(goal="one audience"),
        out,
        signer_function=lambda current: sign_manifest(current, key, "k"),
        seal_fingerprint=fingerprint_for_private_key(key),
        audiences=["customer:bank-a"],
        seal_entries=entries,
        generate_analysis=False,
        embed_viewer=False,
        notarize=False,
    )
    manifest = EPIContainer.read_manifest(out)
    assert manifest.seal_chain is not None
    assert manifest.seal_chain.seq == 1
    assert manifest.seal_chain.audience == "customer:bank-a"
    assert manifest.seal_chains is None
