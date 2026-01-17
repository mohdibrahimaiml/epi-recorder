import json
import zipfile
import hashlib
import time
from pathlib import Path
import os

# Create EPI file WITH viewer
def create_visualizer_evidence():
    manifest = {
        "spec_version": "1.0",
        "workflow_id": "VISUAL-TEST-002",
        "created_at": "2026-01-16T12:00:00Z",
        "signature": "ed25519:test_key:mock_signature_visual",
        "file_manifest": {},
        "environment": {
            "os_name": "Windows",
            "platform": "win32",
            "python_version": "3.9.13"
        }
    }

    # Files
    files = {
        "main.py": "print('Visual Test')",
        "logs.txt": "[INFO] Viewer Loaded"
    }

    # Steps
    steps = [
        {"index": 0, "kind": "term.command", "timestamp": time.time(), "content": {"command": "python visual_test.py"}},
        {"index": 1, "kind": "term.output", "timestamp": time.time(), "content": {"output": "Rendering Charts..."}}
    ]
    steps_content = "\n".join(json.dumps(s) for s in steps)

    # Hash files
    for name, content in files.items():
        manifest["file_manifest"][name] = hashlib.sha256(content.encode()).hexdigest()
    
    # Read actual viewer template
    viewer_path = Path("distribution_ready/extracted_demo/viewer.html")
    if viewer_path.exists():
        viewer_html = viewer_path.read_text(encoding="utf-8")
        # Inject data just like real recorder
        data_json = json.dumps({"manifest": manifest, "steps": steps})
        # Simple string replace for demo purposes (real recorder uses jinja or soup)
        # But wait, the file I read has PRE-REQ data. I should just use it as is but replace the DATA block if I can, or just mock it.
        # For simplicity, let's just use the file AS IS, but we need to update the manifest inside the script tag if we want it to match?
        # Actually, let's just Use the file As IS. It already has valid JSON data inside it.
        # But we need to make sure the outer manifest matches.
        pass
    else:
        viewer_html = "<h1>Fallback Viewer</h1><p>Real viewer not found.</p>"

    # Write Zip
    with zipfile.ZipFile("visualizer_evidence.epi", "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip")
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("steps.jsonl", steps_content)
        zf.writestr("viewer.html", viewer_html)
        for name, content in files.items():
            zf.writestr(name, content)
            
    print("Created visualizer_evidence.epi")

if __name__ == "__main__":
    create_visualizer_evidence()
