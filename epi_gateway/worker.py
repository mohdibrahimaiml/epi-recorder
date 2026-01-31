import threading
import queue
import time
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# We assume epi_recorder is installed and available
# In a real build, we would handle imports carefully
try:
    from epi_core.trust import sign_manifest
    from epi_core.schemas import ManifestModel
except ImportError:
    # Fallback for dev environment/linting without full install
    pass

logger = logging.getLogger("epi-gateway.worker")

class EvidenceWorker:
    """
    Background worker that processes the evidence queue.
    It handles:
    1. Batching (optional, simple sequential for now)
    2. Signing (CPU intensive, kept off main thread)
    3. Storage (IO intensive)
    """

    def __init__(self, storage_dir: str = "./evidence_vault"):
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = None
        self.storage_path = Path(storage_dir)
        self.processed_count = 0
        
        # Batch Configuration
        self.BATCH_SIZE = 50
        self.BATCH_TIMEOUT = 2.0  # Seconds
        
        # Ensure storage exists
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def start(self):
        """Start the worker thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="EPI-Signer")
        self._thread.start()
        logger.info("Background Signer Thread Started")

    def stop(self):
        """Signal the worker to stop and wait for it."""
        logger.info("Stopping Background Signer...")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10.0) # Increased timeout for flush
        logger.info("Background Signer Stopped")

    def enqueue(self, item: Dict[str, Any]):
        """Non-blocking push to queue."""
        self._queue.put(item)

    def queue_size(self) -> int:
        return self._queue.qsize()

    def _run_loop(self):
        """
        Main processing loop with Batching Strategy.
        """
        buffer = []
        last_flush_time = time.time()

        while not self._stop_event.is_set():
            try:
                try:
                    # 1. Try to get an item (non-blocking wait of 1s)
                    item = self._queue.get(timeout=1.0)
                    buffer.append(item)
                    self._queue.task_done()
                except queue.Empty:
                    pass # Continue to check flush conditions

                # FIX: If buffer is empty, keep resetting timer so we don't flush immediately on first item
                if not buffer:
                    last_flush_time = time.time()

                # 2. Check Batch Size trigger
                if len(buffer) >= self.BATCH_SIZE:
                    self._flush_batch(buffer)
                    buffer = []
                    last_flush_time = time.time()
                
                # 3. Check Time trigger (only if we have data)
                elif len(buffer) > 0 and (time.time() - last_flush_time > self.BATCH_TIMEOUT):
                    logger.info("Batch timeout reached - flushing buffer")
                    self._flush_batch(buffer)
                    buffer = []
                    last_flush_time = time.time()

            except Exception as e:
                logger.error(f"Critical Worker Loop Error: {e}", exc_info=True)
        
        # 4. Final Flush on Shutdown
        if buffer:
            logger.info("Shutdown detected. Flushing remaining items.")
            self._flush_batch(buffer)

    def _flush_batch(self, buffer: list):
        """
        Persist a batch of items to a single file.
        """
        try:
            if not buffer: 
                return

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
            batch_id = f"batch_{timestamp}"
            filename = f"evidence_{batch_id}.json"
            file_path = self.storage_path / filename

            # Payload Wrapper
            payload = {
                "batch_id": batch_id,
                "created_at": str(datetime.utcnow()),
                "count": len(buffer),
                "items": buffer
            }

            # In Prod: Sign the entire 'payload' dict here.
            payload['_signed_batch'] = True 

            with open(file_path, 'w') as f:
                json.dump(payload, f, indent=2)
            
            self.processed_count += len(buffer)
            logger.info(f"💾 Flushed Batch {batch_id}: {len(buffer)} items")
            
        except Exception as e:
            logger.error(f"Failed to flush batch: {e}", exc_info=True)


