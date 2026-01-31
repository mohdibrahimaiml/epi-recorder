"""Test Suite 1: Thread-Safety Verification"""
import threading
import time
import tempfile
from pathlib import Path

errors = []
success_count = [0]

def test_concurrent_recording(thread_id):
    try:
        from epi_recorder import record
        
        # Create temp directory for this thread
        with tempfile.TemporaryDirectory() as tmpdir:
            session_name = f"thread_{thread_id}"
            output_path = Path(tmpdir) / f"{session_name}.epi"
            
            with record(output_path) as ctx:
                # Simulate work
                time.sleep(0.05)
                # Recording context is automatically managed
                
            success_count[0] += 1
            print(f"Thread {thread_id} completed")
            
    except Exception as e:
        errors.append(f"Thread {thread_id}: {str(e)}")
        print(f"Thread {thread_id} failed: {e}")

# Run 10 concurrent threads
threads = []
for i in range(10):
    t = threading.Thread(target=test_concurrent_recording, args=(i,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

if errors:
    print(f"\nFAIL: {len(errors)} threads failed")
    for e in errors:
        print(f"  - {e}")
    exit(1)
else:
    print(f"\nPASS: All {success_count[0]} threads completed successfully - Thread-safe!")


