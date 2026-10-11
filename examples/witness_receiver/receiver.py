"""Reference customer witness receiver (stdlib only, ~60 lines).

The vendor points their witness webhook at this server. It verifies the
HMAC, stamps `received_at`, and appends each payload to `received.jsonl` —
the file the customer later checks with:

    epi verify run.epi --witness-log received.jsonl

Run:  python receiver.py [--port 8099] [--secret SHARED_SECRET] [--out received.jsonl]
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PORT = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8099
SECRET = sys.argv[sys.argv.index("--secret") + 1] if "--secret" in sys.argv else ""
OUT = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else Path("received.jsonl")


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
                self.send_response(401)
                self.end_headers()
                return
        payload["received_at"] = datetime.now(timezone.utc).isoformat()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):  # keep logs quiet
        pass


if __name__ == "__main__":
    print(f"witness receiver on :{PORT} -> {OUT} (hmac {'on' if SECRET else 'off'})")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
