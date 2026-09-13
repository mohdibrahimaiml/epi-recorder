"""Smoke tests for epi enterprise bootstrap / kit / capabilities."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from epi_cli.main import app
from epi_core.keys import KeyManager
from epi_recorder import get_current_session, record

runner = CliRunner()


def test_enterprise_capabilities() -> None:
    r = runner.invoke(app, ["enterprise", "capabilities"])
    assert r.exit_code == 0
    assert "Shipped today" in r.stdout
    assert "bootstrap" in r.stdout


def test_enterprise_bootstrap_refuses_without_org_pubkey(tmp_path: Path) -> None:
    """Bootstrap must never generate the customer's private key.

    Without --org-pubkey it refuses with instructions instead of creating
    key material. This is structural: the tool is incapable of seeing a
    customer private key in this flow.
    """
    out = tmp_path / "kit"
    r = runner.invoke(
        app,
        ["enterprise", "bootstrap", "--out", str(out), "--force"],
    )
    assert r.exit_code == 2, r.stdout + r.stderr
    assert "org-pubkey" in r.stdout + r.stderr
    assert "never" in (r.stdout + r.stderr).lower() or "private" in (r.stdout + r.stderr).lower()


def test_enterprise_bootstrap_and_kit(tmp_path: Path) -> None:
    # Simulate customer hardware: generate there, hand over public half only.
    customer_km = KeyManager(keys_dir=tmp_path / "customer-keys")
    _, customer_pub = customer_km.generate_keypair("org-seal")

    out = tmp_path / "kit"
    key = "ent-cli-test"
    r = runner.invoke(
        app,
        [
            "enterprise",
            "bootstrap",
            "--out",
            str(out),
            "--key-name",
            key,
            "--org-pubkey",
            str(customer_pub),
            "--force",
        ],
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    assert (out / "README.md").exists()
    assert (out / "epi_policy.json").exists()
    assert (out / "org-trust-bundle.zip").exists()
    assert (out / ".github" / "workflows" / "epi-enterprise-verify.yml").exists()

    # Bundle holds exactly the customer-supplied public key — nothing swept
    # in from the local signing namespace, no private material anywhere.
    import zipfile

    customer_hex = customer_km.load_public_key("org-seal").hex()
    with zipfile.ZipFile(out / "org-trust-bundle.zip") as zf:
        names = zf.namelist()
        assert names.count(f"keys/enterprise-{key}.pub") == 1
        assert [n for n in names if n.startswith("keys/")] == [f"keys/enterprise-{key}.pub"]
        assert zf.read(f"keys/enterprise-{key}.pub").decode().strip() == customer_hex
    bundle_bytes = (out / "org-trust-bundle.zip").read_bytes()
    assert b"PRIVATE" not in bundle_bytes
    assert customer_pub.read_bytes() not in bundle_bytes  # PEM form never embedded

    epi = tmp_path / "run.epi"
    with record(str(epi), goal="enterprise test"):
        s = get_current_session()
        s.log("decision", ok=True)

    pack = tmp_path / "auditor-pack.zip"
    r2 = runner.invoke(
        app,
        ["enterprise", "kit", str(epi), "--out", str(pack)],
    )
    assert r2.exit_code == 0, r2.stdout + r2.stderr
    assert pack.exists() and pack.stat().st_size > 1000
