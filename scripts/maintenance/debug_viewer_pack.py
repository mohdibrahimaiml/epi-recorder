
import zipfile
import json
import os
import shutil
import uuid
from epi_core.container import EPIContainer  
from epi_core.schemas import ManifestModel
from pathlib import Path

# 1. Create a dummy recording
if os.path.exists("debug_test_recording"):
    shutil.rmtree("debug_test_recording")
os.makedirs("debug_test_recording", exist_ok=True)
with open("debug_test_recording/steps.jsonl", "w") as f:
    f.write('{"timestamp": "2023-10-27T10:00:00Z", "kind": "info", "name": "Start", "content": {}}\n')

# 2. Pack it using local code
manifest = ManifestModel(
    workflow_id=str(uuid.uuid4()),  # Valid UUID
    created_at="2023-10-27T10:00:00Z", # Correct field name
    timestamp="2023-10-27T10:00:00Z",
    cli_command="epi run debug",
    spec_version="1.0"
)
epi_path = Path("debug.epi")
if epi_path.exists():
    os.remove(epi_path)

print("Packing .epi file...")
try:
    EPIContainer.pack(Path("debug_test_recording"), manifest, epi_path)

    # 3. Extract viewer.html and check content
    print(f"Checking {epi_path}...")
    with zipfile.ZipFile(epi_path, 'r') as z:
        if 'viewer.html' in z.namelist():
            html = z.read('viewer.html').decode('utf-8')
            
            # Check for data injection
            if '<script id="epi-data" type="application/json">' in html:
                print("FOUND script tag.")
                start_marker = '<script id="epi-data" type="application/json">'
                end_marker = '</script>'
                
                try:
                    start = html.index(start_marker) + len(start_marker)
                    end = html.index(end_marker, start)
                    json_content = html[start:end].strip()
                    
                    data = json.loads(json_content)
                    print(f"JSON Parse Success! Steps: {len(data.get('steps', []))}")
                    
                    if len(data.get('steps', [])) == 0:
                        print("WARNING: Steps array is empty inside JSON.")
                        
                except Exception as e:
                    print(f"JSON Parse/Extraction Failed: {e}")
                    print(f"Snippet: {html[start:start+100]}")
            else:
                print("MISSING script tag entirely.")
                print(f"HTML Preview: {html[:200]}")
        else:
            print("MISSING viewer.html in ZIP.")

except Exception as e:
    print(f"Packing failed: {e}")

# Cleanup
if os.path.exists("debug_test_recording"):
    shutil.rmtree("debug_test_recording")
if epi_path.exists():
    os.remove(epi_path)


