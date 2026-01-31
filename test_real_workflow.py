"""
Real-world test script - simulating actual agent workflow
"""
import time
print("Test Agent: Starting loan analysis workflow...")

# Simulate LLM call
print("Step 1: Analyzing application data")
time.sleep(0.2)

# Simulate tool call
print("Step 2: Checking credit score")
result = {"score": 680, "status": "approved"}
print(f"Result: {result}")

# Simulate another LLM call
print("Step 3: Generating decision report")
time.sleep(0.1)

print("✅ Workflow complete")


