"""
Detached local HTTP server for epi view.

Runs as a separate process so `epi view` can exit immediately while the
browser keeps loading http://127.0.0.1:<port>/viewer.html.

Usage:
  python -m epi_cli.view_server <directory> <port> [lifetime_seconds]
"""

from __future__ import annotations

import http.server
import socketserver
import sys
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        print("usage: python -m epi_cli.view_server <directory> <port> [lifetime]", file=sys.stderr)
        return 2

    directory = Path(args[0]).resolve()
    port = int(args[1])
    lifetime = float(args[2]) if len(args) > 2 else 900.0

    if not directory.is_dir():
        print(f"not a directory: {directory}", file=sys.stderr)
        return 2

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(directory), **k)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    socketserver.TCPServer.allow_reuse_address = True
    try:
        httpd = socketserver.TCPServer(("127.0.0.1", port), QuietHandler)
    except OSError as exc:
        print(f"bind failed: {exc}", file=sys.stderr)
        return 1

    # Stop after lifetime so orphaned servers do not last forever
    def _stop() -> None:
        time.sleep(max(30.0, lifetime))
        try:
            httpd.shutdown()
        except Exception:
            pass

    import threading

    threading.Thread(target=_stop, name="epi-view-server-stop", daemon=True).start()
    try:
        httpd.serve_forever(poll_interval=0.5)
    except Exception:
        pass
    try:
        httpd.server_close()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
