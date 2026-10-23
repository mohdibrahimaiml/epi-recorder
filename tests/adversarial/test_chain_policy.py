"""Adversarial: the step hash chain is the ordering guarantee — strict needs it.

The ``prev_hash`` chain is what proves the recorded steps were not reordered
or dropped. An artifact whose steps carry **no links at all** proves nothing
about order: a producer can reorder the timeline, drop a step, and re-sign,
and the file still verifies — the chain check passes *vacuously*.

``epi verify --policy strict`` is documented as the claim-ready policy
("rely on the exit code only with --policy strict"). It must therefore FAIL an
artifact with no chain, not PASS it with a warning nobody reads.

The steps used here are otherwise complete (every ``tool.call`` has a
``tool.response``, every ``llm.request`` has an ``llm.response``) and the
signing key is pinned, so identity and completeness both pass. The chain is
the only thing missing — which is exactly the point.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.trust import sign_manifest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

runner = CliRunner()

FIXED_TS = "2026-04-12T00:00:00Z"


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _make_chainless_workspace(tmp_path: Path) -> Path:
    """A workspace whose steps are complete but carry no prev_hash links."""
    workspace = tmp_path / "chainless_workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    steps = [
        {
            "index": 0,
            "timestamp": FIXED_TS,
            "kind": "llm.request",
            "span_id": "s1",
            "content": {"provider": "local-fake", "model": "offline-test-model",
                        "messages": [{"role": "user", "content": "hello"}]},
        },
        {
            "index": 1,
            "timestamp": "2026-04-12T00:00:01Z",
            "kind": "llm.response",
            "span_id": "s1",
            "content": {"provider": "local-fake", "model": "offline-test-model",
                        "text": "hi"},
        },
        {
            "index": 2,
            "timestamp": "2026-04-12T00:00:02Z",
            "kind": "tool.call",
            "content": {"call_id": "c1", "tool": "lookup", "input": {"id": "A-1"}},
        },
        {
            "index": 3,
            "timestamp": "2026-04-12T00:00:03Z",
            "kind": "tool.response",
            "content": {"call_id": "c1", "tool": "lookup", "ok": True},
        },
        {
            "index": 4,
            "timestamp": "2026-04-12T00:00:04Z",
            "kind": "agent.decision",
            "content": {"decision": "proceed"},
        },
    ]
    (workspace / "steps.jsonl").write_text(
        "\n".join(json.dumps(step, sort_keys=True) for step in steps) + "\n",
        encoding="utf-8",
    )
    _write_json(workspace / "environment.json", {"python": "test", "offline": True})
    return workspace


@pytest.fixture
def chainless_signed_epi(tmp_path: Path):
    """A signed, complete, but chainless .epi, with its key pinned."""
    workspace = _make_chainless_workspace(tmp_path)
    key = Ed25519PrivateKey.generate()
    manifest = ManifestModel(
        cli_command="pytest helper",
        goal="Capture a decision without a hash chain",
        notes="Offline deterministic test artifact",
        tags=["test", "offline"],
    )
    output_path = tmp_path / "chainless.epi"
    EPIContainer.pack(
        workspace,
        manifest,
        output_path,
        signer_function=lambda item: sign_manifest(item, key, "producer"),
        preserve_generated=True,
        generate_analysis=False,
    )

    trusted = tmp_path / "trusted_keys"
    trusted.mkdir()
    pub_hex = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    (trusted / "producer.pub").write_text(pub_hex, encoding="utf-8")

    return output_path, trusted


def test_chainless_artifact_is_not_chain_intact(chainless_signed_epi):
    """Precondition: the chain check passes vacuously on a chainless file."""
    artifact, _trusted = chainless_signed_epi

    result = runner.invoke(app, ["verify", str(artifact), "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)

    # The chain check reports "ok" even though there is no chain at all.
    assert report["facts"]["chain_ok"] is True


def test_strict_policy_fails_artifact_without_step_chain(chainless_signed_epi, monkeypatch):
    """--policy strict is the claim-ready policy: no chain means no ordering claim."""
    artifact, trusted = chainless_signed_epi
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trusted))
    monkeypatch.setenv("EPI_KEYS_DIR", str(trusted.parent / "empty_keys"))

    result = runner.invoke(app, ["verify", str(artifact), "--policy", "strict", "--json"])
    report = json.loads(result.stdout)

    # Preconditions: everything else is fine.
    assert report["facts"]["integrity_ok"] is True
    assert report["facts"]["signature_valid"] is True
    assert report["identity"]["status"] == "KNOWN"
    assert report["facts"]["completeness_ok"] is True

    # The chain is the only thing missing — strict must not pass it.
    assert report["decision"]["status"] == "FAIL", report["decision"]
    assert result.exit_code != 0, result.output


def test_standard_policy_does_not_pass_chainless_artifact(chainless_signed_epi, monkeypatch):
    """Standard may WARN, but it must never print a clean PASS for a file
    whose step order is unprovable."""
    artifact, trusted = chainless_signed_epi
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trusted))
    monkeypatch.setenv("EPI_KEYS_DIR", str(trusted.parent / "empty_keys"))

    result = runner.invoke(app, ["verify", str(artifact), "--json"])
    report = json.loads(result.stdout)

    assert report["decision"]["status"] in ("WARN", "FAIL"), report["decision"]
    reason = report["decision"]["reason"]
    assert "chain" in reason.lower(), reason
