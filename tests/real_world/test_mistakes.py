"""
TEST 6: Mistake Detector Test
Creates an intentionally buggy agent to test the epi debug command.
"""

from epi_recorder import record
import time

with record(workflow_name="buggy_agent") as rec:
    print("Starting buggy agent...")
    
    # Simulate repetitive pattern (same action 5 times)
    for i in range(5):
        print(f"Iteration {i}: Calling API with same parameters")
        # Simulating same query multiple times (potential infinite loop pattern)
        time.sleep(0.2)
    
    # Simulate inefficient behavior
    print("Making unnecessary redundant calls...")
    for j in range(3):
        print(f"Redundant call {j}")
        time.sleep(0.1)
    
    print("Buggy agent complete")


