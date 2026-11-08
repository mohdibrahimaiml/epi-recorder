"""Forward compatibility: unknown manifest fields must not change the preimage.

The 4.9.0 verifier rebuilt the manifest through its own model, dropped fields
it did not know, and re-hashed — so any new top-level field read as tampered.
The 4.10.0 fix has two halves:

* new data lives in ``file_manifest`` members, never the manifest top level;
* the verifier hashes the manifest exactly as stored, keeping unknown fields.

These tests pin both.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.serialize import get_canonical_hash
from epi_core.trust import sign_manifest, verify_signature


def _public_raw(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _pack_signed(tmp_path: Path, manifest: ManifestModel) -> tuple[Path, Ed25519PrivateKey]:
    from epi_core.keys import fingerprint_for_private_key

    work = tmp_path / "work"
    work.mkdir()
    (work / "steps.jsonl").write_text(
        json.dumps({"index": 0, "kind": "custom.test", "content": {"n": 1}}) + "\n",
        encoding="utf-8",
    )
    key = Ed25519PrivateKey.generate()
    out = tmp_path / "future.epi"
    EPIContainer.pack(
        work,
        manifest,
        out,
        signer_function=lambda current: sign_manifest(current, key, "future"),
        container_format="legacy-zip",
        generate_analysis=False,
        embed_viewer=False,
        seal_fingerprint=fingerprint_for_private_key(key),
    )
    return out, key


def test_unknown_extra_field_is_kept_and_signed(tmp_path: Path) -> None:
    manifest = ManifestModel(goal="future", future_field={"new": [1, 2, 3]})
    key = Ed25519PrivateKey.generate()

    signed = sign_manifest(manifest, key, "future")

    # extra="allow": the field survives validation and serialization.
    assert signed.future_field == {"new": [1, 2, 3]}
    assert signed.model_dump()["future_field"] == {"new": [1, 2, 3]}
    assert verify_signature(signed, _public_raw(key))[0] is True

    # It is part of the hash, so a later edit is detectable.
    plain = sign_manifest(ManifestModel(goal="future"), key, "future")
    assert get_canonical_hash(signed, exclude_fields={"signature"}) != get_canonical_hash(
        plain, exclude_fields={"signature"}
    )


def test_packed_unknown_extra_field_survives_and_verifies(tmp_path: Path) -> None:
    out, key = _pack_signed(
        tmp_path,
        ManifestModel(goal="future", future_field={"new": [1, 2, 3]}),
    )

    with zipfile.ZipFile(out) as zf:
        stored = json.loads(zf.read("manifest.json"))
    assert stored["future_field"] == {"new": [1, 2, 3]}

    read_back = EPIContainer.read_manifest(out)
    assert read_back.future_field == {"new": [1, 2, 3]}
    valid, message = verify_signature(read_back, _public_raw(key))
    assert valid is True, message


def test_cli_verifies_unknown_extra_field(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from epi_cli.main import app as cli_app

    home = tmp_path / "home"
    (home / "keys").mkdir(parents=True)
    monkeypatch.setenv("EPI_HOME", str(home))
    monkeypatch.setenv("EPI_KEYS_DIR", str(home / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")

    out, _key = _pack_signed(
        tmp_path,
        ManifestModel(goal="future", future_field={"new": [1, 2, 3]}),
    )

    result = CliRunner().invoke(cli_app, ["verify", str(out), "--json"])
    assert result.exit_code in (0, 1), result.output
    payload = json.loads(result.stdout[result.stdout.index("{") :])
    assert payload["facts"]["signature_valid"] is True


def test_member_fields_never_reach_the_top_level(tmp_path: Path) -> None:
    from epi_core.manifest_members import MANIFEST_MEMBER_FIELDS
    from epi_core.schemas import ReleaseRefModel, SealChainModel

    out, _key = _pack_signed(
        tmp_path,
        ManifestModel(
            goal="future",
            case_id="CASE-1",
            record_kind="decision",
            seal_chain=SealChainModel(
                ledger_id="ledger-1",
                key_fingerprint="abcdef0123456789",
                seq=1,
                prev_seq=0,
                prev_content_digest="genesis",
            ),
            release_ref=ReleaseRefModel(release_id="rel-1", release_digest="d" * 64),
            runtime_components=[{"type": "policy", "name": "p"}],
        ),
    )

    with zipfile.ZipFile(out) as zf:
        stored = json.loads(zf.read("manifest.json"))
        members = set(zf.namelist())
    assert not (set(stored) & set(MANIFEST_MEMBER_FIELDS))
    assert "artifacts/case_id.json" in members
    assert "artifacts/seal_chain.json" in members
    assert "artifacts/record_kind.json" in members
    assert "artifacts/release_ref.json" in members
    # The member hashes are inside the signed file_manifest.
    for member in (
        "artifacts/case_id.json",
        "artifacts/seal_chain.json",
        "artifacts/record_kind.json",
        "artifacts/release_ref.json",
    ):
        assert member in stored["file_manifest"]
