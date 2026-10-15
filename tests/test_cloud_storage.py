"""`epi cloud storage` (show/set/test/flush) against a fake transport."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.cloud import app


class FakeResponse:
    def __init__(self, status: int, payload=None):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload or {})

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("err", request=None, response=self)


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.calls: list[dict] = []
        self.routes: dict[tuple[str, str], FakeResponse] = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _call(self, method: str, url: str, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        for (m, suffix), res in self.routes.items():
            if m == method and url.endswith(suffix):
                return res
        return FakeResponse(404, {})

    def get(self, url, **kwargs):
        return self._call("GET", url, **kwargs)

    def put(self, url, **kwargs):
        return self._call("PUT", url, **kwargs)


def _client_with(routes: dict):
    def patched_init(self, *args, **kwargs):
        FakeClient.instances.append(self)
        self.calls = []
        self.routes = routes

    return type("CannedClient", (FakeClient,), {"__init__": patched_init})


FakeClient.instances: list[FakeClient] = []


def _invoke(args: list[str]):
    return CliRunner().invoke(app, args)


@pytest.fixture()
def home(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    for var in ("EPI_CLOUD_URL", "EPI_CLOUD_ORG", "EPI_CLOUD_API_KEY",
                "EPI_STORAGE_URL", "EPI_STORAGE_ENDPOINT",
                "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def _authed(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "Client", _client_with({
        ("GET", "storage-target"): FakeResponse(200, {"target": {
            "kind": "s3", "endpoint": "https://s3.us-east-1.amazonaws.com",
            "bucket": "acme-epi", "region": "us-east-1", "prefix": "runs",
            "object_lock": "unknown", "last_check_at": None, "last_check_ok": None,
        }}),
        ("PUT", "storage-target"): FakeResponse(200, {"ok": True}),
    }))
    return ["--url", "https://cloud.test", "--org", "o1", "--api-key", "epik_x"]


def test_storage_show_and_set(monkeypatch, home):
    base = _authed(monkeypatch)
    out = _invoke(["storage", "show", *base])
    assert out.exit_code == 0, out.output
    assert "acme-epi" in out.output
    out = _invoke(["storage", "set", "s3://other/p", *base])
    assert out.exit_code == 0, out.output
    assert "other" in out.output
    out = _invoke(["storage", "set", "https://not-s3/x", *base])
    assert out.exit_code == 2


def test_storage_flush_empty_and_pending(monkeypatch, home, tmp_path: Path):
    out = _invoke(["storage", "flush"])
    assert out.exit_code == 0, out.output
    assert "Nothing pending" in out.output
    from epi_core import storage_sink as sink

    target = sink.parse_storage_url("s3://mybucket/p")
    sink.queue_storage_upload(str(tmp_path / "gone.epi"), "abc", target)
    monkeypatch.setenv("EPI_STORAGE_TIMEOUT", "1")
    out = _invoke(["storage", "flush"])
    assert out.exit_code == 1  # dead endpoint: stays queued
    assert sink.pending_uploads() != []
