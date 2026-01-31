"""Debug what path the record() function takes"""
import sys
from pathlib import Path

# Patch record to add debug prints
import epi_recorder.api as api_module
original_record = api_module.record

def debug_record(*args, **kwargs):
    print(f"DEBUG record() called with args={args}, kwargs={kwargs}")
    result = original_record(*args, **kwargs)
    print(f"DEBUG record() returned type: {type(result)}")
    print(f"DEBUG is EpiRecorderSession: {isinstance(result, api_module.EpiRecorderSession)}")
    print(f"DEBUG is callable: {callable(result) and not isinstance(result, api_module.EpiRecorderSession)}")
    return result

api_module.record = debug_record

# Now test
from epi_recorder import record
test_file = Path("debug_record_test.epi")

print("\n=== Calling record() ===")
ctx = record(test_file, goal="Test", metadata_tags=["val"])
print(f"\n=== Got context manager, type={type(ctx)} ===")

print("\n=== Entering context ===")
with ctx as session:
    print("=== Inside context ===")
    session.log_step("test", {"x": 1})
    print("=== Logged step ===")

print("\n=== Exited context ===")
print(f"File exists: {test_file.exists()}")
if test_file.exists():
    print(f"Size: {test_file.stat().st_size}")
    test_file.unlink()
    print("SUCCESS!")
else:
    print("FAIL")


