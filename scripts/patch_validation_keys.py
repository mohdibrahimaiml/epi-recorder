"""Patch validation to use realistic fake keys"""
from pathlib import Path

val_file = Path("validate_complete.py")
content = val_file.read_text(encoding="utf-8")

# Fix test to use realistic fake keys
old = """    r = Redactor()
    sensitive = "My API key is sk-proj-abc123xyz and token is ghp_secret123"
    redacted, count = r.redact(sensitive)  # redact() returns (data, count)
    
    assert "sk-proj-abc123xyz" not in redacted
    assert "ghp_secret123" not in redacted
    assert count > 0  # Should have redacted something"""

new = """    r = Redactor()
    # Use realistic fake keys that match actual patterns
    fake_openai = "sk-proj-" + "a" * 48  # OpenAI project key (48+ chars)
    fake_github = "ghp_" + "b" * 36  # GitHub token (36 chars)
    sensitive = f"My API key is {fake_openai} and token is {fake_github}"
    redacted, count = r.redact(sensitive)
    
    assert fake_openai not in redacted
    assert fake_github not in redacted
    assert count >= 2  # Should have redacted both keys"""

if old not in content:
    print("ERROR: Could not find target code")
    import sys
    sys.exit(1)

content = content.replace(old, new)
val_file.write_text(content, encoding="utf-8")
print("OK - Fixed validation test to use realistic fake keys")


