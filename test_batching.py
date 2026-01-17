import requests
import time
import os
import glob
import json
import shutil

EVIDENCE_DIR = "./evidence_vault"
URL = "http://127.0.0.1:8000/capture"

def clean_vault():
    """Clear old evidence to ensure clean test."""
    if os.path.exists(EVIDENCE_DIR):
        for f in glob.glob(f"{EVIDENCE_DIR}/*.json"):
            os.remove(f)
    print("Vault cleaned.")

def send_requests(n=5):
    """Send N requests rapidly."""
    print(f"Sending {n} requests in a burst...")
    for i in range(n):
        # Must match CaptureRequest(kind, content, meta)
        payload = {
            "kind": "manual_test", 
            "content": {"command": f"Batch Test {i}", "id": i},
            "meta": {"tag": "batch-verify"}
        }
        try:
            r = requests.post(URL, json=payload)
            if r.status_code != 202:
                print(f"ERROR: Status {r.status_code} - {r.text}")
        except Exception as e:
            print(f"Gateway Error: {e}")
            return False
    print("Requests sent.")
    return True

def verify_batch(expected_count=5):
    """Wait for timeout and check file."""
    print("Waiting 10 seconds for batch timeout (2s)...")
    time.sleep(10) # Wait for buffer flush
    
    files = glob.glob(f"{EVIDENCE_DIR}/*.json")
    if len(files) == 0:
        print("FAIL: No file created.")
        return
    
    if len(files) > 1:
        print(f"FAIL: Too many files ({len(files)}). Batching didn't work.")
        return

    # Check content
    with open(files[0], 'r') as f:
        data = json.load(f)
    
    actual_count = data.get("count", 0)
    items = data.get("items", [])
    
    if actual_count == expected_count and len(items) == expected_count:
        print(f"SUCCESS: Created 1 file with {actual_count} items.")
        print(f"Batch ID: {data.get('batch_id')}")
    else:
        print(f"FAIL: Expected {expected_count} items, found {actual_count}.")

if __name__ == "__main__":
    print("TEST: Gateway Smart Batching")
    clean_vault()
    if send_requests(5):
        verify_batch(5)
