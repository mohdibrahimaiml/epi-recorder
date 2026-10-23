"""The viewer server is a cold Python process: the browser must only open
once 127.0.0.1:port actually accepts, otherwise double-click lands on
ERR_CONNECTION_REFUSED (fixed 0.35 s sleep vs 1-3 s cold start).

Deterministic by construction: the tests script _wait_for_port's connector
instead of touching real loopback. Real sockets were tried first and flaked
on Windows (loopback SYNs blackholed for seconds at a time — refused never
arrives, every attempt burns its full timeout), both on CI runners and
locally. What these tests own is the poll-loop logic, not the OS network.
"""

from __future__ import annotations

from epi_cli.view import _wait_for_port


class _ScriptedConnector:
    """Fail `failures` times with ConnectionRefusedError, then succeed."""

    def __init__(self, failures: int):
        self.calls = 0
        self.failures = failures

    def __call__(self, address, timeout=None):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionRefusedError("scripted: server not up yet")
        return self._open()

    class _Open:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _open(self):
        return _ScriptedConnector._Open()


def test_wait_for_port_sees_slow_server():
    connector = _ScriptedConnector(failures=5)
    assert _wait_for_port(52165, timeout_seconds=10.0, _connect=connector) is True
    assert connector.calls == 6


def test_wait_for_port_times_out_on_dead_port():
    connector = _ScriptedConnector(failures=10_000)
    assert _wait_for_port(52165, timeout_seconds=0.6, _connect=connector) is False
    assert connector.calls >= 2
