"""Async seal must not block the event loop.

Guards the marketed claim that epi-recorder seals asynchronously without
blocking the caller. If EPIContainer.pack (or sign/finalize) ever moves
back onto the loop thread, this test fails two independent ways:

1. pack must execute on a worker thread, never the loop thread
   (deterministic thread-identity assertion, no timing involved).
2. A 20ms heartbeat task must keep ticking (max gap < 1s) while a
   multi-hundred-step artifact seals underneath it.
3. The sealed file must still be complete and integrity-clean.
"""

from __future__ import annotations

import asyncio
import tempfile
import threading
import time
from pathlib import Path

from epi_core.container import EPIContainer
from epi_recorder import get_current_session, record


def test_async_seal_does_not_block_event_loop(monkeypatch):
    loop_thread = threading.get_ident()
    pack_threads: list[int] = []
    pack_durations: list[float] = []

    real_pack = EPIContainer.pack

    def spy_pack(*args, **kwargs):
        pack_threads.append(threading.get_ident())
        started = time.monotonic()
        try:
            return real_pack(*args, **kwargs)
        finally:
            pack_durations.append(time.monotonic() - started)

    monkeypatch.setattr(EPIContainer, "pack", spy_pack)

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "async_proof.epi"
        beats: list[float] = []
        stop = asyncio.Event()

        async def heartbeat():
            while not stop.is_set():
                beats.append(time.monotonic())
                await asyncio.sleep(0.02)

        async def main() -> None:
            hb = asyncio.create_task(heartbeat())
            try:
                async with record(
                    str(out),
                    workflow_name="async nonblock proof",
                    goal="prove seal off loop",
                    auto_sign=False,
                ):
                    session = get_current_session()
                    assert session is not None
                    for i in range(300):
                        session.log(
                            "tool.call",
                            tool="proof.tool",
                            input={"i": i, "pad": "x" * 200},
                        )
            finally:
                stop.set()
                await hb

        asyncio.run(main())

        # 1. Pack ran off the loop thread.
        assert pack_threads, "EPIContainer.pack was never called during seal"
        assert all(t != loop_thread for t in pack_threads), (
            f"pack ran on the loop thread {loop_thread}: {pack_threads}"
        )

        # 2. Heartbeat kept ticking through the seal.
        assert len(beats) > 10, f"heartbeat starved: {len(beats)} beats"
        gaps = [b - a for a, b in zip(beats, beats[1:])]
        assert max(gaps) < 1.0, (
            f"event loop blocked for {max(gaps):.2f}s during async seal "
            f"(pack took {pack_durations[0]:.2f}s on a worker thread)"
        )

        # 3. Sealed artifact is complete and clean.
        assert out.exists() and out.stat().st_size > 0
        ok, mismatches = EPIContainer.verify_integrity(out)
        assert ok, mismatches
        manifest = EPIContainer.read_manifest(out)
        assert (manifest.total_steps or 0) >= 300
