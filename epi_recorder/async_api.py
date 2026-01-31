import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
from datetime import datetime

from epi_core.storage import EpiStorage
from epi_core.schemas import StepModel

class AsyncRecorder:
    """
    Async-native recorder that doesn't block the event loop.
    Uses background thread for SQLite writes.
    """
    
    def __init__(self, session_name: str, output_dir: str = "."):
        self.session_name = session_name
        self.output_dir = output_dir
        
        # Thread-safe queue for steps
        self._queue = asyncio.Queue()
        
        # Background thread executor (1 thread is enough for SQLite)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="epi_writer")
        
        # Storage instance (created in background thread)
        self._storage: Optional[EpiStorage] = None
        self._writer_task: Optional[asyncio.Task] = None
        
        # State tracking
        self._step_count = 0
        self._done = asyncio.Event()
        self._error: Optional[Exception] = None
    
    async def start(self):
        """Initialize storage in background thread and start writer"""
        # Create storage in thread (SQLite init is also blocking)
        loop = asyncio.get_event_loop()
        self._storage = await loop.run_in_executor(
            self._executor,
            lambda: EpiStorage(self.session_name, self.output_dir)
        )
        
        # Start background writer task
        self._writer_task = asyncio.create_task(self._writer_loop())
    
    async def record_step(self, step_type: str, content: dict):
        """Non-blocking step recording"""
        if self._error:
            raise self._error
        
        self._step_count += 1
        
        # Put in queue (never blocks, just buffers in memory)
        await self._queue.put({
            'index': self._step_count,
            'type': step_type,
            'content': content,
            'timestamp': datetime.utcnow() # StepModel expects datetime
        })
    
    async def _writer_loop(self):
        """Background task: Drains queue to SQLite"""
        try:
            while True:
                # Wait for item with timeout to check for shutdown
                try:
                    step_data = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                
                if step_data is None: # Shutdown sentinel
                   self._queue.task_done()
                   break

                # Write to SQLite in background thread (non-blocking for async)
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    self._executor,
                    self._write_to_storage,
                    step_data
                )
                
                self._queue.task_done()
                
        except asyncio.CancelledError:
            # Graceful shutdown
            pass
        except Exception as e:
            self._error = e
    
    def _write_to_storage(self, step_data: dict):
        """Synchronous SQLite write (runs in background thread)"""
        if self._storage:
            # Construct StepModel
            step = StepModel(
                index=step_data['index'],
                timestamp=step_data['timestamp'],
                kind=step_data['type'],
                content=step_data['content']
            )
            self._storage.add_step(step)
    
    async def stop(self):
        """Finalize: Drain queue, close storage"""
        if not self._writer_task:
            return
        
        # Signal writer to finish
        await self._queue.put(None)
        await self._queue.join()
        
        # Wait for task
        self._writer_task.cancel()
        try:
            await self._writer_task
        except asyncio.CancelledError:
            pass
        
        # Finalize storage in background thread
        if self._storage:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor,
                self._storage.finalize
            )
        
        # Shutdown executor
        self._executor.shutdown(wait=True)

@asynccontextmanager
async def record_async(session_name: str, output_dir: str = "."):
    """
    Async context manager for recording.
    
    Usage:
        async with record_async("my_agent") as rec:
            await agent.arun("task")  # Non-blocking
    """
    recorder = AsyncRecorder(session_name, output_dir)
    await recorder.start()
    try:
        yield recorder
    finally:
        await recorder.stop()


