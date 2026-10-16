"""Device flow for `epi cloud login` with no flags (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.cloud import app


class FakeDeviceClient:
    instances: list[FakeDeviceClient] = []

    def __init__(self, *args, **kwargs):
        self.calls: list[dict] = []
        self.polls = 0
        FakeDeviceClient.instances.append(self)
        base = kwargs.get("base_url", "")
        self.base = base

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, **kwargs):
        self.calls.append({"method": "POST", "url": url})
        assert url.endswith("/auth/device/start")

        class R:
            status_code = 201

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "device_code": "dev_abc123",
                    "verification_url": "https://cloud.test/auth/device?code=dev_abc123",
                }

        return R()

    def get(self, url, **kwargs):
        self.calls.append({"method": "GET", "url": url})
        self.polls += 1

        class R:
            status_code = 200

            def __init__(self, polls: int):
                self.polls = polls

            def json(self):
                if self.polls < 2:
                    return {"status": "pending"}
                return {"status": "authorized", "org_id": "org_123", "api_key": "epik_devicekey123"}

        return R(self.polls)


@pytest.fixture()
def home(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    for var in ("EPI_CLOUD_URL", "EPI_CLOUD_ORG", "EPI_CLOUD_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_cloud_login_device_flow(home, monkeypatch):
    import time
    import webbrowser

    import httpx

    FakeDeviceClient.instances.clear()
    monkeypatch.setattr(httpx, "Client", FakeDeviceClient)
    monkeypatch.setattr(webbrowser, "open", lambda url: True)
    # Avoid real sleep in the poll loop.
    monkeypatch.setattr(time, "sleep", lambda s: None)

    result = CliRunner().invoke(app, ["login"])
    assert result.exit_code == 0, result.output
    saved = json.loads((home / "cloud.json").read_text())
    assert saved["url"] == "https://cloud.epilabs.org"
    assert saved["org_id"] == "org_123"
    assert saved["api_key"] == "epik_devicekey123"
    out = result.output.lower()
    assert "authorize" in out or "authorized" in out
