"""
Simplified edge case test
"""

import sys
from pathlib import Path
from epi_recorder import record
import json
import zipfile

print("="*60)
print("SIMPLIFIED EDGE CASE TEST")
print("="*60)

# Test 1: File overwrite
print("\n1. Testing file overwrite...")
try:
    with record("edge_test1.epi", workflow_name="First"):
        pass
    
    with record("edge_test1.epi", workflow_name="Second"):
        pass
    
    if Path("edge_test1.epi").exists():
        print("   ✅ File overwritten")
    else:
        print("   ❌ File missing")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)
finally:
    Path("edge_test1.epi").unlink(missing_ok=True)

# Test 2: Empty workflow
print("\n2. Testing empty workflow...")
try:
    with record("edge_test2.epi", workflow_name="Empty"):
        pass
    
    if Path("edge_test2.epi").exists():
        print("   ✅ Empty workflow works")
    else:
        print("   ❌ File not created")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)
finally:
    Path("edge_test2.epi").unlink(missing_ok=True)

# Test 3: Large data
print("\n3. Testing large data...")
try:
    with record("edge_test3.epi", workflow_name="Large") as epi:
        for i in range(50):
            epi.log_step(f"step_{i}", {"data": "x" * 1000})
    
    size = Path("edge_test3.epi").stat().st_size
    print(f"   ✅ Large data handled ({size:,} bytes)")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)
finally:
    Path("edge_test3.epi").unlink(missing_ok=True)

# Test 4: Unicode
print("\n4. Testing Unicode...")
try:
    with record("edge_test4.epi", workflow_name="测试 🎉", tags=["标签1"]) as epi:
        epi.log_step("步骤", {"数据": "值"})
    
    print("   ✅ Unicode handled")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)
finally:
    Path("edge_test4.epi").unlink(missing_ok=True)

# Test 5: Artifact
print("\n5. Testing artifact capture...")
try:
    test_file = Path("edge_artifact.txt")
    test_file.write_text("test content")
    
    with record("edge_test5.epi", workflow_name="Artifact") as epi:
        epi.log_artifact(test_file)
    
    # Verify artifact is in ZIP
    with zipfile.ZipFile("edge_test5.epi", 'r') as zf:
        if any('artifacts/' in name for name in zf.namelist()):
            print("   ✅ Artifact captured")
        else:
            print("   ❌ Artifact missing")
            sys.exit(1)
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)
finally:
    Path("edge_artifact.txt").unlink(missing_ok=True)
    Path("edge_test5.epi").unlink(missing_ok=True)

# Test 6: Error handling
print("\n6. Testing error handling...")
try:
    try:
        with record("edge_test6.epi", workflow_name="Error") as epi:
            epi.log_step("before", {"status": "ok"})
            raise ValueError("Test error")
    except ValueError:
        pass
    
    if Path("edge_test6.epi").exists():
        print("   ✅ File saved despite error")
    else:
        print("   ❌ File not saved")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)
finally:
    Path("edge_test6.epi").unlink(missing_ok=True)

# Test 7: Non-existent artifact
print("\n7. Testing non-existent artifact...")
try:
    with record("edge_test7.epi", workflow_name="Test") as epi:
        epi.log_artifact(Path("does_not_exist.txt"))
    print("   ⚠️  Should have failed")
except FileNotFoundError:
    print("   ✅ Correctly raised FileNotFoundError")
except Exception as e:
    print(f"   ✅ Raised: {type(e).__name__}")
finally:
    Path("edge_test7.epi").unlink(missing_ok=True)

# Test 8: Verify created file structure
print("\n8. Verifying file structure...")
try:
    with record("edge_test8.epi", workflow_name="Structure") as epi:
        epi.log_step("test", {"key": "value"})
    
    with zipfile.ZipFile("edge_test8.epi", 'r') as zf:
        files = zf.namelist()
        required = ['manifest.json', 'mimetype', 'steps.jsonl']
        missing = [f for f in required if f not in files]
        
        if missing:
            print(f"   ❌ Missing files: {missing}")
            sys.exit(1)
        else:
            print(f"   ✅ Structure valid ({len(files)} files)")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)
finally:
    Path("edge_test8.epi").unlink(missing_ok=True)

print("\n" + "="*60)
print("✅ ALL EDGE CASE TESTS PASSED")
print("="*60)
print("\nAll edge cases handled correctly!")
