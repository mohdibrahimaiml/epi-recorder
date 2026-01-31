
import os
import time
import requests
import json
from pathlib import Path
from epi_recorder.api import record
from epi_recorder.patcher import get_recording_context
from epi_core.redactor import get_default_redactor

def test_scalability():
    print("\n[TEST] Scalability (Memory Leak Fix)")
    
    # Create a dummy recording
    with record(output_path="test_scale.epi", auto_sign=False) as session:
        context = get_recording_context()
        
        # Verify steps list is NOT growing in memory
        # We can't easily check memory usage directly in a short script without psutil,
        # but we can check if the 'steps' attribute exists or is empty/removed
        
        if hasattr(context, 'steps'):
            print("WARNING: context.steps attribute still exists!")
            # It might exist but be unused/empty if we just commented out the append
            # Let's add some steps
            for i in range(100):
                session.log_step("test.step", {"index": i})
            
            # Check if it grew
            if len(context.steps) > 0:
                 print(f"FAIL: In-memory steps list grew to {len(context.steps)} items (Memory Leak!)")
            else:
                 print("PASS: In-memory steps list remained empty (Fix verified)")
        else:
             print("PASS: context.steps attribute removed (Fix verified)")

def test_robustness():
    print("\n[TEST] Robustness (Requests Patching)")
    
    actual_output_path = None
    with record(output_path="test_requests.epi", auto_sign=False) as session:
        actual_output_path = session.output_path
        print("Making HTTP request to httpbin.org...")
        try:
            requests.get("https://httpbin.org/get", headers={"X-Test": "True"})
        except Exception as e:
            print(f"Request failed: {e}")
            
    # Verify output
    if not actual_output_path or not actual_output_path.exists():
        raise FileNotFoundError(f"Output file not found: {actual_output_path}")
        
    print(f"Verifying capture in {actual_output_path}...")
    
    import zipfile
    found_request = False
    with zipfile.ZipFile(actual_output_path, 'r') as zf:
        steps_content = zf.read("steps.jsonl").decode("utf-8")
        for line in steps_content.splitlines():
            step = json.loads(line)
            if step["kind"] == "http.request":
                print(f"PASS: Captured http.request: {step['content']['url']}")
                found_request = True
                break
    
    if not found_request:
        print("FAIL: Did not capture http.request")

def test_redaction_allowlist():
    print("\n[TEST] Redaction Allowlist")
    
    # Setup redactor with allowlist
    redactor = get_default_redactor()
    redactor.allowlist.add("sk-safe-key-123")
    
    # Test case 1: Should be redacted (standard key)
    secret = "sk-" + "a" * 48
    redacted, count = redactor.redact(secret)
    if redacted == "***REDACTED***":
        print("PASS: Standard secret redacted")
    else:
        print(f"FAIL: Standard secret NOT redacted: {redacted}")
        
    # Test case 2: Should NOT be redacted (allowlist)
    safe = "sk-safe-key-123"
    redacted, count = redactor.redact(safe)
    if redacted == safe:
        print("PASS: Allowlisted key preserved")
    else:
        print(f"FAIL: Allowlisted key was redacted: {redacted}")

if __name__ == "__main__":
    try:
        test_scalability()
        test_robustness()
        test_redaction_allowlist()
        print("\nAll tests completed.")
    except Exception as e:
        print(f"\nTEST SUITE FAILED: {e}")
        import traceback
        traceback.print_exc()


