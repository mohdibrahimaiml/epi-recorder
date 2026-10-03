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


def build_app() -> Starlette:
    token = (os.environ.get("EPI_MCP_TOKEN") or "").strip()
    inner = server.streamable_http_app(streamable_http_path="/mcp")
    routes = list(inner.routes) + [Route("/artifacts/{artifact_id}", _download_artifact)]
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
