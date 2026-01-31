"""
Patch _resolve_output_path to respect user-provided paths
"""
from pathlib import Path

# Read api.py
api_file = Path("epi_recorder/api.py")
content = api_file.read_text(encoding="utf-8")

# Find and remove the auto-directory logic
old_code = """    if output_path is None:
        return _auto_generate_output_path()
    
    path = Path(output_path)
    
    # If path has no directory component (just a filename), put it in epi-recordings/
    if len(path.parts) == 1:
        recordings_dir = Path(os.getenv("EPI_RECORDINGS_DIR", "epi-recordings"))
        recordings_dir.mkdir(parents=True, exist_ok=True)
        path = recordings_dir / path
    
    # Add .epi extension if missing
    if path.suffix != ".epi":
        path = path.with_suffix(".epi")
    
    return path"""

new_code = """    if output_path is None:
        return _auto_generate_output_path()
    
    path = Path(output_path)
    
    # Add .epi extension if missing
    if path.suffix != ".epi":
        path = path.with_suffix(".epi")
    
    return path"""

# Check if the old code exists
if old_code not in content:
    print("ERROR: Could not find the target code to replace!")
    print("The file may have already been patched or modified.")
    import sys
    sys.exit(1)

# Replace
new_content = content.replace(old_code, new_code)

# Write back
api_file.write_text(new_content, encoding="utf-8")
print("OK - Successfully patched _resolve_output_path")
print("OK - Removed auto-directory feature that moved files to epi-recordings/")


