"""Cross-process exclusive lock for a state file (stdlib only).

Windows has no atomic O_APPEND (CPython emulates it as seek+write, so
concurrent writers overwrite each other), and there is no portable fcntl.
The lock is an adjacent ``<path>.lock`` file created with O_CREAT|O_EXCL,
which IS atomic on Windows and POSIX. Stale locks (crashed holder) are
reaped by mtime.

Never raises: on timeout the caller proceeds unlocked with a warning
(availability over perfection; contention windows are milliseconds).

Extracted from the witness outbox in ``epi_core/webhook.py`` so the seal
ledger uses the identical, already-proven mechanism instead of a second
implementation (``webhook`` re-exports the old private name).
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger("epi.filelock")


class FileLock:
    """Exclusive, cross-process lock implemented as ``<path>.lock``."""

    def __init__(
        self, target: Path, *, timeout: float = 10.0, stale_after: float = 30.0
    ) -> None:
        self._lock_path = Path(str(target) + ".lock")
        self._timeout = max(0.5, float(timeout))
        self._stale_after = max(1.0, float(stale_after))
        self._locked = False

    def __enter__(self) -> bool:
        deadline = time.monotonic() + self._timeout
        try:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            return False
        while True:
            try:
                fd = os.open(str(self._lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                self._locked = True
                return True
            except FileExistsError:
                try:
                    age = time.time() - self._lock_path.stat().st_mtime
                    if age > self._stale_after:
                        self._lock_path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
            except OSError:
                # Windows raises a sharing violation when another process is
                # releasing the lock at the same instant. That is contention,
                # not permission to run unlocked: retry until the deadline.
                if time.monotonic() >= deadline:
                    logger.warning(
                        "State lock could not be taken for %s; proceeding unlocked",
                        self._lock_path,
                    )
                    return False
                time.sleep(0.01)
                continue
            if time.monotonic() >= deadline:
                logger.warning("State lock timed out for %s; proceeding unlocked", self._lock_path)
                return False
            time.sleep(0.01)

    def __exit__(self, *exc) -> None:
        if self._locked:
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._locked = False
