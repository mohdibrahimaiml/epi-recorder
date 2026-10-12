"""Customer witness receiver (stdlib only).

The vendor points their witness webhook (``EPI_WITNESS_URL`` /
``witness_url=``) at this server. It checks the ``X-EPI-Signature`` HMAC,
stamps ``received_at`` and appends each hash-only seal report
(``schema: epi-witness/v1``) to a JSONL log -- the file the customer later
checks with::

    epi verify run.epi --policy strict --witness-log received.jsonl

Run it with ``epi witness serve`` (installed with the package). The
reference script ``examples/witness_receiver/receiver.py`` is a thin
wrapper around :func:`main` in this module.

The default host is 127.0.0.1 (this machine only). For a vendor on another
machine, listen on 0.0.0.0 behind a TLS-terminating reverse proxy (Caddy,
nginx, a cloud load balancer) and give the vendor the https:// URL.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import hmac
import json
import os
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable

WITNESS_SCHEMA = "epi-witness/v1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8099
DEFAULT_OUT = Path("received.jsonl")
SECRET_ENV = "EPI_WITNESS_SECRET"


def _log(message: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{stamp}] {message}", file=sys.stderr, flush=True)


def make_handler(
    out: Path,
    secret: str | None,
    *,
    log: Callable[[str], None] = _log,
) -> type[BaseHTTPRequestHandler]:
    """Request handler bound to one output log and (optional) HMAC secret."""
    out_path = Path(out)
    secret_bytes = (secret or "").encode("utf-8")
    write_lock = threading.Lock()

    class WitnessHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (http.server convention)
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                payload = json.loads(body.decode("utf-8"))
            except Exception:
                self._reply(400)
                return
            if (
                not isinstance(payload, dict)
                or payload.get("schema") != WITNESS_SCHEMA
                or payload.get("type") != "epi.sealed"
            ):
                self._reply(400)
                return
            if secret_bytes:
                want = hmac.new(secret_bytes, body, hashlib.sha256).hexdigest()
                got = (self.headers.get("X-EPI-Signature") or "").removeprefix("sha256=")
                if not hmac.compare_digest(want, got):
                    log(
                        f"rejected: bad or missing X-EPI-Signature HMAC from "
                        f"{self.client_address[0]} (workflow {payload.get('workflow_id')}) "
                        "- check the shared secret"
                    )
                    self._reply(401)
                    return
            payload["received_at"] = datetime.now(timezone.utc).isoformat()
            try:
                with write_lock:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    with out_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(payload) + "\n")
            except OSError as exc:
                log(f"error: cannot append to {out_path}: {exc}")
                self._reply(500)
                return
            log(f"accepted: workflow {payload.get('workflow_id')} -> {out_path}")
            self._reply(200)

        def _reply(self, code: int) -> None:
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):  # keep per-request access logs quiet
            pass

    return WitnessHandler


def make_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    out: Path = DEFAULT_OUT,
    secret: str | None = None,
    log: Callable[[str], None] = _log,
) -> HTTPServer:
    """Bind the receiver. Raises OSError (see :func:`bind_error_message`)."""
    return HTTPServer((host, port), make_handler(out, secret, log=log))


def bind_error_message(host: str, port: int, exc: OSError) -> str:
    """One-line, friendly reason a bind failed."""
    # Windows reports a taken port as WSAEADDRINUSE (10048) or, when the
    # other socket holds it exclusively, WSAEACCES (10013).
    if exc.errno == errno.EADDRINUSE or getattr(exc, "winerror", None) in (10048, 10013):
        return (
            f"error: port {port} on {host} is already in use "
            "(another receiver running?). Pick another with --port."
        )
    return f"error: cannot listen on {host}:{port}: {exc}"


def vendor_url(host: str, port: int) -> str:
    """The URL to hand the vendor for EPI_WITNESS_URL."""
    shown = host
    if host in ("", "0.0.0.0", "::"):
        shown = "<this-host>"
    elif ":" in host and not host.startswith("["):
        shown = f"[{host}]"
    return f"http://{shown}:{port}/"


def serve_forever(server: HTTPServer) -> None:
    """Serve until Ctrl-C, then close the socket."""
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reference EPI customer witness receiver. Accepts hash-only seal "
            "reports (schema epi-witness/v1) and appends them to a JSONL log "
            "for `epi verify FILE --policy strict --witness-log LOG`."
        ),
        epilog=(
            "Use --host 0.0.0.0 only behind a TLS-terminating reverse proxy, "
            "so a remote vendor posts to an https:// URL. "
            "Installed equivalent: `epi witness serve`."
        ),
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Interface to listen on (default: 127.0.0.1, this machine only).",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="Port to listen on (default: 8099)."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Append-only witness log to write (default: received.jsonl).",
    )
    parser.add_argument(
        "--secret",
        default=os.environ.get(SECRET_ENV, ""),
        help=(
            "Shared HMAC secret agreed with the vendor (default: EPI_WITNESS_SECRET "
            "env). Without it, the HMAC check is off and any well-formed report is kept."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point of the reference script (examples/witness_receiver/receiver.py)."""
    args = build_parser().parse_args(argv)
    secret = args.secret or ""
    out = args.out
    try:
        server = make_server(args.host, args.port, out=out, secret=secret)
    except OSError as exc:
        print(bind_error_message(args.host, args.port, exc), file=sys.stderr)
        return 2
    print(
        f"witness receiver on {args.host}:{server.server_port} -> {out} "
        f"(hmac {'on' if secret else 'off'})",
        flush=True,
    )
    serve_forever(server)
    return 0


if __name__ == "__main__":
    sys.exit(main())
