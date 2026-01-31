import time
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from .main import app, worker

# Setup Test Client
client = TestClient(app)

def test_gateway_flow():
    print("Starting Gateway Integration Test...")

    # 1. Clean previous evidence
    vault = Path("./evidence_vault")
    if vault.exists():
        shutil.rmtree(vault)
    vault.mkdir()
    
    # 2. Send Capture Request
    payload = {
        "kind": "test.event",
        "content": {"message": "Hello Enterprise"},
        "meta": {"source": "integration_test"}
    }
    
    print("Sending POST /capture request...")
    start_time = time.time()
    response = client.post("/capture", json=payload)
    duration = time.time() - start_time
    
    # 3. Verify Response (Immediate 202)
    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "message": "Evidence queued for signing"}
    print(f"API Response received in {duration:.4f}s (Non-blocking)")

    # 4. Verification Loop (Wait for Worker)
    print("Waiting for background worker to persist file...")
    timeout = 5
    start_wait = time.time()
    found_file = False
    
    while time.time() - start_wait < timeout:
        files = list(vault.glob("evidence_*.json"))
        if files:
            found_file = True
            print(f"Found evidence file: {files[0].name}")
            
            # Verify content
            import json
            with open(files[0]) as f:
                data = json.load(f)
                # UPDATED FOR BATCHING SUPPORT
                if "items" in data:
                    print("Detected Batch Format. Verifying item 0...")
                    first_item = data["items"][0]
                    assert first_item["content"]["message"] == "Hello Enterprise"
                    assert data.get("_signed_batch") is True
                else:
                    assert data["content"]["message"] == "Hello Enterprise"
                    assert data["_signed"] is True
            print("Evidence content verified")
            break
        time.sleep(0.1)

    if not found_file:
        print("Test Failed: Worker did not persist file in time.")
        exit(1)
        
    print("Gateway Test Passed: API accepted request, Worker processed it.")

if __name__ == "__main__":
    # Manually start/stop worker since TestClient doesn't trigger lifespan events automatically in all versions
    worker.start()
    try:
        test_gateway_flow()
    finally:
        worker.stop()


