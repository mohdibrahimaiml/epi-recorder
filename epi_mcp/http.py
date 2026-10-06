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
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
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
        from epi_mcp import auth as _auth
        from epi_mcp.tools import _current_subject as _subject_var

        presented = (request.headers.get("authorization") or "").strip()
        raw = presented[7:] if presented.lower().startswith("bearer ") else presented
        subject = _auth.verify_bearer_token(raw) if raw else None
        if subject is None and not _auth.auth_configured():
            # No auth configured (loopback dev): the caller is the operator.
            subject = "operator"
        path = request.url.path
        if subject is None and path.startswith("/artifacts/"):
            # Human download links carry their own expiring capability token.
            from epi_mcp.tools import download_token_valid

            aid = path[len("/artifacts/"):]
            if download_token_valid(aid, request.query_params.get("t")):
                subject = "download-link"
        if subject is None and (path.startswith("/artifacts/") or path == "/mcp"):
            # The WWW-Authenticate challenge is what makes MCP hosts
            # (ChatGPT) discover OAuth and start the approval flow.
            from epi_mcp import oauth as _oauth

            base = _oauth.public_base() or str(request.base_url).rstrip("/")
            return JSONResponse(
                {"error": "Unauthorized"},
                status_code=401,
                headers={
                    "WWW-Authenticate": (
                        f'Bearer resource_metadata="{base}/.well-known/oauth-protected-resource"'
                    )
                },
            )
        _subject_var.set(subject)
        try:
            return await call_next(request)
        finally:
            _subject_var.set(None)


async def _download_artifact(request: Request):
    path = get_artifact_path(request.path_params.get("artifact_id", ""))
    if path is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=path.name,
        headers={"Cache-Control": "no-store"},
    )


def _favicon_path():
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


async def _oauth_protected_resource(request: Request):
    from epi_mcp import oauth as _oauth

    base = _oauth.public_base() or str(request.base_url).rstrip("/")
    return JSONResponse({
        "resource": f"{base}/mcp",
        "authorization_servers": [base],
        "scopes_supported": ["seal", "verify", "export"],
        "bearer_methods_supported": ["header"],
    })


async def _oauth_metadata(request: Request):
    from epi_mcp import oauth as _oauth

    base = _oauth.public_base() or str(request.base_url).rstrip("/")
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_post", "client_secret_basic", "none",
        ],
    })


async def _oauth_register(request: Request):
    from epi_mcp import oauth as _oauth

    try:
        info = await request.json()
    except Exception:
        info = {}
    if not isinstance(info, dict):
        info = {}
    return JSONResponse(_oauth.register_client(info))


async def _oauth_authorize_form(request: Request):
    params = dict(request.query_params)
    missing = [k for k in ("client_id", "redirect_uri", "state") if not params.get(k)]
    if missing:
        return JSONResponse({"error": f"missing: {', '.join(missing)}"}, status_code=400)
    import html as _html
    from urllib.parse import urlencode as _urlencode

    from epi_mcp import oauth as _oauth

    if not _oauth.redirect_allowed(params["client_id"], params["redirect_uri"]):
        return JSONResponse({"error": "invalid redirect_uri for client"}, status_code=400)
    action = _html.escape("/oauth/approve?" + _urlencode(params), quote=True)
    return HTMLResponse(
        "<html><body><h1>Approve EPI Evidence Sealer?</h1>"
        "<p>This grants sealing under a pseudonymous identity bound to this "
        "approval. It does not share passwords or verify who you are.</p>"
        f'<form method="post" action="{action}">'
        '<button type="submit" name="decision" value="approve">Approve</button> '
        '<button type="submit" name="decision" value="deny">Deny</button>'
        "</form></body></html>"
    )


async def _oauth_approve(request: Request):
    from epi_mcp import oauth as _oauth

    from urllib.parse import urlencode as _urlencode

    params = dict(request.query_params)
    form = dict(await request.form())
    if not _oauth.redirect_allowed(params.get("client_id", ""), params.get("redirect_uri", "")):
        return JSONResponse({"error": "invalid redirect_uri for client"}, status_code=400)
    sep = "&" if "?" in params["redirect_uri"] else "?"
    if form.get("decision") != "approve":
        q = _urlencode({"error": "access_denied", "state": params.get("state", "")})
        return RedirectResponse(f"{params['redirect_uri']}{sep}{q}", status_code=303)
    subject = _oauth.create_approval()
    code = _oauth.issue_code(
        subject,
        params.get("client_id", ""),
        params.get("redirect_uri", ""),
        params.get("code_challenge", ""),
        params.get("code_challenge_method"),
    )
    q = _urlencode({"code": code, "state": params.get("state", "")})
    return RedirectResponse(f"{params['redirect_uri']}{sep}{q}", status_code=303)


async def _oauth_token(request: Request):
    from epi_mcp import oauth as _oauth

    try:
        form = dict(await request.form())
    except Exception:
        form = {}
    if not form:
        try:
            body = await request.json()
            form = body if isinstance(body, dict) else {}
        except Exception:
            form = {}
    grant = form.get("grant_type", "")
    if not form.get("client_id"):
        # RFC 6749 §2.3.1: clients may authenticate via HTTP Basic.
        basic = (request.headers.get("authorization") or "").strip()
        if basic.lower().startswith("basic "):
            import base64 as _b64

            try:
                decoded = _b64.b64decode(basic[6:]).decode("utf-8", "replace")
                form["client_id"] = decoded.split(":", 1)[0]
            except Exception:
                pass
    if grant == "authorization_code":
        out = _oauth.redeem_code(
            str(form.get("code", "")),
            str(form.get("client_id", "")),
            str(form.get("redirect_uri", "")),
            str(form.get("code_verifier", "")),
        )
    elif grant == "refresh_token":
        out = _oauth.redeem_refresh(str(form.get("refresh_token", "")))
    else:
        out = None
    if out is None:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    return JSONResponse(out)


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
        Route("/.well-known/oauth-authorization-server", _oauth_metadata),
        Route("/.well-known/oauth-authorization-server/{rest:path}", _oauth_metadata),
        Route("/.well-known/oauth-protected-resource", _oauth_protected_resource),
        Route("/.well-known/oauth-protected-resource/{rest:path}", _oauth_protected_resource),
        Route("/oauth/register", _oauth_register, methods=["POST"]),
        Route("/oauth/authorize", _oauth_authorize_form, methods=["GET"]),
        Route("/oauth/approve", _oauth_approve, methods=["POST"]),
        Route("/oauth/token", _oauth_token, methods=["POST"]),
    ]
    # Subject middleware always present: binds caller identity for seals.
    return Starlette(
        middleware=[Middleware(_BearerAuthMiddleware, token=token)],
        routes=routes,
        lifespan=inner.router.lifespan_context,
    )


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

    import sys

    if not (os.environ.get("EPI_OAUTH_SECRET") or os.environ.get("EPI_SIGNING_SEED") or "").strip():
        print(
            "[epi-mcp] WARNING: EPI_OAUTH_SECRET is not set. OAuth tokens fall back to the "
            "static EPI_MCP_TOKEN as their signing key, and seal signing keys live on this "
            "server's disk, so signers change when the disk is reset and cannot be pinned. "
            "Set EPI_OAUTH_SECRET to a random 32+ character value.",
            file=sys.stderr,
        )

    import uvicorn

    uvicorn.run(build_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
