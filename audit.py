import json
import hashlib
import os

audit_dir = "audit_dir"

with open(os.path.join(audit_dir, "manifest.json"), "r", encoding="utf-8") as f:
    manifest = json.load(f)

print("--- FILE HASH CHECKS ---")
file_hashes = manifest["file_manifest"]
for fname, expected_hash in file_hashes.items():
    fpath = os.path.join(audit_dir, fname)
    if os.path.exists(fpath):
        with open(fpath, "rb") as f:
            content = f.read()
            actual_hash = hashlib.sha256(content).hexdigest()
            if actual_hash == expected_hash:
                print(f"[OK] {fname}")
            else:
                print(f"[FAIL] {fname} - Expected: {expected_hash}, Actual: {actual_hash}")
    else:
        print(f"[MISSING] {fname}")

print("\n--- CHAIN VERIFICATION ---")
with open(os.path.join(audit_dir, "steps.jsonl"), "r", encoding="utf-8") as f:
    steps = [json.loads(line) for line in f]

prev_hash = None
broken = False
for i, step in enumerate(steps):
    step_id = step.get("id")
    actual_prev_hash = step.get("prev_hash")
    
    if i == 0:
        if actual_prev_hash is not None:
            print(f"Step 0 should have null prev_hash, got {actual_prev_hash}")
    else:
        if actual_prev_hash != prev_hash:
            print(f"[BROKEN CHAIN] Step {i} (id: {step_id}): Expected prev_hash {prev_hash}, got {actual_prev_hash}")
            broken = True
            print(f"Step Content: {json.dumps(step, indent=2)}")
            print(f"Previous Step Content: {json.dumps(steps[i-1], indent=2)}")
            break
            
    # Calculate hash of current step for next iteration
    # Depending on how the recorder computes the chain, it's usually hash of step content
    # Let's just output the step ID and timestamp
    # Actually EPI computes hash of canonical JSON string of the step.
    
    # We'll just look for the anomaly.
    pass

if not broken:
    print("Chain links look consistent locally, but hash mismatch might mean content was altered.")

print("\n--- LLM/TOOL ACTIVITY ---")
for step in steps:
    step_type = step.get("type", step.get("action"))
    print(f"{step.get('timestamp', step.get('created_at', ''))} | {step_type} | {step.get('id')}")
    if step_type in ("llm_call", "tool_call", "agent_decision"):
        print(json.dumps(step, indent=2))
