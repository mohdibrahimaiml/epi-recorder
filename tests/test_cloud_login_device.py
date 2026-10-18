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
        self.calls.append({"method": "POST", "url": url, "json": kwargs.get("json")})
        assert url.endswith("/auth/device/start")
        # The CLI names this computer so the dashboard can list it.
        assert (kwargs.get("json") or {}).get("device_name")

        class R:
            status_code = 201

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "device_code": "dev_abc123",
                    "user_code": "WDJB-MJHT",
                    "verification_url": "https://cloud.test/auth/device",
                    "interval": 5,
                }

        return R()

    def get(self, url, **kwargs):
        self.calls.append({"method": "GET", "url": url})
        self.polls += 1

        class R:
            status_code = 200
            headers: dict[str, str] = {}

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
    assert "WDJB-MJHT" in result.output
    # The secret device code is never printed; only the typed user code is.
    assert "dev_abc123" not in result.output


def test_cloud_login_device_flow_backs_off_on_429(home, monkeypatch):
    """Poller handles 429 with Retry-After instead of hammering sign-in."""

    import time
    import webbrowser

    import httpx

    seen_waits: list[float] = []

    class Throttled(FakeDeviceClient):
        def get(self, url, **kwargs):
            self.calls.append({"method": "GET", "url": url})
            self.polls += 1

            class R:
                status_code = 429 if self.polls == 1 else 200

                def __init__(self, polls: int):
                    self.polls = polls
                    self.headers = {"retry-after": "7"} if polls == 1 else {}

                def json(self):
                    if self.polls < 3:
                        return {"status": "pending"}
                    return {
                        "status": "authorized",
                        "org_id": "org_123",
                        "api_key": "epik_devicekey123",
                    }

            return R(self.polls)

    Throttled.instances.clear()
    monkeypatch.setattr(httpx, "Client", Throttled)
    monkeypatch.setattr(webbrowser, "open", lambda url: True)
    monkeypatch.setattr(time, "sleep", lambda s: seen_waits.append(s))

    result = CliRunner().invoke(app, ["login"])
    assert result.exit_code == 0, result.output
    assert seen_waits and max(seen_waits) >= 7


def test_warn_if_cli_outdated_matches_current_reports_nothing(capsys):
    """The CLI built here must not warn when min == current (no catch-22)."""
    from epi_core import __version__ as current

    from epi_cli.cloud import _warn_if_cli_outdated, _version_tuple

    assert _version_tuple("1.0.2") < _version_tuple("1.0.10")
    assert not (_version_tuple(current) < _version_tuple(current))
    _warn_if_cli_outdated(current)
    out = capsys.readouterr().out
    assert "too old" not in out.lower() and "pip install" not in out.lower()


def test_warn_if_cli_outdated_tells_exact_pip_command(capsys):
    from epi_cli.cloud import _warn_if_cli_outdated

    _warn_if_cli_outdated("99.0.0")
    out = " ".join(capsys.readouterr().out.split())
    assert "pip install -U epi-recorder" in out


def test_no_forced_ansi_in_windows_cmd():
    """No Console(legacy_windows=False): rich must translate ANSI for cmd.exe."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1] / "epi_cli"
    offenders = []
    for path in repo.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "legacy_windows=False" in text:
            offenders.append(path.name)
    assert not offenders, f"forced ANSI in windows cmd: {offenders}"
