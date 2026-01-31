"""
Script to safely patch the signing method in api.py
"""
import sys
from pathlib import Path

# Read the file
api_file = Path("epi_recorder/api.py")
content = api_file.read_text(encoding="utf-8")

# Find and replace the dangerous pattern
old_code = """                # Repack the ZIP with signed manifest
                self.output_path.unlink()  # Remove old file
                
                with zipfile.ZipFile(self.output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    # Write mimetype first (uncompressed)
                    from epi_core.container import EPI_MIMETYPE
                    zf.writestr("mimetype", EPI_MIMETYPE, compress_type=zipfile.ZIP_STORED)
                    
                    # Write all other files
                    for file_path in tmp_path.rglob("*"):
                        if file_path.is_file() and file_path.name != "mimetype":
                            arc_name = str(file_path.relative_to(tmp_path)).replace("\\\\", "/")
                            zf.write(file_path, arc_name)"""

new_code = """                # Repack the ZIP with signed manifest
                # CRITICAL: Write to temp file first to prevent data loss
                temp_output = self.output_path.with_suffix('.epi.tmp')
                
                with zipfile.ZipFile(temp_output, 'w', zipfile.ZIP_DEFLATED) as zf:
                    # Write mimetype first (uncompressed)
                    from epi_core.container import EPI_MIMETYPE
                    zf.writestr("mimetype", EPI_MIMETYPE, compress_type=zipfile.ZIP_STORED)
                    
                    # Write all other files
                    for file_path in tmp_path.rglob("*"):
                        if file_path.is_file() and file_path.name != "mimetype":
                            arc_name = str(file_path.relative_to(tmp_path)).replace("\\\\", "/")
                            zf.write(file_path, arc_name)
                
                # Successfully created signed file, now safely replace original
                self.output_path.unlink()
                temp_output.rename(self.output_path)"""

# Check if the old code exists
if old_code not in content:
    print("ERROR: Could not find the target code to replace!")
    print("The file may have already been patched or modified.")
    sys.exit(1)

# Replace
new_content = content.replace(old_code, new_code)

# Verify we only made one replacement
if content.count(old_code) != 1:
    print(f"ERROR: Found {content.count(old_code)} instances of target code (expected 1)")
    sys.exit(1)

# Write back
api_file.write_text(new_content, encoding="utf-8")
print("OK - Successfully patched epi_recorder/api.py")
print("OK - Signing method now uses safe temp-file-then-rename pattern")


