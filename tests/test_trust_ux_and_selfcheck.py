"""Trust UX polish + offline crypto self-check + keys trust from .epi."""

from pathlib import Path

from typer.testing import CliRunner

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
    assert "selfVerifyEmbeddedCase" in viewer
    assert "self_check_pending" in viewer
    assert "OPEN VIA EPI VIEW TO VERIFY" not in viewer
    assert "trust_scorecard_v1" in viewer or "viewer_capabilities" in viewer
    assert "authority-ladder" in viewer or "trust-plain-summary" in viewer
    assert "epilabs.org/verify" in verify_txt
    assert "epi keys trust" in verify_txt or "SIMPLE PATH" in verify_txt
    assert "SIMPLE PATH" in verify_txt or "epi verify" in verify_txt


def test_crypto_js_exports_verify_manifest_signature():
    crypto = Path("epi_viewer_static/crypto.js").read_text(encoding="utf-8")
    assert "globalThis.verifyManifestSignature" in crypto
    assert "async function verifyManifestSignature" in crypto


def test_web_viewer_scorecard_and_partial_integrity_copy():
    js = Path("web_viewer/app.js").read_text(encoding="utf-8")
    html = Path("web_viewer/index.html").read_text(encoding="utf-8")
    # Simple path for normal users
    assert "renderTrustPlainSummary" in js
    assert "trust-plain-summary" in html
    assert "Seal looks OK" in js or "Looks good" in js
    # Power remains available, not front-and-center
    assert "integrity_scope" in js
    assert "archive_base64" in js
    assert "JSZip" in js
    assert "authority-ladder" in html
    assert "Advanced details" in html
    assert "epi keys trust" in html or "keys trust" in js


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

    result = runner.invoke(
        app,
        ["keys", "trust", str(epi), "--name", "from-cli", "--overwrite"],
    )
    assert result.exit_code == 0, result.output
    assert (trust_dir / "from-cli.pub").exists()
    assert "Trusted key" in result.output or "OK" in result.output
