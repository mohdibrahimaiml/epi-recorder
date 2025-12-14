"""
Add detailed instrumentation to record() function to trace execution
"""
from pathlib import Path

# Read api.py
api_file = Path("epi_recorder/api.py")
content = api_file.read_text(encoding="utf-8")

# Find the record() function and add logging
# We'll insert print statements at key decision points

old_decorator_check = """    # Check if this is being used as a decorator with arguments
    # If the first argument is not a path but keyword arguments are provided,
    # we need to return a decorator function
    if output_path is None and (goal is not None or notes is not None or metrics is not None or 
                               approved_by is not None or metadata_tags is not None):
        # This is a decorator with arguments, return a decorator function"""

new_decorator_check = """    # Check if this is being used as a decorator with arguments
    # If the first argument is not a path but keyword arguments are provided,
    # we need to return a decorator function
    print(f"[RECORD DEBUG] output_path={output_path}, goal={goal}, metadata_tags={metadata_tags}")  # DEBUG
    if output_path is None and (goal is not None or notes is not None or metrics is not None or 
                               approved_by is not None or metadata_tags is not None):
        print("[RECORD DEBUG] Taking decorator-with-args path")  # DEBUG
        # This is a decorator with arguments, return a decorator function"""

# Also add debug at callable check
old_callable_check = """    # Handle decorator usage: record is called without parentheses
    if callable(output_path):
        func = output_path"""

new_callable_check = """    # Handle decorator usage: record is called without parentheses
    print(f"[RECORD DEBUG] Checking if callable: {callable(output_path)}")  # DEBUG
    if callable(output_path):
        print("[RECORD DEBUG] Taking decorator-without-args path")  # DEBUG
        func = output_path"""

# Add debug at normal path
old_normal_path = """    # Normal context manager usage
    resolved_path = _resolve_output_path(output_path)
    return EpiRecorderSession("""

new_normal_path = """    # Normal context manager usage
    print(f"[RECORD DEBUG] Taking normal context manager path")  # DEBUG
    resolved_path = _resolve_output_path(output_path)
    print(f"[RECORD DEBUG] Resolved path: {resolved_path}")  # DEBUG
    return EpiRecorderSession("""

# Apply replacements
if old_decorator_check in content:
    content = content.replace(old_decorator_check, new_decorator_check)
    print("✓ Added debug to decorator check")
else:
    print("✗ Could not find decorator check")

if old_callable_check in content:
    content = content.replace(old_callable_check, new_callable_check)
    print("✓ Added debug to callable check")
else:
    print("✗ Could not find callable check")

if old_normal_path in content:
    content = content.replace(old_normal_path, new_normal_path)
    print("✓ Added debug to normal path")
else:
    print("✗ Could not find normal path")

# Write back
api_file.write_text(content, encoding="utf-8")
print("\n✓ Instrumented epi_recorder/api.py with debug logging")
