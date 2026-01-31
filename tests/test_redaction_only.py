"""Test redaction in isolation"""
from epi_core.redactor import Redactor

r = Redactor()
sensitive = "My API key is sk-proj-abc123xyz and token is ghp_secret123"
print(f"Input: {sensitive}")

result, count = r.redact(sensitive)
print(f"Output: {result}")
print(f"Count: {count}")

# Check what was redacted
print(f"\nChecks:")
print(f"  'sk-proj-abc123xyz' in result: {'sk-proj-abc123xyz' in result}")
print(f"  'ghp_secret123' in result: {'ghp_secret123' in result}")
print(f"  count > 0: {count > 0}")

if "sk-proj-abc123xyz" not in result and "ghp_secret123" not in result and count > 0:
    print("\n✓ TEST PASSED")
else:
    print("\n✗ TEST FAILED")
    if count == 0:
        print("  Patterns didn't match - need to check redaction patterns")


