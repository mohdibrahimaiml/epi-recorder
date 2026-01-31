# Debug: Why isn't record() creating files?
from epi_recorder import record
from pathlib import Path
import sys

print("Testing basic record() function...")
print(f"Current directory: {Path.cwd()}")

try:
    # Test 1: No arguments (should auto-generate)
    print("\nTest 1: record() with no path (auto-generate)")
    with record() as epi:
        epi.log_step("TEST", {"data": "test"})
        print(f"  Session output_path: {epi.output_path}")
    
    # Check epi-recordings directory
    epi_dir = Path("./epi-recordings")
    if epi_dir.exists():
        files = list(epi_dir.glob("*.epi"))
        print(f"  Files in epi-recordings: {len(files)}")
        if files:
            latest = max(files, key=lambda p: p.stat().st_mtime)
            print(f"  Latest: {latest.name} ({latest.stat().st_size} bytes)")
    
    # Test 2: Explicit path
    print("\nTest 2: record() with explicit path")
    with record("explicit_test.epi") as epi:
        epi.log_step("TEST", {"data": "test2"})
        print(f"  Session output_path: {epi.output_path}")
    
    explicit_file = Path("explicit_test.epi")
    if explicit_file.exists():
        print(f"  ✅ File created: {explicit_file} ({explicit_file.stat().st_size} bytes)")
        explicit_file.unlink()  # cleanup
    else:
        # Maybe it went to epi-recordings?
        alt_path = Path("epi-recordings/explicit_test.epi")
        if alt_path.exists():
            print(f"  ✅ File created at: {alt_path}")
            alt_path.unlink()
        else:
            print(f"  ❌ File NOT created")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\nDone!")


