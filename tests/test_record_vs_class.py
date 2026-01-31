"""Test via record() function vs EpiRecorderSession class"""
import sys
import time
from pathlib import Path

# Test 1: Using record() function (FAILS)
print("=== Test 1: record() function ===")
from epi_recorder import record
test1 = Path(f"test1_{int(time.time())}.epi")
try:
    with record(test1, goal="Test", metadata_tags=["val"]) as session:
        session.log_step("test", {"x": 1})
    print(f"File exists: {test1.exists()}")
    if test1.exists():
        print(f"Size: {test1.stat().st_size}")
        test1.unlink()
        print("SUCCESS!") 
    else:
        print("FAIL")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Using EpiRecorderSession class directly (WORKS)  
print("\n=== Test 2: EpiRecorderSession class ===")
from epi_recorder import EpiRecorderSession
test2 = Path(f"test2_{int(time.time())}.epi")
try:
    with EpiRecorderSession(test2, goal="Test", metadata_tags=["val"]) as session:
        session.log_step("test", {"x": 1})
    print(f"File exists: {test2.exists()}")
    if test2.exists():
        print(f"Size: {test2.stat().st_size}")
        test2.unlink()
        print("SUCCESS!")
    else:
        print("FAIL")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()


