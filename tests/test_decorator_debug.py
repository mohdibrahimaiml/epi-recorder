"""Test decorator to see what's happening"""
from epi_recorder import record
from pathlib import Path

print("Testing decorator...")

@record
def my_test_workflow():
    print("Inside workflow")
    return "result"

result = my_test_workflow()
print(f"Result: {result}")

# Check for .epi files
epi_files = list(Path(".").glob("*.epi"))
print(f"Found {len(epi_files)} .epi files")
for f in epi_files:
    print(f"  - {f}")


