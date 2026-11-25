"""P3 privacy claim: customer bucket credentials never reach EPI Cloud.

Claim (epi_core/storage_sink.py header): "EPI Cloud never sees these bytes or
credentials." Credentials live in env or ~/.aws/credentials and are used only
by the signed PUT to the customer's own bucket.

These tests set unique sentinel credentials and assert they appear in no
request to EPI Cloud, in the local Cloud config, or in the storage outbox.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.cloud import app
from epi_core import storage_sink

REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "website" / "assets" / "sample.epi"

ACCESS = "AKIA_PRIVACY_SENTINEL_ACCESS_KEY"
SECRET = "privacy-sentinel-secret-9f8e7d6c5b4a"
SESSION = "privacy-sentinel-session-token-001122334455"
SENTINELS = (ACCESS, SECRET, SESSION)


class FakeResponse:
    def __init__(self, status: int, payload=None, text: str = ""):
        self.status_code = status
        self._payload = payload
        self.text = text if text else json.dumps(payload or {})

    def json(self):
        return self._payload


class RecordingClient:
    """Records every request the CLI makes; no network."""

    calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        self.calls = []
        RecordingClient.calls.append(self.calls)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _call(self, method: str, url: str, **kwargs):
        body = kwargs.get("content")
        content_bytes = b""
        if hasattr(body, "read"):
            content_bytes = body.read()
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(kwargs.get("headers") or {}),
                "json": kwargs.get("json"),
                "content_bytes": content_bytes,
            }
        )
        if method == "POST" and url.endswith("init"):
            return FakeResponse(
                201,
                {
                    "id": "art_1",
                    "put_url": "/v1/orgs/o1/artifacts/art_1/content",
                    "witness_status": "witnessed",
                    "signature_check": "valid",
                },
            )
        if method == "PUT":
            return FakeResponse(200, {"stored": True})
        return FakeResponse(200, {})

    def get(self, url, **kwargs):
        return self._call("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._call("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self._call("PUT", url, **kwargs)


@pytest.fixture()
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    monkeypatch.setenv("EPI_CLOUD_URL", "https://cloud.test")
    monkeypatch.setenv("EPI_CLOUD_ORG", "o1")
    monkeypatch.setenv("EPI_CLOUD_API_KEY", "epik_privacy")
    monkeypatch.setenv("EPI_STORAGE_URL", "s3://customer-evidence")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", ACCESS)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", SECRET)
    monkeypatch.setenv("AWS_SESSION_TOKEN", SESSION)
    return tmp_path


@pytest.fixture()
def recorded(monkeypatch: pytest.MonkeyPatch, home: Path) -> list[RecordingClient]:
    import httpx

    RecordingClient.calls.clear()
    monkeypatch.setattr(httpx, "Client", RecordingClient)
    return RecordingClient.calls


def _push_and_collect(recorded) -> tuple[object, list[dict]]:
    result = CliRunner().invoke(app, ["push", str(SAMPLE), "--reason", "sample"])
    calls = [c for batch in recorded for c in batch]
    return result, calls


def test_push_sends_no_bucket_credentials(recorded) -> None:
    result, calls = _push_and_collect(recorded)
    assert result.exit_code == 0, result.output
    assert calls, "the push should have made at least one request"

    for call in calls:
        text = json.dumps(
            {
                "method": call["method"],
                "url": call["url"],
                "headers": call["headers"],
                "json": call["json"],
            }
        )
        for sentinel in SENTINELS:
            assert sentinel not in text, (
                f"bucket credential leaked to EPI Cloud in {call['method']} {call['url']}"
            )


def test_push_does_not_put_credentials_in_the_manifest(recorded) -> None:
    result, calls = _push_and_collect(recorded)
    assert result.exit_code == 0, result.output
    init = next(c for c in calls if c["method"] == "POST" and c["url"].endswith("init"))
    manifest_json = init["json"]["manifest_json"]
    for sentinel in SENTINELS:
        assert sentinel not in manifest_json


def test_cloud_config_file_holds_no_bucket_credentials(recorded, home: Path) -> None:
    result, _ = _push_and_collect(recorded)
    assert result.exit_code == 0, result.output
    config = home / "cloud.json"
    if config.exists():
        text = config.read_text(encoding="utf-8")
        for sentinel in SENTINELS:
            assert sentinel not in text


def test_storage_outbox_never_persists_secrets(home: Path) -> None:
    target = storage_sink.StorageTarget(
        endpoint="https://s3.example", bucket="customer-evidence", prefix="epi", region="us-east-1"
    )
    storage_sink.queue_storage_upload("C:/tmp/file.epi", "a" * 64, target)
    outbox = (home / "storage_outbox.jsonl").read_text(encoding="utf-8")
    for sentinel in SENTINELS:
        assert sentinel not in outbox
    assert "customer-evidence" in outbox


def test_storage_target_has_no_credential_fields() -> None:
    target = storage_sink.StorageTarget(
        endpoint="https://s3.example", bucket="b", prefix="", region="us-east-1"
    )
    assert set(vars(target)) == {"endpoint", "bucket", "prefix", "region"}


def test_credentials_repr_masks_the_secret(home: Path) -> None:
    creds = storage_sink.load_credentials()
    rendered = repr(creds)
    assert SECRET not in rendered
    assert "***" in rendered
    assert ACCESS in rendered  # an access key id is an identifier, not a secret
