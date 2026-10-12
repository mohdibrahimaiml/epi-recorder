"""Reference customer witness receiver (stdlib only).

The vendor points their witness webhook at this server. It verifies the
HMAC, stamps `received_at`, and appends each payload to `received.jsonl` —
the file the customer later checks with:

    epi verify run.epi --witness-log received.jsonl

Run:

    python receiver.py --port 8099 --secret SHARED_SECRET --out received.jsonl

The default host is 127.0.0.1 (this machine only). For a vendor on another
machine, listen on 0.0.0.0 behind a TLS-terminating reverse proxy (Caddy,
nginx, a cloud load balancer) and give the vendor the https:// URL. The
secret can also come from the EPI_WITNESS_SECRET environment variable.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SECRET = ""
OUT = Path("received.jsonl")


def _log(message: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{stamp}] {message}", file=sys.stderr, flush=True)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 (http.server convention)
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            self.send_response(400)
            self.end_headers()
            return
        if payload.get("schema") != "epi-witness/v1" or payload.get("type") != "epi.sealed":
            self.send_response(400)
            self.end_headers()
            return
        if SECRET:
            want = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
            got = (self.headers.get("X-EPI-Signature") or "").removeprefix("sha256=")
            if not hmac.compare_digest(want, got):
                _log(
                    f"rejected: bad or missing X-EPI-Signature HMAC from "
                    f"{self.client_address[0]} (workflow {payload.get('workflow_id')}) "
                    "- check the shared secret"
                )
                self.send_response(401)
                self.end_headers()
                return
        payload["received_at"] = datetime.now(timezone.utc).isoformat()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):  # keep per-request access logs quiet
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reference EPI customer witness receiver. Accepts hash-only seal "
            "reports (schema epi-witness/v1) and appends them to a JSONL log "
            "for `epi verify FILE --witness-log LOG`."
        ),
        epilog=(
            "Use --host 0.0.0.0 only behind a TLS-terminating reverse proxy, "
            "so a remote vendor posts to an https:// URL."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to listen on (default: 127.0.0.1, this machine only).",
    )
    parser.add_argument("--port", type=int, default=8099, help="Port to listen on (default: 8099).")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("received.jsonl"),
        help="Append-only witness log to write (default: received.jsonl).",
    )
    parser.add_argument(
        "--secret",
        default=os.environ.get("EPI_WITNESS_SECRET", ""),
        help=(
            "Shared HMAC secret agreed with the vendor (default: EPI_WITNESS_SECRET "
            "env). Without it, the HMAC check is off and any well-formed report is kept."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    global SECRET, OUT
    args = build_parser().parse_args(argv)
    SECRET = args.secret or ""
    OUT = args.out
    try:
        server = HTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            print(
                f"error: port {args.port} on {args.host} is already in use "
                "(another receiver running?). Pick another with --port.",
                file=sys.stderr,
            )
        else:
            print(f"error: cannot listen on {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 2
    print(f"witness receiver on {args.host}:{args.port} -> {OUT} (hmac {'on' if SECRET else 'off'})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
