"""
Simple test - no emojis for Windows compatibility
"""

from epi_recorder import record

print("Creating EPI recording...")

with record("test_simple.epi", workflow_name="Simple Test"):
    print("Recording started")
    result = sum(range(1, 101))
    print(f"Sum of 1-100: {result}")
    print("Recording completed")

print("\nSuccess! File created: test_simple.epi")
print("\nVerify with:")
print("  python -m epi_cli.main verify test_simple.epi")


