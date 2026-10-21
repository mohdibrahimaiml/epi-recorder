"""The viewer server is a cold Python process: the browser must only open
once 127.0.0.1:port actually accepts, otherwise double-click lands on
ERR_CONNECTION_REFUSED (fixed 0.35 s sleep vs 1-3 s cold start)."""

from __future__ import annotations

import socket
import threading
import time

from epi_cli.view import _wait_for_port


def _serve_late(port: int, delay: float) -> list:
    """Bind 127.0.0.1:port after `delay` seconds, like a cold server process.

    Retries the bind: on a busy CI runner the port picked by _free_port() can
    be stolen between release and rebind. Without retries the thread died
    silently and _wait_for_port timed out — a flaky test, not product behavior
    (seen once on the Windows release gate). Errors are collected so a real
    failure is loud instead of surfacing as a bare timeout assert.
    """
    errors: list = []

    def _run() -> None:
        time.sleep(delay)
        srv = None
        deadline = time.monotonic() + 8.0
        while srv is None:
            try:
                srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind(("127.0.0.1", port))
            except OSError as exc:
                if srv is not None:
                    srv.close()
                    srv = None
                if time.monotonic() >= deadline:
                    errors.append(exc)
                    return
                time.sleep(0.2)
                continue
        try:
            srv.listen(1)
            srv.settimeout(10.0)
            try:
                conn, _ = srv.accept()
                conn.close()
            except OSError as exc:
                errors.append(exc)
        finally:
            srv.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return errors


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_wait_for_port_sees_slow_server():
    port = _free_port()
    errors = _serve_late(port, delay=1.5)
    assert _wait_for_port(port, timeout_seconds=10.0) is True
    assert errors == []


def test_wait_for_port_times_out_on_dead_port():
    port = _free_port()  # nothing will ever bind here
    assert _wait_for_port(port, timeout_seconds=0.6) is False
