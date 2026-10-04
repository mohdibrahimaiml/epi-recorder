"""Item 4: secure gateway defaults on every entry point."""

from fastapi.testclient import TestClient

from epi_gateway.main import GatewayRuntimeSettings, create_app
from epi_gateway.worker import EvidenceWorker


def test_library_defaults_are_secure():
    s = GatewayRuntimeSettings()
    assert s.proxy_failure_mode == "fail-closed"
    assert s.retention_mode == "full_content"
    assert s.allowed_origins == []
    assert s.auth_required is False  # loopback bind is the protection; auth when configured


def test_cli_serve_defaults_match_library():
    import typer.testing  # noqa: F401
    from typer.testing import CliRunner
    from epi_cli.gateway import app as gw_app

    # Inspect option defaults rather than launching a server.
    import epi_cli.gateway as gwmod
    import inspect

    sig = inspect.signature(gwmod.serve)
    assert sig.parameters["retention_mode"].default.default == "full_content"
    assert sig.parameters["proxy_failure_mode"].default.default == "fail-closed"


def test_metrics_requires_auth_when_configured(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path / "v", batch_size=1, batch_timeout=0.1)
    settings = GatewayRuntimeSettings(
        storage_dir=str(tmp_path / "v"),
        access_token="secret",
    )
    app = create_app(worker=worker, settings=settings)
    with TestClient(app) as client:
        r = client.get("/metrics")
        assert r.status_code == 401
        r2 = client.get("/metrics", headers={"Authorization": "Bearer secret"})
        assert r2.status_code == 200


def test_metrics_open_without_auth(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path / "v", batch_size=1, batch_timeout=0.1)
    settings = GatewayRuntimeSettings(storage_dir=str(tmp_path / "v"))
    app = create_app(worker=worker, settings=settings)
    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 200


def test_non_loopback_bind_without_auth_refused():
    import pytest

    from epi_gateway.main import require_auth_for_host

    no_auth = GatewayRuntimeSettings()
    for host in ["0.0.0.0", "::", "192.168.1.10", "example.com"]:
        with pytest.raises(RuntimeError):
            require_auth_for_host(host, no_auth)
    # Loopback without auth is fine; non-loopback with auth is fine.
    require_auth_for_host("127.0.0.1", no_auth)
    require_auth_for_host("localhost", no_auth)
    require_auth_for_host("::1", no_auth)
    with_auth = GatewayRuntimeSettings(access_token="secret")
    require_auth_for_host("0.0.0.0", with_auth)
