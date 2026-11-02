"""`epi share` moves to Cloud without breaking installed CLIs.

The default is EPI Cloud. While Cloud's compatibility route is not deployed
(or if it is down), the CLI falls back to the legacy Render portal once. A
user-pinned service never falls back, and a rejection from Cloud (e.g. 400 or
429) is reported rather than retried elsewhere.
"""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import typer

from epi_cli.share import DEFAULT_SHARE_API_URL, PRIMARY_SHARE_API_URL, share

GOLDEN = Path(__file__).resolve().parent / "goldens" / "spec-4.4.3.epi"


def _host(url: str) -> str:
    return urlsplit(url).hostname or ""


def _is_cloud(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname == "cloud.epilabs.org"


class _Resp:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(url: str, code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "nope", {}, io.BytesIO(b'{"detail":"nope"}'))


def test_default_is_cloud(monkeypatch):
    monkeypatch.delenv("EPI_SHARE_API_URL", raising=False)
    from epi_cli.share import _resolve_share_api_base_url

    assert _resolve_share_api_base_url(None) == PRIMARY_SHARE_API_URL
    assert DEFAULT_SHARE_API_URL == "https://epi-verify-portal.onrender.com"


def test_falls_back_to_legacy_when_cloud_route_is_missing(monkeypatch, capsys):
    calls: list[str] = []

    def fake_urlopen(request, timeout=30):
        url = request.full_url
        calls.append(url)
        if _is_cloud(url):
            raise _http_error(url, 404)
        return _Resp({"url": "https://legacy.example/s/abc"})

    monkeypatch.delenv("EPI_SHARE_API_URL", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(typer.Exit) as exit_info:
        share(GOLDEN, 7, True, True, False, None)

    assert exit_info.value.exit_code == 0
    assert _is_cloud(calls[0])
    assert _host(calls[1]) == "epi-verify-portal.onrender.com"
    assert "https://legacy.example/s/abc" in capsys.readouterr().out


def test_falls_back_when_cloud_is_unreachable(monkeypatch):
    calls: list[str] = []

    def fake_urlopen(request, timeout=30):
        url = request.full_url
        calls.append(url)
        if _is_cloud(url):
            raise urllib.error.URLError("connection refused")
        return _Resp({"url": "https://legacy.example/s/abc"})

    monkeypatch.delenv("EPI_SHARE_API_URL", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(typer.Exit) as exit_info:
        share(GOLDEN, 7, True, True, False, None)

    assert exit_info.value.exit_code == 0
    assert len(calls) == 2


def test_pinned_service_never_falls_back(monkeypatch):
    calls: list[str] = []

    def fake_urlopen(request, timeout=30):
        calls.append(request.full_url)
        raise _http_error(request.full_url, 404)

    monkeypatch.delenv("EPI_SHARE_API_URL", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(typer.Exit) as exit_info:
        share(GOLDEN, 7, True, True, False, "https://my-gateway.example")

    assert exit_info.value.exit_code == 1
    assert len(calls) == 1
    assert _host(calls[0]) == "my-gateway.example"


def test_rejection_from_cloud_is_not_retried_elsewhere(monkeypatch):
    calls: list[str] = []

    def fake_urlopen(request, timeout=30):
        calls.append(request.full_url)
        raise _http_error(request.full_url, 400)

    monkeypatch.delenv("EPI_SHARE_API_URL", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(typer.Exit) as exit_info:
        share(GOLDEN, 7, True, True, False, None)

    assert exit_info.value.exit_code == 1
    assert len(calls) == 1
