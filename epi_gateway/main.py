import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel

# Internal imports (Worker logic)
from .worker import EvidenceWorker

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("epi-gateway")

# --- Schemas ---
class CaptureRequest(BaseModel):
    """
    Data model for the capture endpoint.
    Allows flexibility for different types of evidence.
    """
    kind: str  # e.g., "llm.request", "api.call"
    content: Dict[str, Any]
    meta: Dict[str, Any] = {}  # timestamp, tags, trace_id

# --- Worker Lifecycle ---
worker = EvidenceWorker()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage the lifecycle of the background worker.
    """
    logger.info("🚀 EPI Gateway Starting... Initializing Worker.")
    worker.start()
    yield
    logger.info("🛑 EPI Gateway Shutting down... Stopping Worker.")
    worker.stop()

# --- App Definition ---
app = FastAPI(
    title="EPI Gateway (Sidecar)",
    description="Asynchronous Evidence Capture Sidecar for Enterprise",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """
    Liveness probe for K8s/Docker.
    """
    return {
        "status": "healthy", 
        "queue_size": worker.queue_size(), 
        "processed_count": worker.processed_count
    }

@app.post("/capture", status_code=202)
async def capture_evidence(request: CaptureRequest):
    """
    Fire-and-Forget endpoint.
    Receives evidence, pushes to queue, and returns immediately.
    """
    try:
        # Push to in-memory queue for background processing
        # This is non-blocking and extremely fast.
        worker.enqueue(request.model_dump())
        return {"status": "accepted", "message": "Evidence queued for signing"}
    except Exception as e:
        logger.error(f"Failed to enqueue evidence: {e}")
        # Even if we fail, we try not to crash the caller, but here we must signal error
        raise HTTPException(status_code=500, detail="Internal Gateway Error")


