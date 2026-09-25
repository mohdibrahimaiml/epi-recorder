"""Async seal must not block the event loop.

Guards the marketed claim that epi-recorder seals asynchronously without
blocking the caller. If EPIContainer.pack (or sign/finalize) ever moves
back onto the loop thread, this test fails two independent ways:

1. pack must execute on a worker thread, never the loop thread
   (deterministic thread-identity assertion, no timing involved).
2. While pack runs, a 20ms heartbeat task on the loop must keep ticking.
   The pack wrapper sleeps 2s inside the worker first, so the seal phase
   lasts a deterministic minimum on any hardware: a loop-blocking pack
   would stall the heartbeat for ~2s and fail the 1s bound, while an
   off-loop pack leaves gaps in the tens of milliseconds.
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

# Minimum seal-phase length, enforced inside the worker thread so the
# heartbeat bound below discriminates on any hardware speed.
SEAL_DWELL_SECONDS = 2.0
HEARTBEAT_INTERVAL = 0.02
MAX_LOOP_GAP = 1.0


def test_async_seal_does_not_block_event_loop(monkeypatch):
    loop_thread = threading.get_ident()
    pack_threads: list[int] = []

    real_pack = EPIContainer.pack

    def spy_pack(*args, **kwargs):
        pack_threads.append(threading.get_ident())
        time.sleep(SEAL_DWELL_SECONDS)
        return real_pack(*args, **kwargs)

    monkeypatch.setattr(EPIContainer, "pack", spy_pack)

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "async_proof.epi"
        beats: list[float] = []
        stop = asyncio.Event()
        seal_start = 0.0
        seal_end = 0.0

        async def heartbeat():
            while not stop.is_set():
                beats.append(time.monotonic())
                await asyncio.sleep(HEARTBEAT_INTERVAL)

        async def main() -> None:
            nonlocal seal_start, seal_end
            hb = asyncio.create_task(heartbeat())
            try:
                ctx = record(
                    str(out),
                    workflow_name="async nonblock proof",
                    goal="prove seal off loop",
                    auto_sign=False,
                )
                await ctx.__aenter__()
                try:
                    session = get_current_session()
                    assert session is not None
                    for i in range(50):
                        session.log(
                            "tool.call",
                            tool="proof.tool",
                            input={"i": i},
                        )
                finally:
                    # __aexit__ (env capture, finalize, pack, cleanup)
                    # runs here: this timestamp pair is the seal window.
                    seal_start = time.monotonic()
                    await ctx.__aexit__(None, None, None)
                    seal_end = time.monotonic()
            finally:
                stop.set()
                await hb

        asyncio.run(main())

        # 1. Pack ran off the loop thread.
        assert pack_threads, "EPIContainer.pack was never called during seal"
        assert all(t != loop_thread for t in pack_threads), (
            f"pack ran on the loop thread {loop_thread}: {pack_threads}"
        )

        # 2. Heartbeat kept ticking through the >=2s seal window.
        assert seal_end > seal_start + SEAL_DWELL_SECONDS, (
            "seal window shorter than the enforced worker dwell"
        )
        window_beats = [b for b in beats if seal_start <= b <= seal_end]
        assert len(window_beats) >= 50, (
            f"heartbeat starved during seal: {len(window_beats)} beats in "
            f"{seal_end - seal_start:.2f}s"
        )
        gaps = [b - a for a, b in zip(window_beats, window_beats[1:])]
        assert max(gaps) < MAX_LOOP_GAP, (
            f"event loop blocked for {max(gaps):.2f}s during async seal"
        )

        # 3. Sealed artifact is complete and clean.
        assert out.exists() and out.stat().st_size > 0
        ok, mismatches = EPIContainer.verify_integrity(out)
        assert ok, mismatches
        manifest = EPIContainer.read_manifest(out)
        assert (manifest.total_steps or 0) >= 50
