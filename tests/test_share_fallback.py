"""`epi share` uploads to EPI Cloud only.

The legacy Render portal is being retired. Whatever Cloud answers (missing
route, outage, Cloudflare 403, rejection), the file is never sent to a second
service: the error is reported and the upload fails. A pinned service is used
as given.
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
    assert DEFAULT_SHARE_API_URL == PRIMARY_SHARE_API_URL == "https://cloud.epilabs.org"


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

def test_upload_identifies_the_client(monkeypatch):
    """Cloudflare rejects urllib's default UA with 403 error 1010."""
    seen: dict[str, str | None] = {}

    def fake_urlopen(request, timeout=30):
        if _is_cloud(request.full_url):
            seen["ua"] = request.get_header("User-agent")
        return _Resp({"url": "https://cloud.example/s/abc"})

    monkeypatch.delenv("EPI_SHARE_API_URL", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(typer.Exit) as exit_info:
        share(GOLDEN, 7, True, True, False, None)

    assert exit_info.value.exit_code == 0
    assert seen["ua"].startswith("epi-recorder/")


@pytest.mark.parametrize("failure", [403, 404, 502, 503, "unreachable"])
def test_cloud_failure_is_reported_and_never_sent_elsewhere(monkeypatch, failure):
    calls: list[str] = []

    def fake_urlopen(request, timeout=30):
        calls.append(request.full_url)
        if failure == "unreachable":
            raise urllib.error.URLError("down")
        raise _http_error(request.full_url, failure)

    monkeypatch.delenv("EPI_SHARE_API_URL", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(typer.Exit) as exit_info:
        share(GOLDEN, 7, True, True, False, None)

    assert exit_info.value.exit_code == 1
    assert len(calls) == 1
    assert _is_cloud(calls[0])


def test_no_render_host_left_in_share_code():
    import epi_cli.share as share_mod

    assert "onrender" not in Path(share_mod.__file__).read_text(encoding="utf-8")
