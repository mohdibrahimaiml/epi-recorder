"""Org trust bundles v0 — issuance, offline verification, seal binding.

Covers design docs/design/org-trust-bundle.md §5 (steps 1-6):
valid steady state, stale bundles, tampered envelopes, foreign keys,
window violations, missing org_root, and the seal-time governance write.
No network anywhere in this file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from epi_cli.main import app
from epi_core.container import EPIContainer, EPI_CONTAINER_FORMAT_LEGACY
from epi_core.org_bundle import (
    fingerprint_pubkey,
    issue_bundle,
    load_bundle,
    save_bundle,
    verify_artifact_against_bundle,
)
from epi_core.schemas import ManifestModel
from epi_core.trust import sign_manifest
from tests.helpers.artifacts import make_decision_workspace

runner = CliRunner()
CREATED = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _keypair() -> tuple[Ed25519PrivateKey, str]:
    priv = Ed25519PrivateKey.generate()
    pub_hex = (
        priv.public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        .hex()
    )
    return priv, pub_hex


def _signed_manifest(seal_priv, org_root: str | None, created: datetime = CREATED) -> ManifestModel:
    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=created,
        cli_command="pytest org-bundle",
        governance={"org_root": org_root} if org_root else None,
    )
    return sign_manifest(manifest, seal_priv, "seal-2026")


def _pack(tmp_path: Path, manifest: ManifestModel, name: str = "org.epi") -> Path:
    workspace = make_decision_workspace(tmp_path)
    out = tmp_path / name
    EPIContainer.pack(
        workspace,
        manifest,
        out,
        signer_function=(lambda item: item),
        preserve_generated=True,
        container_format=EPI_CONTAINER_FORMAT_LEGACY,
        generate_analysis=False,
    )
    return out


def _issue(root_priv, root_pub, seal_pub, **kw) -> dict:
    params = {
        "bundle_id": "acme-corp",
        "keys": [
            {
                "key_id": "seal-2026",
                "public_key": seal_pub,
                "not_before": "2026-01-05T00:00:00Z",
            }
        ],
        "root_private_key": root_priv,
        "root_public_hex": root_pub,
        "version": 1,
        "issued_at": "2026-07-01T00:00:00Z",
    }
    params.update(kw)
    return issue_bundle(**params)


def test_issue_and_verify_valid():
    root_priv, root_pub = _keypair()
    seal_priv = Ed25519PrivateKey.generate()
    seal_pub = (
        seal_priv.public_key()
        .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        .hex()
    )
    manifest = _signed_manifest(seal_priv, fingerprint_pubkey(root_pub))
    bundle = _issue(root_priv, root_pub, seal_pub)
    report = verify_artifact_against_bundle(manifest, bundle)
    assert report["status"] == "VALID", report
    assert report["key_id"] == "seal-2026"


def test_stale_bundle_is_unknown_not_valid():
    root_priv, root_pub = _keypair()
    seal_priv = Ed25519PrivateKey.generate()
    seal_pub = (
        seal_priv.public_key()
        .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        .hex()
    )
    manifest = _signed_manifest(seal_priv, fingerprint_pubkey(root_pub))
    # Bundle issued BEFORE the artifact was sealed: cannot confirm history.
    bundle = _issue(root_priv, root_pub, seal_pub, issued_at="2026-01-01T00:00:00Z")
    report = verify_artifact_against_bundle(manifest, bundle)
    assert report["status"] == "UNKNOWN", report


def test_tampered_bundle_envelope_is_invalid():
    root_priv, root_pub = _keypair()
    seal_priv = Ed25519PrivateKey.generate()
    seal_pub = (
        seal_priv.public_key()
        .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        .hex()
    )
    manifest = _signed_manifest(seal_priv, fingerprint_pubkey(root_pub))
    bundle = _issue(root_priv, root_pub, seal_pub)
    bundle["keys"][0]["public_key"] = "00" + seal_pub[2:]
    report = verify_artifact_against_bundle(manifest, bundle)
    assert report["status"] == "INVALID", report


def test_foreign_sealing_key_is_unknown():
    root_priv, root_pub = _keypair()
    _, seal_pub = _keypair()
    foreign_priv = Ed25519PrivateKey.generate()
    manifest = _signed_manifest(foreign_priv, fingerprint_pubkey(root_pub))
    bundle = _issue(root_priv, root_pub, seal_pub)
    report = verify_artifact_against_bundle(manifest, bundle)
    assert report["status"] == "UNKNOWN", report


def test_window_violations_are_invalid():
    root_priv, root_pub = _keypair()
    seal_priv = Ed25519PrivateKey.generate()
    seal_pub = (
        seal_priv.public_key()
        .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        .hex()
    )
    manifest = _signed_manifest(seal_priv, fingerprint_pubkey(root_pub))
    # Key validity starts after sealing.
    bundle = _issue(root_priv, root_pub, seal_pub)
    bundle["keys"][0]["not_before"] = "2026-08-01T00:00:00Z"
    bundle = issue_bundle(
        bundle_id=bundle["bundle_id"],
        keys=bundle["keys"],
        root_private_key=root_priv,
        root_public_hex=root_pub,
        version=2,
        issued_at="2026-07-01T00:00:00Z",
    )
    report = verify_artifact_against_bundle(manifest, bundle)
    assert report["status"] == "INVALID", report
    # Key validity ended before sealing.
    bundle = _issue(root_priv, root_pub, seal_pub)
    bundle["keys"][0]["not_after"] = "2026-05-01T00:00:00Z"
    bundle = issue_bundle(
        bundle_id=bundle["bundle_id"],
        keys=bundle["keys"],
        root_private_key=root_priv,
        root_public_hex=root_pub,
        version=3,
        issued_at="2026-07-01T00:00:00Z",
    )
    report = verify_artifact_against_bundle(manifest, bundle)
    assert report["status"] == "INVALID", report


def test_missing_org_root_is_unknown():
    root_priv, root_pub = _keypair()
    seal_priv = Ed25519PrivateKey.generate()
    seal_pub = (
        seal_priv.public_key()
        .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        .hex()
    )
    manifest = _signed_manifest(seal_priv, None)
    bundle = _issue(root_priv, root_pub, seal_pub)
    report = verify_artifact_against_bundle(manifest, bundle)
    assert report["status"] == "UNKNOWN", report


def test_wrong_format_rejected():
    manifest = _signed_manifest(Ed25519PrivateKey.generate(), "0" * 64)
    report = verify_artifact_against_bundle(manifest, {"format": "nope"})
    assert report["status"] == "INVALID"


def test_seal_writes_org_root(tmp_path: Path):
    """record(org_root=...) binds the fingerprint into manifest.governance."""
    from epi_recorder import record

    root_priv, root_pub = _keypair()
    fingerprint = fingerprint_pubkey(root_pub)
    out = tmp_path / "orgroot.epi"
    with record(str(out), workflow_name="org-root-test", org_root=fingerprint) as session:
        session.log_step("custom.test", {"ok": True})
    manifest = EPIContainer.read_manifest(out)
    assert (manifest.governance or {}).get("org_root") == fingerprint


def test_cli_issue_and_verify_roundtrip(tmp_path: Path):
    root_priv, root_pub = _keypair()
    seal_priv = Ed25519PrivateKey.generate()
    seal_pub = (
        seal_priv.public_key()
        .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        .hex()
    )
    root_pem = tmp_path / "root.pem"
    root_pem.write_bytes(
        root_priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    bundle_path = tmp_path / "org-bundle.json"
    r = runner.invoke(
        app,
        [
            "org", "bundle", "issue",
            "--bundle-id", "acme-corp",
            "--root-key", str(root_pem),
            "--key", f"seal-2026={seal_pub}",
            "--not-before", "2026-01-05T00:00:00Z",
            "--out", str(bundle_path),
        ],
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    saved = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert saved["format"] == "epi-org-bundle-v1"

    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=CREATED,
        cli_command="pytest org-bundle",
        governance={"org_root": fingerprint_pubkey(root_pub)},
    )
    workspace = make_decision_workspace(tmp_path)
    epi_path = tmp_path / "org.epi"
    EPIContainer.pack(
        workspace,
        manifest,
        epi_path,
        signer_function=(lambda item: sign_manifest(item, seal_priv, "seal-2026")),
        preserve_generated=True,
        container_format=EPI_CONTAINER_FORMAT_LEGACY,
        generate_analysis=False,
    )
    r2 = runner.invoke(app, ["org", "bundle", "verify", str(epi_path), str(bundle_path)])
    assert r2.exit_code == 0, r2.stdout + r2.stderr
    assert "VALID" in r2.stdout

    r3 = runner.invoke(app, ["org", "bundle", "verify", str(epi_path), str(bundle_path), "--json"])
    assert r3.exit_code == 0, r3.stdout + r3.stderr
    assert json.loads(r3.stdout)["status"] == "VALID"
