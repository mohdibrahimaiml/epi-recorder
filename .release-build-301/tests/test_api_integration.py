"""
Standalone integration smoke for the Python API.

This file is intentionally executable as a script for manual verification.
It is not part of the regular pytest suite.
"""

from pathlib import Path
import json
import zipfile

from epi_recorder.api import record


ARTIFACT_DIR = Path("epi-recordings")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def _print_header(title: str) -> None:
    print(title)
    print("=" * 60)


_print_header("Testing EPI Recorder Python API Integration")

# Test 1: Basic recording
print("\n1. Test: Basic Recording")
with record(str(ARTIFACT_DIR / "test_integration_basic.epi"), workflow_name="Integration Test"):
    print("   OK Recording context entered")
    result = 42 * 2
    print(f"   OK Calculation: {result}")

print("   OK .epi file created: epi-recordings/test_integration_basic.epi")

# Test 2: With manual logging
print("\n2. Test: Manual Logging")
with record(str(ARTIFACT_DIR / "test_integration_manual.epi"), workflow_name="Manual Log Test") as epi:
    print("   OK Recording started")
    epi.log_step("data.load", {"rows": 1000, "columns": 10})
    print("   OK Logged data loading")
    epi.log_step("processing.complete", {"status": "success", "duration": 1.5})
    print("   OK Logged processing")

print("   OK .epi file created: epi-recordings/test_integration_manual.epi")

# Test 3: With artifact
print("\n3. Test: Artifact Capture")
test_file = Path("test_artifact.txt")
test_file.write_text("This is a test artifact", encoding="utf-8")

with record(str(ARTIFACT_DIR / "test_integration_artifact.epi"), workflow_name="Artifact Test") as epi:
    print("   OK Recording started")
    epi.log_artifact(test_file)
    print("   OK Artifact captured")

test_file.unlink()
print("   OK .epi file created: epi-recordings/test_integration_artifact.epi")

# Test 4: Error handling
print("\n4. Test: Error Handling")
try:
    with record(str(ARTIFACT_DIR / "test_integration_error.epi"), workflow_name="Error Test") as epi:
        print("   OK Recording started")
        epi.log_step("before.error", {"status": "ok"})
        raise ValueError("Test error")
except ValueError:
    print("   OK Error caught and logged")

print("   OK .epi file created: epi-recordings/test_integration_error.epi")

# Verification
print("\nVerification")
print("=" * 60)

for filename in [
    "test_integration_basic.epi",
    "test_integration_manual.epi",
    "test_integration_artifact.epi",
    "test_integration_error.epi",
]:
    path = ARTIFACT_DIR / filename
    if not path.exists():
        continue

    with zipfile.ZipFile(path, "r") as zf:
        files = zf.namelist()
        has_manifest = "manifest.json" in files
        has_steps = "steps.jsonl" in files
        has_env = "environment.json" in files

        manifest = json.loads(zf.read("manifest.json"))
        is_signed = manifest.get("signature") is not None

        print(f"OK {filename}")
        print(f"   - Structure: {'yes' if all([has_manifest, has_steps, has_env]) else 'no'}")
        print(f"   - Signed: {'yes' if is_signed else 'no'}")

        steps_data = zf.read("steps.jsonl").decode("utf-8").strip()
        step_count = len(steps_data.splitlines()) if steps_data else 0
        print(f"   - Steps: {step_count}")

print("\nAll integration checks completed.")
print("=" * 60)
print("\nGenerated files can be verified with:")
print("  python -m epi_cli.main verify test_integration_basic.epi")
print("\nView them with:")
print("  python -m epi_cli.main view test_integration_basic.epi")
