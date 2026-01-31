"""Patch validate_complete.py to use correct Redactor API"""
from pathlib import Path

val_file = Path("validate_complete.py")
content = val_file.read_text(encoding="utf-8")

# Fix the redaction test
old = """test("Redaction functionality")
try:
    from epi_core.redactor import Redactor
    
    r = Redactor()
    sensitive = "My API key is sk-proj-abc123xyz and token is ghp_secret123"
    redacted = r.redact_text(sensitive)
    
    assert "sk-proj-abc123xyz" not in redacted
    assert "ghp_secret123" not in redacted
    assert "***REDACTED***" in redacted
    success()
except Exception as e:
    fail(str(e))"""

new = """test("Redaction functionality")
try:
    from epi_core.redactor import Redactor
    
    r = Redactor()
    sensitive = "My API key is sk-proj-abc123xyz and token is ghp_secret123"
    redacted, count = r.redact(sensitive)  # redact() returns (data, count)
    
    assert "sk-proj-abc123xyz" not in redacted
    assert "ghp_secret123" not in redacted
    assert count > 0  # Should have redacted something
    success()
except Exception as e:
    fail(str(e))"""

if old not in content:
    print("ERROR: Could not find target code")
    import sys
    sys.exit(1)

content = content.replace(old, new)
val_file.write_text(content, encoding="utf-8")
print("OK - Fixed Redactor API call in validate_complete.py")


