"""`epi cloud push/status/login` against a fake transport (no network)."""

from __future__ import annotations

import hashlib
import json
import zlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.cloud import app, file_hashes, read_manifest, resolve_creds

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "website" / "assets" / "sample.epi"


class FakeResponse:
    def __init__(self, status: int, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text if text else json.dumps(payload or {})

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("err", request=None, response=self)


class FakeClient:
    """Records requests; canned responses per (method, path)."""

    instances: list[FakeClient] = []

    def __init__(self, *args, **kwargs):
        self.calls: list[dict] = []
        self.routes: dict[tuple[str, str], FakeResponse] = {}
        FakeClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _call(self, method: str, url: str, **kwargs):
        body = kwargs.get("content")
        if hasattr(body, "read"):
            kwargs["content_bytes"] = body.read()
        self.calls.append({"method": method, "url": url, **kwargs})
        for (m, suffix), res in self.routes.items():
            if m == method and url.endswith(suffix):
                return res
        return FakeResponse(404, {}, "no route")

    def get(self, url, **kwargs):
        return self._call("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._call("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self._call("PUT", url, **kwargs)


@pytest.fixture()
def fake_transport(monkeypatch):
    import httpx

    FakeClient.instances.clear()
    monkeypatch.setattr(httpx, "Client", FakeClient)
    return FakeClient


@pytest.fixture()
def home(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    for var in ("EPI_CLOUD_URL", "EPI_CLOUD_ORG", "EPI_CLOUD_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def _invoke(args: list[str]):
    return CliRunner().invoke(app, args)


def _client_with(routes: dict):
    def patched_init(self, *args, **kwargs):
        FakeClient.instances.append(self)
        self.calls = []
        self.routes = routes

    return type("CannedClient", (FakeClient,), {"__init__": patched_init})


def test_file_hashes_match_independent_computation():
    digest, crc, size = file_hashes(SAMPLE)
    raw = SAMPLE.read_bytes()
    assert digest == hashlib.sha256(raw).hexdigest()
    assert crc == (zlib.crc32(raw) & 0xFFFFFFFF)
    assert size == len(raw)
    import zipfile

    assert json.loads(read_manifest(SAMPLE)) == json.loads(
        zipfile.ZipFile(SAMPLE).read("manifest.json")
    )


def test_push_happy_path(fake_transport, home):
    routes = {
        ("POST", "init"): FakeResponse(
            201,
            {
                "id": "art_1",
                "put_url": "/v1/orgs/o1/artifacts/art_1/content",
                "witness_status": "witnessed",
                "signature_check": "valid",
            },
        ),
        ("PUT", "content"): FakeResponse(200, {"stored": True}),
    }
    with pytest.MonkeyPatch().context() as mp:
        import httpx

        mp.setattr(httpx, "Client", _client_with(routes))
        result = _invoke(
            ["push", str(SAMPLE), "--agent", "loans", "--reason", "sample",
             "--url", "https://cloud.test", "--org", "o1", "--api-key", "epik_x"]
        )
    assert result.exit_code == 0, result.output
    client = FakeClient.instances[-1]
    init_call = next(c for c in client.calls if c["method"] == "POST")
    payload = init_call["json"]
    raw = SAMPLE.read_bytes()
    assert payload["claimed_sha256"] == hashlib.sha256(raw).hexdigest()
    assert payload["claimed_crc32"] == (zlib.crc32(raw) & 0xFFFFFFFF)
    assert payload["size_bytes"] == len(raw)
    assert payload["agent"] == "loans" and payload["reason"] == "sample"
    import zipfile

    expected_manifest = json.loads(zipfile.ZipFile(SAMPLE).read("manifest.json"))
    assert json.loads(payload["manifest_json"]) == expected_manifest
    put_call = next(c for c in client.calls if c["method"] == "PUT")
    assert put_call["headers"]["Content-Length"] == str(len(raw))
    assert put_call["content_bytes"] == raw
    assert "art_1" in result.output and "witnessed" in result.output


def test_push_deduped_skips_upload(fake_transport, home):
    routes = {("POST", "init"): FakeResponse(200, {"id": "art_9", "deduped": True})}
    with pytest.MonkeyPatch().context() as mp:
        import httpx

        mp.setattr(httpx, "Client", _client_with(routes))
        result = _invoke(
            [
                "push", str(SAMPLE),
                "--url", "https://cloud.test", "--org", "o1", "--api-key", "epik_x",
            ]
        )
    assert result.exit_code == 0, result.output
    assert "Already in the Evidence Room" in result.output


def test_push_sample_skip_is_deterministic(fake_transport, home):
    digest = hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
    pct = int(digest[:8], 16) % 100 or 1
    result = _invoke(
        ["push", str(SAMPLE), "--sample", str(pct),
         "--url", "https://cloud.test", "--org", "o1", "--api-key", "epik_x"]
    )
    assert result.exit_code == 0, result.output
    assert "Skipped by --sample" in result.output
    assert FakeClient.instances == []


def test_push_rejects_bad_reason_and_missing_file(home):
    assert _invoke(["push", str(SAMPLE), "--reason", "nope"]).exit_code == 2
    assert _invoke(["push", "missing.epi"]).exit_code == 2


def test_status_list_and_show(fake_transport, home):
    routes = {
        ("GET", "artifacts"): FakeResponse(
            200,
            {"artifacts": [{"id": "art_1", "goal": "g", "signature_check": "valid",
                            "witness_status": "witnessed", "reason": "sample"}]},
        ),
        ("GET", "art_1"): FakeResponse(
            200, {"id": "art_1", "upload_state": "stored", "goal": "g"}
        ),
    }
    with pytest.MonkeyPatch().context() as mp:
        import httpx

        mp.setattr(httpx, "Client", _client_with(routes))
        base = ["--url", "https://cloud.test", "--org", "o1", "--api-key", "epik_x"]
        assert _invoke(["status", *base]).exit_code == 0
        out = _invoke(["status", "art_1", *base])
        assert out.exit_code == 0, out.output
        assert "art_1" in out.output


def test_login_saves_config(fake_transport, home):
    routes = {("GET", "artifacts"): FakeResponse(200, {"artifacts": []})}
    with pytest.MonkeyPatch().context() as mp:
        import httpx

        mp.setattr(httpx, "Client", _client_with(routes))
        result = _invoke(
            ["login", "--url", "https://cloud.test",
             "--org", "o1", "--api-key", "epik_x"]
        )
    assert result.exit_code == 0, result.output
    saved = json.loads((home / "cloud.json").read_text())
    assert saved == {"url": "https://cloud.test", "org": "o1", "key": "epik_x"}


def test_resolve_creds_prefers_flags_over_env_over_file(home, monkeypatch):
    (home / "cloud.json").write_text(json.dumps(
        {"url": "https://file", "org_id": "o-file", "api_key": "k-file"}
    ))
    monkeypatch.setenv("EPI_CLOUD_URL", "https://env")
    creds = resolve_creds(None, None, None)
    assert creds["url"] == "https://env" and creds["org"] == "o-file"
    creds = resolve_creds("https://flag", "o-flag", "k-flag")
    assert creds == {"url": "https://flag", "org": "o-flag", "key": "k-flag"}
