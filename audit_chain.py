import json
import hashlib
import os

with open(os.path.join("audit_dir", "steps.jsonl"), "r", encoding="utf-8") as f:
    steps = [json.loads(line) for line in f]

for i, step in enumerate(steps):
    # canonical json
    canonical = json.dumps(step, separators=(",", ":"), sort_keys=True)
    step_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    print(f"Step {i} actual hash: {step_hash}")
    if i + 1 < len(steps):
        print(f"Step {i+1} prev_hash : {steps[i+1]['prev_hash']}")
        if step_hash != steps[i+1]['prev_hash']:
            print(f"  -> MISMATCH at step {i} to {i+1}")
        else:
            print(f"  -> MATCH at step {i} to {i+1}")
