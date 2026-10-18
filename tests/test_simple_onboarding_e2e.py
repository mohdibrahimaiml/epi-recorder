"""Simple onboarding e2e (no browser, no env vars, no --agent).

New user -> `epi cloud login` choosing "Test Bank" -> push uses the saved
customer automatically with witness settings from login. No EPI_WITNESS_*
env vars, no copy-paste, no --agent flag.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from epi_cli.cloud import app as cloud_app

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "website" / "assets" / "sample.epi"


class FakeResponse:
    def __init__(self, status: int, payload=None, text: str = ""):
        self.status_code = status
        self._payload = payload
        self.text = text if text else json.dumps(payload or {})
        self.headers: dict[str, str] = {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("err", request=None, response=self)


class FakeClient:
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


def _canned(routes: dict):
    def patched_init(self, *args, **kwargs):
        FakeClient.instances.append(self)
        self.calls = []
        self.routes = routes

    return type("CannedClient", (FakeClient,), {"__init__": patched_init})


def test_login_saves_test_bank_without_env(monkeypatch, tmp_path: Path):
    """Device login choosing Test Bank saves customer + witness, no env vars."""
    import time
    import webbrowser

    import httpx

    for var in ("EPI_CLOUD_URL", "EPI_CLOUD_ORG", "EPI_CLOUD_API_KEY",
                "EPI_WITNESS_URL", "EPI_WITNESS_SECRET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("EPI_HOME", str(tmp_path))

    class Device(FakeClient):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.polls = 0

        def post(self, url, **kwargs):
            assert url.endswith("/auth/device/start")
            return FakeResponse(201, {"device_code": "dev_1", "user_code": "AAAA-BBBB",
                                      "verification_url": "https://cloud.test/auth/device",
                                      "interval": 5, "min_cli_version": "4.6.1"})

        def get(self, url, **kwargs):
            self.polls += 1
            if self.polls < 2:
                return FakeResponse(200, {"status": "pending"})
            return FakeResponse(200, {"status": "authorized", "org_id": "org_1",
                                      "api_key": "epik_testbank",
                                      "customer_label": "Test Bank",
                                      "witness_url": "https://cloud.test/w/inb_tb",
                                      "witness_secret": "s3cr3t"})

    FakeClient.instances.clear()
    monkeypatch.setattr(httpx, "Client", Device)
    monkeypatch.setattr(webbrowser, "open", lambda url: True)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    result = CliRunner().invoke(cloud_app, ["login"])
    assert result.exit_code == 0, result.output
    saved = json.loads((tmp_path / "cloud.json").read_text())
    assert saved["customer"] == "Test Bank"
    assert saved["witness_url"] == "https://cloud.test/w/inb_tb"
    assert saved["witness_secret"] == "s3cr3t"
    assert "Test Bank" in result.output


def test_push_uses_saved_customer_no_agent_flag(monkeypatch, tmp_path: Path):
    """Push tags Test Bank with no --agent and no env vars."""
    import httpx

    for var in ("EPI_CLOUD_URL", "EPI_CLOUD_ORG", "EPI_CLOUD_API_KEY",
                "EPI_WITNESS_URL", "EPI_WITNESS_SECRET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    (tmp_path / "cloud.json").write_text(json.dumps({
        "url": "https://cloud.test", "org_id": "org_1", "api_key": "epik_testbank",
        "customer": "Test Bank", "witness_url": "https://cloud.test/w/inb_tb",
        "witness_secret": "s3cr3t",
    }))

    routes = {
        ("POST", "init"): FakeResponse(201, {"id": "art_tb",
                                             "put_url": "/v1/orgs/org_1/artifacts/art_tb/content",
                                             "witness_status": "witnessed",
                                             "signature_check": "valid"}),
        ("PUT", "content"): FakeResponse(200, {"stored": True}),
    }
    FakeClient.instances.clear()
    monkeypatch.setattr(httpx, "Client", _canned(routes))

    result = CliRunner().invoke(cloud_app, ["push", str(SAMPLE), "--reason", "sample"])
    assert result.exit_code == 0, result.output
    client = FakeClient.instances[-1]
    init = next(c for c in client.calls if c["method"] == "POST")
    assert init["json"]["agent"] == "Test Bank"
    assert "witnessed" in result.output
