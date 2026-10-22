"""Adversarial: a self-asserted identity must never be described as pinned.

`manifest.governance.did` is written by whoever seals the file. Under the
default (`standard`) policy the verifier resolves that DID, and if the
resolved document lists the file's own embedded public key, the identity
becomes KNOWN.

The trust anchor there is a server the file's own author controls — the
signer vouches for themselves. That is not a pin the verifier chose.

Before this fix the human-readable report printed::

    ✔ SEAL · IDENTITY PINNED
      - Status:       KNOWN

for exactly that case: a file that is 100% attacker-authored, signed with an
attacker-generated key, published at the attacker's own domain, reading as a
green, pinned, PASSing artifact. The policy decision itself is a documented
trade-off (see docs/VERIFICATION_CONTRACT.md), but the *words* were a false
claim, and the words are what a skimming reviewer reads.

These tests pin:
* a DID-resolved identity is never labelled "PINNED" and is labelled
  SELF-ASSERTED,
* a genuine local pin still says "IDENTITY PINNED",
* `identity.pin_source` reports the source explicitly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.serialize import canonical_format_for, hash_normalized_dict, model_dict_for_hash
from epi_core.trust import sign_manifest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

runner = CliRunner()

ATTACKER_DID = "did:web:attacker.example"


def _chain(steps: list[dict]) -> list[dict]:
    from epi_core.schemas import StepModel

    fmt = canonical_format_for("4.6.2")
    out: list[dict] = []
    for i, step in enumerate(steps):
        step = dict(step)
        if i == 0:
            step["prev_hash"] = "CHAIN_START"
        else:
            prev = StepModel(**out[i - 1])
            step["prev_hash"] = hash_normalized_dict(model_dict_for_hash(prev), fmt)
        out.append(step)
    return out


def _build(tmp_path: Path, *, did: str | None, name: str = "case.epi") -> tuple[Path, str]:
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    steps = _chain([
        {"index": 0, "timestamp": "2026-04-12T00:00:00Z", "kind": "llm.request",
         "span_id": "s1", "content": {"provider": "x", "model": "m", "messages": []}},
        {"index": 1, "timestamp": "2026-04-12T00:00:01Z", "kind": "llm.response",
         "span_id": "s1", "content": {"provider": "x", "model": "m", "text": "hi"}},
    ])
    (workspace / "steps.jsonl").write_text(
        "\n".join(json.dumps(s, sort_keys=True) for s in steps) + "\n", encoding="utf-8"
    )
    (workspace / "environment.json").write_text(
        json.dumps({"python": "test"}), encoding="utf-8"
    )

    key = Ed25519PrivateKey.generate()
    pub_hex = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    ).hex()
    manifest = ManifestModel(
        cli_command="pytest helper",
        goal="A perfectly legitimate run",
        governance={"did": did} if did else {},
    )
    out = tmp_path / name
    EPIContainer.pack(
        workspace,
        manifest,
        out,
        signer_function=lambda item: sign_manifest(item, key, "signer"),
        preserve_generated=True,
        generate_analysis=False,
    )
    return out, pub_hex


@pytest.fixture
def attacker_did_resolves(monkeypatch):
    """The attacker's own domain serves a DID document listing their own key."""
    import epi_core.did_web as did_web

    state = {"pub_hex": None}

    def _resolve(did, timeout=10):
        return {
            "id": did,
            "verificationMethod": [{
                "id": f"{did}#key-1",
                "type": "Ed25519VerificationKey2020",
                "controller": did,
                "publicKeyHex": state["pub_hex"],
            }],
        }

    monkeypatch.setattr(did_web, "resolve_did_web", _resolve)
    return state


def test_self_asserted_identity_is_not_described_as_pinned(tmp_path, attacker_did_resolves):
    artifact, pub_hex = _build(tmp_path, did=ATTACKER_DID)
    attacker_did_resolves["pub_hex"] = pub_hex

    result = runner.invoke(app, ["verify", str(artifact)])
    assert result.exit_code == 0, result.output
    out = result.output

    assert "IDENTITY PINNED" not in out, out
    assert "SELF-ASSERTED" in out, out
    assert "--policy strict" in out, out


def test_self_asserted_identity_is_reported_as_self_asserted_in_json(tmp_path, attacker_did_resolves):
    artifact, pub_hex = _build(tmp_path, did=ATTACKER_DID)
    attacker_did_resolves["pub_hex"] = pub_hex

    result = runner.invoke(app, ["verify", str(artifact), "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)

    assert report["identity"]["status"] == "KNOWN"
    assert report["identity"]["pin_source"] == "did_web"
    # The policy decision itself is unchanged — this is a wording fix, not a
    # change to the documented trust model.
    assert report["decision"]["status"] == "PASS"


def test_real_local_pin_still_says_identity_pinned(tmp_path, monkeypatch):
    """A key the verifier actually pinned must keep its green chrome."""
    artifact, pub_hex = _build(tmp_path, did=None)

    trusted = tmp_path / "trusted_keys"
    trusted.mkdir()
    (trusted / "acme.pub").write_text(pub_hex, encoding="utf-8")
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trusted))

    result = runner.invoke(app, ["verify", str(artifact)])
    assert result.exit_code == 0, result.output
    out = result.output

    assert "IDENTITY PINNED" in out, out
    assert "SELF-ASSERTED" not in out, out

    report_result = runner.invoke(app, ["verify", str(artifact), "--json"])
    report = json.loads(report_result.stdout)
    assert report["identity"]["pin_source"] == "local_pin"


def test_strict_policy_still_fails_a_self_asserted_identity(tmp_path, attacker_did_resolves):
    """The documented defence must keep working."""
    artifact, pub_hex = _build(tmp_path, did=ATTACKER_DID)
    attacker_did_resolves["pub_hex"] = pub_hex

    result = runner.invoke(app, ["verify", str(artifact), "--policy", "strict", "--json"])
    assert result.exit_code != 0, result.output
    report = json.loads(result.stdout)
    assert report["decision"]["status"] == "FAIL"
    assert report["identity"]["status"] == "UNKNOWN"
