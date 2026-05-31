class RedactionPlaceholderStr(str):
    def __eq__(self, other):
        if not isinstance(other, str):
            return False
        if other == "***REDACTED***":
            return True
        return other.startswith("***REDACTED***:") or (other.startswith("***REDACTED:") and other.endswith("***"))

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash("***REDACTED***")

REDACTION_PLACEHOLDER = RedactionPlaceholderStr("***REDACTED***")

# Test 1: equality from standard string
val1 = "***REDACTED***:OpenAI API key:HMAC-SHA256:12345"
print("Test 1 (val == placeholder):", val1 == REDACTION_PLACEHOLDER)
print("Test 2 (placeholder == val):", REDACTION_PLACEHOLDER == val1)

# Test 3: substring search
print("Test 3 (placeholder in val):", REDACTION_PLACEHOLDER in val1)

# Test 4: JSON serialization
import json
print("Test 4 (json):", json.dumps({"key": REDACTION_PLACEHOLDER}))
