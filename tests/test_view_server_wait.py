"""The viewer server is a cold Python process: the browser must only open
once 127.0.0.1:port actually accepts, otherwise double-click lands on
ERR_CONNECTION_REFUSED (fixed 0.35 s sleep vs 1-3 s cold start)."""

from __future__ import annotations

import socket
import threading
import time

from epi_cli.view import _wait_for_port


def _serve_late(port: int, delay: float) -> None:
    def _run() -> None:
        time.sleep(delay)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", port))
            srv.listen(1)
            srv.settimeout(10.0)
            try:
                conn, _ = srv.accept()
                conn.close()
            except OSError:
                pass

    threading.Thread(target=_run, daemon=True).start()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_wait_for_port_sees_slow_server():
    port = _free_port()
    _serve_late(port, delay=1.5)
    assert _wait_for_port(port, timeout_seconds=10.0) is True


def test_wait_for_port_times_out_on_dead_port():
    port = _free_port()  # nothing will ever bind here
    assert _wait_for_port(port, timeout_seconds=0.6) is False
