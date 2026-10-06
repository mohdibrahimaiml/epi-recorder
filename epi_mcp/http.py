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
        from epi_mcp.tools import _current_identity as _identity_var
        from epi_mcp.tools import _current_subject as _subject_var

        presented = (request.headers.get("authorization") or "").strip()
        raw = presented[7:] if presented.lower().startswith("bearer ") else presented
        subject = _auth.verify_bearer_token(raw) if raw else None
        if subject is None and not _auth.auth_configured():
            # No auth configured (loopback dev): the caller is the operator.
            subject = "operator"
        path = request.url.path
        if subject is None and path.startswith(("/artifacts/", "/view/")):
            # Human download and view links carry their own expiring capability token.
            from epi_mcp.tools import download_token_valid

            aid = path.split("/", 2)[2] if path.count("/") >= 2 else ""
            if download_token_valid(aid, request.query_params.get("t")):
                subject = "download-link"
            elif path.startswith("/view/"):
                return HTMLResponse(
                    "<html><body style=\"font-family:sans-serif;max-width:40em;margin:3em auto\">"
                    "<h1>This link has expired or is not valid</h1>"
                    "<p>Sealed files are kept for 24 hours. If you downloaded the file, "
                    "open it by uploading it at <a href=\"https://epilabs.org/verify\">"
                    "epilabs.org/verify</a>.</p></body></html>",
                    status_code=404,
                    headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
                )
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
        identity = None
        if raw and subject is not None:
            from epi_mcp import oauth as _oauth_mod

            claims = _oauth_mod.verify_own_claims(raw)
            if claims and claims[0] == subject:
                identity = claims[1]
        _identity_var.set(identity)
        try:
            return await call_next(request)
        finally:
            _subject_var.set(None)
            _identity_var.set(None)


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


async def _view_artifact(request: Request):
    """Show a sealed file in the browser with nothing to install.

    The .epi is an HTML viewer with the signed archive appended, so serving the
    same bytes as a web page renders it. The page holds a conversation, so it is
    sandboxed: scripts run (the viewer needs them) but in an opaque origin, with
    no access to this server's origin, cookies or storage.
    """
    path = get_artifact_path(request.path_params.get("artifact_id", ""))
    if path is None:
        return HTMLResponse(
            "<html><body style=\"font-family:sans-serif;max-width:40em;margin:3em auto\">"
            "<h1>Not found</h1><p>This file is no longer on the server.</p></body></html>",
            status_code=404,
            headers={"Cache-Control": "no-store"},
        )
    return FileResponse(
        path,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Security-Policy": "sandbox allow-scripts allow-downloads",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
            "X-Robots-Tag": "noindex",
        },
    )


_SEAL_WINDOW_SECONDS = 3600
_SEAL_MAX_PER_WINDOW = 10
_SEAL_HITS: dict[str, list[float]] = {}

_PAGE_CSS = (
    "body{font-family:system-ui,sans-serif;max-width:46em;margin:2.5em auto;padding:0 1em;line-height:1.5;"
    "color:#1b1f23;background:#fff}h1{font-size:1.5em}textarea{width:100%;min-height:12em;font:inherit}"
    "label{font-weight:600;display:block;margin-top:1em}button{margin-top:1em;padding:.6em 1.2em;font:inherit}"
    ".note{background:#f4f6f8;border-left:4px solid #8a94a0;padding:.6em 1em;margin:1em 0}"
    ".err{background:#fdf0ef;border-left:4px solid #c0392b;padding:.6em 1em;margin:1em 0}"
    "code{background:#f4f6f8;padding:.1em .3em;word-break:break-all}"
    "@media (prefers-color-scheme:dark){body{background:#14171a;color:#e6e8ea}.note,code{background:#222830}"
    ".err{background:#33201f}a{color:#7db7ff}}"
)


def _seal_page(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>Seal a conversation</title><style>{_PAGE_CSS}</style></head><body>{body}</body></html>",
        status_code=status,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"},
    )


def _seal_form(message: str = "", extra: str = "") -> str:
    import html as _html

    msg = f'<div class="err">{_html.escape(message)}</div>' if message else ""
    return (
        "<h1>Seal a conversation</h1>"
        "<p>Make a signed, tamper-evident record of a Claude or ChatGPT conversation. "
        "No chat model is involved, so nothing can be paused or shortened.</p>"
        f"{msg}{extra}"
        '<form method="post" action="/seal" enctype="multipart/form-data">'
        '<label for="file">Upload your chat export (conversations.json)</label>'
        '<input id="file" type="file" name="file" accept=".json,.txt,.md">'
        '<label for="text">Or paste the conversation</label>'
        '<textarea id="text" name="text" placeholder="Paste here. Lines like &quot;You:&quot; / &quot;Claude:&quot; '
        'are read as turns."></textarea>'
        '<label for="conversation">If your export has several conversations, which number? (optional)</label>'
        '<input id="conversation" name="conversation" type="number" min="1" style="width:6em">'
        '<p><button type="submit">Seal it</button></p></form>'
        '<div class="note"><strong>What this proves.</strong> The sealed file holds exactly what you gave us, and any '
        "later change to it is detectable. EPI does not check that the text really came from Claude or ChatGPT. "
        "Files are kept for 24 hours, so download yours. Anyone can check a saved file at "
        '<a href="https://epilabs.org/verify">epilabs.org/verify</a>.</div>'
    )


async def _seal_get(request: Request):
    return _seal_page(_seal_form())


def _client_key(request: Request) -> str:
    # The proxy in front appends the real address last; earlier entries can be forged.
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[-1].strip()
    return fwd or (request.client.host if request.client else "unknown")


async def _seal_post(request: Request):
    import hashlib
    import html as _html
    import time as _time

    from starlette.concurrency import run_in_threadpool

    from epi_mcp import tools as _tools
    from epi_mcp.transcripts import MAX_INPUT_BYTES, NeedsChoice, TranscriptError, parse_transcript

    key = _client_key(request)
    now = _time.time()
    hits = [t for t in _SEAL_HITS.get(key, []) if now - t < _SEAL_WINDOW_SECONDS]
    if len(hits) >= _SEAL_MAX_PER_WINDOW:
        _SEAL_HITS[key] = hits
        return _seal_page(_seal_form("Too many seals from this connection in the last hour. Please try again later."), 429)

    if int(request.headers.get("content-length") or 0) > MAX_INPUT_BYTES + 512 * 1024:
        return _seal_page(_seal_form("That is too large. Export or paste a single conversation (limit 3 MB)."), 413)
    try:
        form = await request.form(max_part_size=MAX_INPUT_BYTES + 1024)
    except Exception:
        return _seal_page(_seal_form("That upload could not be read. Try pasting the text instead."), 400)

    upload = form.get("file")
    raw: bytes | str = b""
    filename = ""
    if upload is not None and hasattr(upload, "read"):
        raw = await upload.read()
        filename = getattr(upload, "filename", "") or ""
    if not raw:
        raw = str(form.get("text") or "")
    choice_raw = str(form.get("conversation") or "").strip()
    choice = int(choice_raw) if choice_raw.isdigit() else None

    try:
        parsed = parse_transcript(raw, filename=filename, choice=choice)
    except NeedsChoice as exc:
        items = "".join(f"<li>{i}. {_html.escape(t[:100])}</li>" for i, t in enumerate(exc.titles[:60], 1))
        more = f"<li>… and {len(exc.titles) - 60} more</li>" if len(exc.titles) > 60 else ""
        return _seal_page(
            _seal_form(
                "That file has several conversations. Choose one by number and upload it again.",
                f"<ol style='list-style:none;padding:0'>{items}{more}</ol>",
            )
        )
    except TranscriptError as exc:
        return _seal_page(_seal_form(str(exc)), 400)

    subject = "web-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

    def _do_seal():
        token = _tools._current_subject.set(subject)
        try:
            return _tools.epi_seal_record_tool(parsed["events"], goal=parsed["goal"], include_bytes=False)
        finally:
            _tools._current_subject.reset(token)

    try:
        sealed = await run_in_threadpool(_do_seal)
    except (ValueError, PermissionError) as exc:
        return _seal_page(_seal_form(str(exc)), 400)
    hits.append(now)
    _SEAL_HITS[key] = hits

    base = (os.environ.get("EPI_MCP_PUBLIC_URL") or "").strip().rstrip("/") or str(request.base_url).rstrip("/")
    aid = sealed["artifact_id"]
    token = _tools._issue_download_token(aid)
    view, dl = f"{base}/view/{aid}?t={token}", f"{base}/artifacts/{aid}?t={token}"
    counts = sealed.get("summary_counts", {}).get("by_kind", {})
    warns = "".join(f"<li>{_html.escape(w)}</li>" for w in sealed.get("warnings", []))
    how = {
        "export": "read from your chat export, with the times it recorded",
        "labelled-text": "read from your pasted text by its speaker labels (no times)",
        "single-text": "sealed as one block of text, because no speaker labels were found",
    }[parsed["how"]]
    body = (
        "<h1>Sealed</h1>"
        f"<p>{sealed['steps_sealed']} items {how}. "
        f"({counts.get('user.message', 0)} from you, {counts.get('assistant.message', 0)} from the assistant.)</p>"
        f'<p><a href="{_html.escape(view, quote=True)}"><strong>View it now</strong></a> &nbsp;·&nbsp; '
        f'<a href="{_html.escape(dl, quote=True)}">Download the .epi file</a> (kept for 24 hours)</p>'
        f"<p>SHA-256: <code>{_html.escape(sealed['sha256'])}</code></p>"
        + (f"<p>Things to know:</p><ul>{warns}</ul>" if warns else "")
        + '<div class="note">Anyone can check a saved file at <a href="https://epilabs.org/verify">'
        "epilabs.org/verify</a>; nothing needs installing. The seal shows the text has not changed since sealing. "
        "It does not prove the text came from Claude or ChatGPT.</div>"
        '<p><a href="/seal">Seal another</a></p>'
    )
    return _seal_page(body)


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
    from epi_mcp import idp as _idp

    signin = ""
    if _idp.idp_enabled():
        hidden = "".join(
            f'<input type="hidden" name="{_html.escape(k, quote=True)}" value="{_html.escape(v, quote=True)}">'
            for k, v in params.items()
        )
        label = _html.escape(_idp.idp_config()["name"])
        signin = (
            '<hr><form method="get" action="/oauth/idp/start">' + hidden
            + f"<p>Or sign in with {label} so sealed files name you as the person who sealed them.</p>"
            + (
                "<p>Your public GitHub username will be written into the sealed files.</p>"
                '<p><label><input type="checkbox" name="include_email" value="1"> '
                "Also include my verified GitHub email</label></p>"
                if _idp.idp_config()["issuer"] == "github"
                else '<p><label><input type="checkbox" name="include_email" value="1" checked> '
                "Put my email in the sealed files (uncheck to stay pseudonymous)</label></p>"
            )
            + f'<button type="submit">Sign in with {label} and approve</button></form>'
        )
    gate = (
        '<p><label>Access passphrase: <input type="password" name="passphrase" '
        'autocomplete="off" required></label></p>'
        if _approve_passphrase()
        else ""
    )
    return HTMLResponse(
        "<html><body><h1>Approve EPI Evidence Sealer?</h1>"
        "<p>This grants sealing under a pseudonymous identity bound to this "
        "approval. It does not share passwords or verify who you are.</p>"
        f'<form method="post" action="{action}">{gate}'
        '<button type="submit" name="decision" value="approve">Approve</button> '
        '<button type="submit" name="decision" value="deny">Deny</button>'
        f"</form>{signin}</body></html>"
    )


def _approve_passphrase() -> str:
    return (os.environ.get("EPI_APPROVE_PASSPHRASE") or "").strip()


async def _oauth_approve(request: Request):
    from epi_mcp import oauth as _oauth

    from urllib.parse import urlencode as _urlencode

    params = dict(request.query_params)
    form = dict(await request.form())
    if not _oauth.redirect_allowed(params.get("client_id", ""), params.get("redirect_uri", "")):
        return JSONResponse({"error": "invalid redirect_uri for client"}, status_code=400)
    sep = "&" if "?" in params["redirect_uri"] else "?"
    required = _approve_passphrase()
    if required and form.get("decision") == "approve":
        import hmac as _hmac

        given = str(form.get("passphrase", ""))
        if not _hmac.compare_digest(given.encode("utf-8"), required.encode("utf-8")):
            return HTMLResponse(
                "<html><body><h1>Wrong passphrase</h1>"
                "<p>Access to this EPI server is restricted. Go back and try again.</p>"
                "</body></html>",
                status_code=403,
            )
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


def _idp_page(title: str, message: str, status: int) -> HTMLResponse:
    import html as _html

    return HTMLResponse(
        f"<html><body><h1>{_html.escape(title)}</h1><p>{_html.escape(message)}</p></body></html>",
        status_code=status,
    )


async def _oauth_idp_start(request: Request):
    from epi_mcp import idp as _idp
    from epi_mcp import oauth as _oauth

    params = {k: v for k, v in request.query_params.items() if k != "include_email"}
    if not _oauth.redirect_allowed(params.get("client_id", ""), params.get("redirect_uri", "")):
        return JSONResponse({"error": "invalid redirect_uri for client"}, status_code=400)
    try:
        url = _idp.begin_login(params, include_email=bool(request.query_params.get("include_email")))
    except Exception as exc:
        return _idp_page("Sign-in unavailable", str(exc) if isinstance(exc, _idp.IdpError) else "Sign-in is unavailable. Use the anonymous approval instead.", 503)
    return RedirectResponse(url, status_code=303)


async def _oauth_idp_callback(request: Request):
    from urllib.parse import urlencode as _urlencode

    from epi_mcp import idp as _idp
    from epi_mcp import oauth as _oauth

    q = request.query_params
    if q.get("error") or not q.get("code") or not q.get("state"):
        return _idp_page("Sign-in cancelled", "Nothing was approved. You can go back and try again.", 400)
    try:
        params, subject, identity = _idp.finish_login(q["code"], q["state"])
    except _idp.IdpError as exc:
        return _idp_page("Sign-in failed", str(exc), 403)
    if not _oauth.redirect_allowed(params.get("client_id", ""), params.get("redirect_uri", "")):
        return JSONResponse({"error": "invalid redirect_uri for client"}, status_code=400)
    _oauth.create_approval(subject)
    code = _oauth.issue_code(
        subject, params.get("client_id", ""), params.get("redirect_uri", ""),
        params.get("code_challenge", ""), params.get("code_challenge_method"), identity,
    )
    redirect_uri = params["redirect_uri"]
    sep = "&" if "?" in redirect_uri else "?"
    out = _urlencode({"code": code, "state": params.get("state", "")})
    return RedirectResponse(f"{redirect_uri}{sep}{out}", status_code=303)


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
        Route("/view/{artifact_id}", _view_artifact),
        Route("/seal", _seal_get, methods=["GET"]),
        Route("/seal", _seal_post, methods=["POST"]),
        Route("/favicon.ico", _serve_favicon),
        Route("/.well-known/oauth-authorization-server", _oauth_metadata),
        Route("/.well-known/oauth-authorization-server/{rest:path}", _oauth_metadata),
        Route("/.well-known/oauth-protected-resource", _oauth_protected_resource),
        Route("/.well-known/oauth-protected-resource/{rest:path}", _oauth_protected_resource),
        Route("/oauth/register", _oauth_register, methods=["POST"]),
        Route("/oauth/authorize", _oauth_authorize_form, methods=["GET"]),
        Route("/oauth/approve", _oauth_approve, methods=["POST"]),
        Route("/oauth/idp/start", _oauth_idp_start, methods=["GET"]),
        Route("/oauth/idp/callback", _oauth_idp_callback, methods=["GET"]),
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
