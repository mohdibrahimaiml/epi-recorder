import hashlib
import json
import zipfile
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from typer.testing import CliRunner

from epi_cli.main import app
from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now
from epi_core.trust import sign_manifest


runner = CliRunner()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_epi(tmp_path: Path, *, signed: bool = False, invalid_signature: bool = False) -> Path:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    steps = b'{"index":0,"kind":"test","content":{"ok":true}}\n'
    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=utc_now(),
        cli_command="python demo.py",
        file_manifest={"steps.jsonl": _sha256(steps)},
    )
    if signed:
        key = Ed25519PrivateKey.generate()
        manifest = sign_manifest(manifest, key, "default")
    if invalid_signature:
        manifest = ManifestModel(
            **{
                **manifest.model_dump(),
                "signature": "ed25519:default:" + ("aa" * 64),
                "public_key": "bb" * 32,
            }
        )

    artifact = tmp_path / "case.epi"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("mimetype", "application/vnd.epi+zip")
        archive.writestr("manifest.json", manifest.model_dump_json())
        archive.writestr("steps.jsonl", steps)
        archive.writestr("viewer.html", "<html></html>")
    return artifact


class _MockHttpResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_share_rejects_nonexistent_file():
    result = runner.invoke(app, ["share", "missing.epi"])
    assert result.exit_code == 1
    assert "file not found" in result.stdout.lower()


def test_share_rejects_oversize_file(tmp_path):
    oversize = tmp_path / "oversize.epi"
    oversize.write_bytes(b"x" * ((5 * 1024 * 1024) + 1))

    result = runner.invoke(app, ["share", str(oversize)])
    assert result.exit_code == 1
    assert "share limit" in result.stdout.lower()


def test_share_rejects_invalid_or_tampered_artifact(tmp_path):
    artifact = _make_epi(tmp_path, signed=True, invalid_signature=True)

    result = runner.invoke(app, ["share", str(artifact)])
    assert result.exit_code == 1
    assert "signature" in result.stdout.lower()


def test_share_success_prints_hosted_url(tmp_path):
    artifact = _make_epi(tmp_path, signed=False)
    payload = {
        "id": "abc123",
        "url": "https://epilabs.org/cases/?id=abc123",
        "expires_at": "2026-04-29T00:00:00Z",
        "size_bytes": artifact.stat().st_size,
        "signature_status": "unsigned",
        "signer": None,
        "steps_count": 1,
    }

    with patch("epi_cli.share.urllib.request.urlopen", return_value=_MockHttpResponse(payload)):
        with patch("epi_cli.share.webbrowser.open") as mock_open:
            result = runner.invoke(app, ["share", str(artifact)])

    assert result.exit_code == 0, result.output
    assert "https://epilabs.org/cases/?id=abc123" in result.stdout
    assert "no epi install needed" in result.stdout.lower()
    mock_open.assert_called_once_with("https://epilabs.org/cases/?id=abc123")


def test_share_no_open_suppresses_browser_launch(tmp_path):
    artifact = _make_epi(tmp_path, signed=False)
    payload = {
        "id": "abc123",
        "url": "https://epilabs.org/cases/?id=abc123",
        "expires_at": "2026-04-29T00:00:00Z",
        "size_bytes": artifact.stat().st_size,
        "signature_status": "unsigned",
        "signer": None,
        "steps_count": 1,
    }

    with patch("epi_cli.share.urllib.request.urlopen", return_value=_MockHttpResponse(payload)):
        with patch("epi_cli.share.webbrowser.open") as mock_open:
            result = runner.invoke(app, ["share", str(artifact), "--no-open"])

    assert result.exit_code == 0, result.output
    mock_open.assert_not_called()


def test_share_warns_when_browser_open_fails(tmp_path):
    artifact = _make_epi(tmp_path, signed=False)
    payload = {
        "id": "abc123",
        "url": "https://epilabs.org/cases/?id=abc123",
        "expires_at": "2026-04-29T00:00:00Z",
        "size_bytes": artifact.stat().st_size,
        "signature_status": "unsigned",
        "signer": None,
        "steps_count": 1,
    }

    with patch("epi_cli.share.urllib.request.urlopen", return_value=_MockHttpResponse(payload)):
        with patch("epi_cli.share.webbrowser.open", side_effect=RuntimeError("no browser")):
            result = runner.invoke(app, ["share", str(artifact)])

    assert result.exit_code == 0, result.output
    assert "could not open your browser automatically" in result.stdout.lower()


def test_share_json_output_is_machine_readable(tmp_path):
    artifact = _make_epi(tmp_path, signed=True)
    payload = {
        "id": "json123",
        "url": "https://epilabs.org/cases/?id=json123",
        "expires_at": "2026-04-29T00:00:00Z",
        "size_bytes": artifact.stat().st_size,
        "signature_status": "verified",
        "signer": "default",
        "steps_count": 1,
    }

    with patch("epi_cli.share.urllib.request.urlopen", return_value=_MockHttpResponse(payload)):
        with patch("epi_cli.share.webbrowser.open") as mock_open:
            result = runner.invoke(app, ["share", str(artifact), "--json"])

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.stdout)
    assert parsed["id"] == "json123"
    assert parsed["signature_status"] == "verified"
    mock_open.assert_not_called()


def test_share_respects_api_base_url_override(tmp_path):
    artifact = _make_epi(tmp_path)
    captured = {}
    payload = {
        "id": "override123",
        "url": "https://epilabs.org/cases/?id=override123",
        "expires_at": "2026-04-29T00:00:00Z",
        "size_bytes": artifact.stat().st_size,
        "signature_status": "unsigned",
        "signer": None,
        "steps_count": 1,
    }

    def _mock_urlopen(request, timeout=30):
        captured["url"] = request.full_url
        return _MockHttpResponse(payload)

    with patch("epi_cli.share.urllib.request.urlopen", side_effect=_mock_urlopen):
        with patch("epi_cli.share.webbrowser.open"):
            result = runner.invoke(
                app,
                ["share", str(artifact), "--api-base-url", "https://example.test", "--expires", "7"],
            )

    assert result.exit_code == 0, result.output
    assert captured["url"] == "https://example.test/api/share?expires_days=7"


def test_share_resolves_bare_filename_from_default_recordings_dir(tmp_path, monkeypatch):
    artifact = _make_epi(tmp_path, signed=False)
    recordings_dir = tmp_path / "epi-recordings"
    recordings_dir.mkdir()
    target = recordings_dir / artifact.name
    target.write_bytes(artifact.read_bytes())
    monkeypatch.chdir(tmp_path)

    payload = {
        "id": "resolved123",
        "url": "https://epilabs.org/cases/?id=resolved123",
        "expires_at": "2026-04-29T00:00:00Z",
        "size_bytes": target.stat().st_size,
        "signature_status": "unsigned",
        "signer": None,
        "steps_count": 1,
    }

    with patch("epi_cli.share.urllib.request.urlopen", return_value=_MockHttpResponse(payload)):
        with patch("epi_cli.share.webbrowser.open") as mock_open:
            result = runner.invoke(app, ["share", artifact.name, "--no-open"])

    assert result.exit_code == 0, result.output
    assert "https://epilabs.org/cases/?id=resolved123" in result.stdout
    mock_open.assert_not_called()
