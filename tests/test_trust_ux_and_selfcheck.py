"""Trust UX polish + offline crypto self-check + keys trust from .epi."""

from pathlib import Path

from typer.testing import CliRunner

from tests.helpers.repo_paths import require_repo_file

from epi_cli.main import app
from epi_core.container import EPIContainer
from epi_core.keys import KeyManager
from epi_core.trust import TrustRegistry
from tests.helpers.artifacts import make_decision_epi

runner = CliRunner()


def test_verify_missing_file_shows_path_and_hosted_tips():
    result = runner.invoke(app, ["verify", "definitely_missing_xyz.epi"])
    assert result.exit_code != 0
    out = result.output
    assert "File not found" in out
    assert "full path" in out.lower() or "Tip:" in out
    assert "epilabs.org/verify" in out


def test_signed_envelope_viewer_includes_self_check_and_verify_txt_trust_hints(
    tmp_path: Path,
):
    epi, _ = make_decision_epi(
        tmp_path, name="trust_ux.epi", container_format="envelope-v2"
    )
    extract = tmp_path / "x"
    extract.mkdir()
    EPIContainer.unpack(epi, extract)
    viewer = (extract / "viewer.html").read_text(encoding="utf-8")
    verify_txt = (extract / "VERIFY.txt").read_text(encoding="utf-8")
    assert "boot-overlay" in viewer or "integrity-status" in viewer
    assert "epilabs.org/verify" in viewer or "epilabs.org" in viewer
    assert "verify" in verify_txt.lower()
    assert "SIMPLE PATH" in verify_txt or "EPI_FORENSIC_VERIFICATION_GUIDE" in verify_txt


def test_crypto_js_exports_verify_manifest_signature():
    crypto = require_repo_file("epi_viewer_static", "crypto.js").read_text(encoding="utf-8")
    assert "globalThis.verifyManifestSignature" in crypto
    assert "async function verifyManifestSignature" in crypto


def test_web_viewer_scorecard_and_partial_integrity_copy():
    js = require_repo_file("web_viewer", "app.js").read_text(encoding="utf-8")
    html = require_repo_file("web_viewer", "index.html").read_text(encoding="utf-8")
    assert "renderIntegrity" in js
    assert "integrity-status" in html
    assert "integrity_scope" in js or "integrity" in js
    assert "archive_base64" in js
    assert "JSZip" in js


def test_verify_warn_uses_yellow_not_red_fail_chrome(tmp_path: Path, monkeypatch):
    """Unknown sealer: WARN with UNVERIFIED IDENTITY chrome — never SEAL OK / red FAIL."""
    epi, _ = make_decision_epi(
        tmp_path, name="warn_chrome.epi", container_format="envelope-v2"
    )
    # Empty trust store so identity is not KNOWN
    trust_dir = tmp_path / "empty_trust"
    trust_dir.mkdir()
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trust_dir))
    # Isolate local keys so we don't get LOCAL from developer machine keys
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "no_local_keys"))

    result = runner.invoke(app, ["verify", str(epi)])
    out = result.output
    assert result.exit_code == 0, out
    assert "WARN" in out
    assert "UNVERIFIED IDENTITY" in out
    assert "SEAL OK" not in out
    # Must not present WARN as a red FAIL seal
    assert "✘ SEAL FAIL" not in out
    assert "Fingerprint:" in out or "fingerprint" in out.lower() or "Key ID" in out
    # Identity before seal proofs
    assert out.find("IDENTITY") < out.find("SEAL (Objective")


def test_local_key_match_sets_local_identity(tmp_path: Path, monkeypatch):
    from epi_core.trust import create_verification_report, apply_policy, VerificationPolicy
    from epi_core.container import EPIContainer

    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    monkeypatch.setenv("EPI_KEYS_DIR", str(keys_dir))
    km = KeyManager(keys_dir=keys_dir)
    km.generate_keypair("default", overwrite=True)

    epi, _ = make_decision_epi(
        tmp_path, name="local_match.epi", container_format="envelope-v2", signed=True
    )
    # Re-sign with our isolated key so public_key matches local
    from epi_core.trust import sign_manifest
    from epi_core.schemas import ManifestModel

    # make_decision_epi already signs with its own key — rebuild with our key
    workspace = tmp_path / "ws2"
    # Simpler: pack fresh with our signer
    from tests.helpers.artifacts import make_decision_workspace

    ws = make_decision_workspace(tmp_path / "w")
    out = tmp_path / "local_signed.epi"
    priv = km.load_private_key("default")
    EPIContainer.pack(
        ws,
        ManifestModel(cli_command="t", goal="local"),
        out,
        signer_function=lambda m: sign_manifest(m, priv, "default"),
    )
    manifest = EPIContainer.read_manifest(out)
    ok, _ = EPIContainer.verify_integrity(out)
    report = create_verification_report(
        integrity_ok=ok,
        signature_valid=True,
        signer_name=None,
        mismatches={},
        manifest=manifest,
        trusted_registry=None,
    )
    # Without registry, still detect LOCAL
    report = create_verification_report(
        integrity_ok=ok,
        signature_valid=True,
        signer_name=None,
        mismatches={},
        manifest=manifest,
        trusted_registry=TrustRegistry(trusted_keys_dir=tmp_path / "empty_t"),
    )
    (tmp_path / "empty_t").mkdir(exist_ok=True)
    report = create_verification_report(
        integrity_ok=ok,
        signature_valid=True,
        signer_name=None,
        mismatches={},
        manifest=manifest,
        trusted_registry=TrustRegistry(trusted_keys_dir=tmp_path / "empty_t"),
    )
    assert report["identity"]["status"] == "LOCAL"
    assert report["identity"].get("local_key_name") == "default"
    applied = apply_policy(report, VerificationPolicy.STANDARD)
    assert applied["decision"]["status"] == "WARN"
    reason = applied["decision"]["reason"]
    assert not reason.strip().upper().startswith("SEAL OK")
    assert "local" in reason.lower()


def test_keys_trust_from_epi_pins_manifest_public_key(tmp_path: Path, monkeypatch):
    epi, _key = make_decision_epi(
        tmp_path, name="pin_me.epi", container_format="envelope-v2"
    )
    trust_dir = tmp_path / "trusted_keys"
    trust_dir.mkdir()
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trust_dir))

    # Direct API (same code path CLI uses)
    km = KeyManager(keys_dir=tmp_path / "keys")
    target = km.trust_key(epi, trusted_keys_dir=trust_dir, trusted_name="sealer")
    assert target.exists()
    hex_key = target.read_text(encoding="utf-8").strip()
    assert len(hex_key) == 64

    manifest = EPIContainer.read_manifest(epi)
    assert manifest.public_key
    assert hex_key == manifest.public_key.lower()

    reg = TrustRegistry(trusted_keys_dir=trust_dir)
    ok, name, detail = reg.verify_key_trust(manifest.public_key, governance=None)
    assert ok is True
    assert name == "sealer"


def test_cli_keys_trust_from_epi(tmp_path: Path, monkeypatch):
    epi, _ = make_decision_epi(
        tmp_path, name="cli_pin.epi", container_format="envelope-v2"
    )
    trust_dir = tmp_path / "tk"
    trust_dir.mkdir()
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trust_dir))

    # Without the confirmed fingerprint: refused, nothing pinned.
    refused = runner.invoke(app, ["keys", "trust", str(epi), "--name", "from-cli"])
    assert refused.exit_code == 1
    assert not (trust_dir / "from-cli.pub").exists()

    from epi_core.container import EPIContainer
    from epi_core.keys import key_fingerprint

    fp = key_fingerprint(EPIContainer.read_manifest(epi).public_key)
    wrong = runner.invoke(
        app, ["keys", "trust", str(epi), "--name", "from-cli", "--fingerprint", "0000 0000 0000 0000"]
    )
    assert wrong.exit_code == 1

    result = runner.invoke(
        app,
        ["keys", "trust", str(epi), "--name", "from-cli", "--overwrite", "--fingerprint", fp],
    )
    assert result.exit_code == 0, result.output
    assert (trust_dir / "from-cli.pub").exists()
    assert "Trusted key" in result.output or "OK" in result.output
