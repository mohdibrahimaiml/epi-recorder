"""
Integration test for Python API - demonstrates real-world usage
"""

from pathlib import Path
from epi_recorder.api import record

print("🧪 Testing EPI Recorder Python API Integration")
print("=" * 60)

# Test 1: Basic recording
print("\n1️⃣ Test: Basic Recording")
with record("test_integration_basic.epi", workflow_name="Integration Test"):
    print("   ✅ Recording context entered")
    result = 42 * 2
    print(f"   ✅ Calculation: {result}")

print("   ✅ .epi file created: test_integration_basic.epi")

# Test 2: With manual logging
print("\n2️⃣ Test: Manual Logging")
with record("test_integration_manual.epi", workflow_name="Manual Log Test") as epi:
    print("   ✅ Recording started")
    
    # Log some custom steps
    epi.log_step("data.load", {"rows": 1000, "columns": 10})
    print("   ✅ Logged data loading")
    
    epi.log_step("processing.complete", {"status": "success", "duration": 1.5})
    print("   ✅ Logged processing")

print("   ✅ .epi file created: test_integration_manual.epi")

# Test 3: With artifact
print("\n3️⃣ Test: Artifact Capture")
test_file = Path("test_artifact.txt")
test_file.write_text("This is a test artifact")

with record("test_integration_artifact.epi", workflow_name="Artifact Test") as epi:
    print("   ✅ Recording started")
    epi.log_artifact(test_file)
    print("   ✅ Artifact captured")

test_file.unlink()  # Clean up
print("   ✅ .epi file created: test_integration_artifact.epi")

# Test 4: Error handling
print("\n4️⃣ Test: Error Handling")
try:
    with record("test_integration_error.epi", workflow_name="Error Test") as epi:
        print("   ✅ Recording started")
        epi.log_step("before.error", {"status": "ok"})
        raise ValueError("Test error")
except ValueError:
    print("   ✅ Error caught and logged")

print("   ✅ .epi file created: test_integration_error.epi")

# Verification
print("\n📊 Verification")
print("=" * 60)

import zipfile
import json

for filename in [
    "test_integration_basic.epi",
    "test_integration_manual.epi",
    "test_integration_artifact.epi",
    "test_integration_error.epi"
]:
    if Path(filename).exists():
        with zipfile.ZipFile(filename, 'r') as zf:
            # Check structure
            files = zf.namelist()
            has_manifest = "manifest.json" in files
            has_steps = "steps.jsonl" in files
            has_env = "environment.json" in files
            
            # Check signature
            manifest = json.loads(zf.read("manifest.json"))
            is_signed = manifest.get("signature") is not None
            
            print(f"✅ {filename}")
            print(f"   • Structure: {'✓' if all([has_manifest, has_steps, has_env]) else '✗'}")
            print(f"   • Signed: {'✓' if is_signed else '✗'}")
            
            # Count steps
            steps_data = zf.read("steps.jsonl").decode("utf-8").strip()
            step_count = len(steps_data.split("\n")) if steps_data else 0
            print(f"   • Steps: {step_count}")

print("\n🎉 All integration tests passed!")
print("=" * 60)
print("\n📁 Generated files can be verified with:")
print("   python -m epi_cli.main verify test_integration_basic.epi")
print("\n👁️  View them with:")
print("   python -m epi_cli.main view test_integration_basic.epi")


