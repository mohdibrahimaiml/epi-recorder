"""EPI evidence MCP server (Streamable HTTP).

Same three tools as stdio (see ``tools.py``), served at ``/mcp`` for
remote hosts such as ChatGPT Developer Mode.

Run: ``epi-mcp-http [--host 127.0.0.1] [--port 8000]``

Security posture (mirrors the gateway defaults):
- Binds loopback by default.
- A non-loopback bind without ``EPI_MCP_TOKEN`` refuses to start.
- When ``EPI_MCP_TOKEN`` is set, ``/mcp`` requires
  ``Authorization: Bearer <token>``.
"""

from __future__ import annotations

import argparse
import os

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from epi_mcp.server import server
from epi_mcp.tools import get_artifact_path


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in {"localhost", "::1"} or h.startswith("127.")


class _BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/mcp" or request.url.path.startswith("/artifacts/"):
            presented = (request.headers.get("authorization") or "").strip()
            if presented != f"Bearer {self._token}":
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


async def _download_artifact(request: Request):
    path = get_artifact_path(request.path_params.get("artifact_id", ""))
    if path is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=path.name,
    )


def _favicon_path() -> Path | None:
    from pathlib import Path as _Path

    here = _Path(__file__).resolve()
    for candidate in [
        here.parent.parent / "assets" / "favicon.ico",
        _Path("assets") / "favicon.ico",
    ]:
        if candidate.is_file():
            return candidate
    try:
        import epi_core as _core

        packaged = _Path(_core.__file__).resolve().parent / "assets" / "epi.ico"
        if packaged.is_file():
            return packaged
    except Exception:
        pass
    return None


async def _serve_favicon(request: Request):
    path = _favicon_path()
    if path is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(path, media_type="image/x-icon")


def _transport_security():
    """Host allowlist for the SDK's DNS-rebinding protection.

    Loopback always allowed (local dev + tests). The public hostname is
    derived from EPI_MCP_PUBLIC_URL so the deployed endpoint answers.
    Without this, the SDK rejects the public Host header (HTTP 421).
    """
    import os as _os
    from urllib.parse import urlparse as _urlparse

    hosts = ["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "[::1]", "testserver"]
    public = (_os.environ.get("EPI_MCP_PUBLIC_URL") or "").strip()
    if public:
        hn = _urlparse(public if "://" in public else f"https://{public}").hostname
        if hn and hn not in hosts:
            hosts.extend([hn, f"{hn}:*", f"{hn}:443", f"{hn}:80"])
    try:
        from mcp.server.transport_security import TransportSecuritySettings as _TSS

        return _TSS(allowed_hosts=hosts)
    except Exception:
        return None


def build_app() -> Starlette:
    token = (os.environ.get("EPI_MCP_TOKEN") or "").strip()
    inner = server.streamable_http_app(
        streamable_http_path="/mcp", transport_security=_transport_security()
    )
    routes = list(inner.routes) + [
        Route("/artifacts/{artifact_id}", _download_artifact),
        Route("/favicon.ico", _serve_favicon),
    ]
    if token:
        return Starlette(
            middleware=[Middleware(_BearerAuthMiddleware, token=token)],
            routes=routes,
            lifespan=inner.router.lifespan_context,
        )
    return Starlette(routes=routes, lifespan=inner.router.lifespan_context)


def main() -> None:
    parser = argparse.ArgumentParser(description="EPI evidence MCP over Streamable HTTP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if not is_loopback_host(args.host) and not (os.environ.get("EPI_MCP_TOKEN") or "").strip():
        raise SystemExit(
            f"Refusing to bind {args.host} with no EPI_MCP_TOKEN: "
            "set EPI_MCP_TOKEN or bind 127.0.0.1."
        )

    import uvicorn

    uvicorn.run(build_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
