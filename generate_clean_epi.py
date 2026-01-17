import json
import zipfile
import hashlib
import time
from pathlib import Path

# Create a clean EPI file manally to ensure NO embedded viewer
def create_clean_evidence():
    manifest = {
        "spec_version": "1.0",
        "workflow_id": "CLEAN-AUDIT-TEST-001",
        "created_at": "2026-01-16T10:00:00Z",
        "signature": "ed25519:test_key:mock_signature_for_demo",
        "file_manifest": {},
        "environment": {
            "os_name": "Windows",
            "platform": "win32",
            "python_version": "3.9.13"
        }
    }

    # Create dummy files
    files = {
        "main.py": "print('Hello World')",
        "requirements.txt": "requests==2.28.1",
        "logs.txt": "[INFO] System initialized\n[INFO] Audit logging enabled"
    }

    # Create steps.jsonl
    steps = [
        {"index": 0, "kind": "term.command", "timestamp": time.time(), "content": {"command": "python main.py"}},
        {"index": 1, "kind": "term.output", "timestamp": time.time(), "content": {"output": "Hello World"}}
    ]
    steps_content = "\n".join(json.dumps(s) for s in steps)

    # Hash files
    for name, content in files.items():
        manifest["file_manifest"][name] = hashlib.sha256(content.encode()).hexdigest()
    
    # Write Zip
    with zipfile.ZipFile("clean_evidence.epi", "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip")
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("steps.jsonl", steps_content)
        for name, content in files.items():
            zf.writestr(name, content)
            
    print("Created clean_evidence.epi")

if __name__ == "__main__":
    create_clean_evidence()
