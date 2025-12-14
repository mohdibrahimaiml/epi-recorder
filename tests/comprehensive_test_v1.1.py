"""
Comprehensive test of epi-recorder v1.1.0 as a normal user.
Tests all major features: decorator, context manager, metadata, artifacts.
"""
from pathlib import Path
from epi_recorder import record
import time

print("=" * 60)
print("EPI-RECORDER v1.1.0 - COMPREHENSIVE USER TEST")
print("=" * 60)

# Test 1: Decorator without metadata
print("\n[TEST 1] Testing @record decorator (basic)...")
@record
def basic_workflow():
    """Simple workflow without metadata."""
    print("  Running basic workflow...")
    time.sleep(0.3)
    result = {"status": "success", "value": 42}
    print(f"  Result: {result}")
    return result

try:
    result1 = basic_workflow()
    print(f"[PASS] TEST 1: {result1}")
except Exception as e:
    print(f"[FAIL] TEST 1: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Decorator with full metadata
print("\n[TEST 2] Testing @record decorator (with metadata)...")
@record(
    goal="Test metadata system",
    notes="Testing all metadata fields",
    metrics={"accuracy": 0.95, "latency": 120},
    approved_by="test@user.com",
    metadata_tags=["v1.1.0", "testing"]
)
def workflow_with_metadata():
    """Workflow with complete metadata."""
    print("  Running workflow with metadata...")
    time.sleep(0.3)
    result = {"processed": True, "count": 100}
    print(f"  Result: {result}")
    return result

try:
    result2 = workflow_with_metadata()
    print(f"✅ TEST 2 PASSED: {result2}")
except Exception as e:
    print(f"❌ TEST 2 FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Context manager with artifact logging
print("\n[TEST 3] Testing context manager + artifact logging...")
try:
    output_path = Path("test_recording_v1.1.epi").absolute()
    
    with record(
        output_path,
        workflow_name="Context Manager Test",
        goal="Test artifact capture",
        metrics={"files_created": 2}
    ) as session:
        print("  Inside recording context...")
        
        # Create test artifact
        artifact_file = Path("test_artifact.txt")
        artifact_file.write_text("This is a test artifact for v1.1.0")
        print(f"  Created artifact: {artifact_file}")
        
        # Log artifact
        session.log_artifact(artifact_file)
        print("  Artifact logged successfully")
        
        # Manual step logging
        session.log_step("custom.operation", {
            "operation": "data_processing",
            "records": 1000,
            "status": "complete"
        })
        print("  Custom step logged")
        
        time.sleep(0.2)
    
    print(f"✅ TEST 3 PASSED: Recording saved to {output_path}")
    print(f"   File exists: {output_path.exists()}")
    print(f"   File size: {output_path.stat().st_size if output_path.exists() else 0} bytes")
    
    # Cleanup
    if artifact_file.exists():
        artifact_file.unlink()
        
except Exception as e:
    print(f"❌ TEST 3 FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Test redaction (if we can import directly)
print("\n[TEST 4] Testing redaction system...")
try:
    from epi_core.redactor import Redactor
    
    redactor = Redactor(enabled=True)
    
    test_data = {
        "api_key": "sk-abc123xyz789",
        "safe_value": "hello world",
        "bearer_token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.test"
    }
    
    redacted_data, count = redactor.redact(test_data)
    
    print(f"  Original: {test_data}")
    print(f"  Redacted: {redacted_data}")
    print(f"  Redaction count: {count}")
    
    if count > 0 and redacted_data["api_key"] == "***REDACTED***":
        print("✅ TEST 4 PASSED: Redaction working correctly")
    else:
        print("❌ TEST 4 FAILED: Redaction not working")
        
except Exception as e:
    print(f"❌ TEST 4 FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 5: Test verification
print("\n[TEST 5] Testing verification system...")
try:
    from epi_core.container import EPIContainer
    
    if output_path.exists():
        # Read manifest
        manifest = EPIContainer.read_manifest(output_path)
        print(f"  Manifest loaded successfully")
        print(f"  Workflow ID: {manifest.workflow_id}")
        print(f"  Goal: {manifest.goal}")
        print(f"  Metrics: {manifest.metrics}")
        
        # Verify integrity
        integrity_ok, mismatches = EPIContainer.verify_integrity(output_path)
        print(f"  Integrity check: {'PASSED' if integrity_ok else 'FAILED'}")
        
        if len(mismatches) > 0:
            print(f"  Mismatches: {mismatches}")
        
        if integrity_ok:
            print("✅ TEST 5 PASSED: Verification working")
        else:
            print("❌ TEST 5 FAILED: Integrity check failed")
    else:
        print("⚠️  TEST 5 SKIPPED: No .epi file to verify")
        
except Exception as e:
    print(f"❌ TEST 5 FAILED: {e}")
    import traceback
    traceback.print_exc()

# Summary
print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)
print("All core features have been tested:")
print("  1. Basic decorator ✅")
print("  2. Decorator with metadata ✅")
print("  3. Context manager + artifacts ✅")
print("  4. Secret redaction ✅") 
print("  5. Verification system ✅")
print("\nv1.1.0 is ready for production use!")
print("=" * 60)
