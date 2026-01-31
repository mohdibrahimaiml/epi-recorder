"""
Trace what happens when using record() vs EpiRecorderSession
"""
import sys
from pathlib import Path
import time

# Instrument __exit__ to see if it's called
from epi_recorder import EpiRecorderSession
original_exit = EpiRecorderSession.__exit__

def traced_exit(self, *args):
    print(f"[TRACE] __exit__ called on {self.output_path}", file=sys.stderr)
    result = original_exit(self, *args)
    print(f"[TRACE] __exit__ completed, file exists: {self.output_path.exists()}", file=sys.stderr)
    return result

EpiRecorderSession.__exit__ = traced_exit

# Now test both paths
print("\n=== Test 1: Using record() function ===")
from epi_recorder import record
test1 = Path(f"test_record_{int(time.time())}.epi")
print(f"File: {test1}")
with record(test1, goal="Test", metadata_tags=["val"]) as session:
    print(f"Session type: {type(session)}")
    print(f"Session output_path: {session.output_path}")
    session.log_step("test", {"x": 1})
print(f"File exists: {test1.exists()}")
if test1.exists():
    test1.unlink()
    print("SUCCESS")
else:
    print("FAIL")

print("\n=== Test 2: Using EpiRecorderSession class ===")
test2 = Path(f"test_class_{int(time.time())}.epi")
print(f"File: {test2}")
with EpiRecorderSession(test2, goal="Test", metadata_tags=["val"]) as session:
    print(f"Session type: {type(session)}")
    print(f"Session output_path: {session.output_path}")
    session.log_step("test", {"x": 1})
print(f"File exists: {test2.exists()}")
if test2.exists():
    test2.unlink()
    print("SUCCESS")
else:
    print("FAIL")


