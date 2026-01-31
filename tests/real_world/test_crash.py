import time
import sys
from epi_recorder import record

# TEST 5: Crash Recovery Test
# This intentionally crashes mid-recording to test crash-safety

with record(workflow_name="crash_test"):
    print("Starting recording...")
    
    # Step 1: Normal operation
    print("Step 1: Normal work completed")
    time.sleep(0.5)
    
    # Step 2: Simulate crash
    print("About to crash...")
    time.sleep(0.3)
    sys.exit(1)  # Hard kill


