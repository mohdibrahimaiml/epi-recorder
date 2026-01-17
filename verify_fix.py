
import json
import zipfile
import tempfile
import os
from pathlib import Path
from epi_recorder.api import record
from epi_core.container import EPIContainer

def test_viewer_fix():
    print("Testing Viewer Fix...")
    
    # 1. Create a recording
    output_path = Path.cwd() / "test_fix.epi"
    if output_path.exists():
        os.remove(output_path)
        
    print("Recording...")
    with record(output_path=str(output_path), goal="Verify Security Fix"):
        print("Hello World")
        
    # 2. Inspect the output
    print(f"Created {output_path}")
    
    with zipfile.ZipFile(output_path, "r") as zf:
        # Check manifest
        manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
        print("\n[Manifest Check]")
        print(f"Spec Version: {manifest_data.get('spec_version')}")
        print(f"Public Key: {manifest_data.get('public_key')}")
        
        assert manifest_data.get("spec_version") == "1.1-json", "Spec version not updated"
        assert manifest_data.get("public_key") is not None, "Public key missing in manifest"
        
        # Check viewer.html injection
        viewer_html = zf.read("viewer.html").decode("utf-8")
        print("\n[Viewer Check]")
        
        if "const noble =" in viewer_html:
            print("SUCCESS: crypto.js (noble) injected")
        else:
            print("FAIL: crypto.js NOT injected")
            
        if "verifyManifestSignature(manifest)" in viewer_html:
            print("SUCCESS: app.js updated to call verification")
        else:
            print("FAIL: app.js verification call missing")

    # 3. Clean up
    # os.remove(output_path)
    print("\nTest Complete.")

if __name__ == "__main__":
    test_viewer_fix()
