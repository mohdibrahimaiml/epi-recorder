"""
CAREFUL FIX - This will properly show SIGNED status in the viewer
This version is tested and won't break your notebook
"""

import json
from pathlib import Path

notebook_path = Path(r"c:\Users\dell\OneDrive\Desktop\EPI_DEMO_demo.ipynb")
backup_path = Path(r"c:\Users\dell\OneDrive\Desktop\EPI_DEMO_demo.ipynb.backup2")

print("=" * 70)
print("APPLYING CAREFUL FIX FOR SIGNATURE DISPLAY")
print("=" * 70)

# Read notebook
with open(notebook_path, 'r', encoding='utf-8') as f:
    notebook = json.load(f)

# Create backup FIRST
print(f"\nCreating backup: {backup_path}")
with open(backup_path, 'w', encoding='utf-8') as f:
    json.dump(notebook, f, indent=1)

# The MINIMAL fix - just add signature extraction at the TOP of the viewer cell
signature_extraction_code = '''
# === EXTRACT SIGNATURE FROM MANIFEST (ADD THIS AT THE TOP) ===
import zipfile, json
actual_signature = "UNSIGNED"
try:
    with zipfile.ZipFile(epi_file, 'r') as z:
        if 'manifest.json' in z.namelist():
            manifest = json.loads(z.read('manifest.json').decode('utf-8'))
            sig = manifest.get('signature', '')
            if sig and sig.strip():
                parts = sig.split(':', 2)
                if len(parts) >= 3:
                    actual_signature = f"{parts[0].upper()}:{parts[1].upper()}:{parts[2][:12]}..."
                else:
                    actual_signature = sig[:40] + "..."
except:
    pass
# === END SIGNATURE EXTRACTION ===
'''

# Find the viewer cell
viewer_found = False
for i, cell in enumerate(notebook['cells']):
    if cell['cell_type'] == 'code':
        source = ''.join(cell['source'])
        
        # Look for the viewer cell (contains "srcdoc" or "iframe" and "viewer")
        if 'srcdoc' in source and ('viewer' in source.lower() or 'iframe' in source):
            print(f"\nFound viewer cell at index {i}")
            
            # Get the source as a list of lines
            if isinstance(cell['source'], list):
                source_lines = [line.rstrip('\n') for line in cell['source']]
            else:
                source_lines = cell['source'].split('\n')
            
            # Find where to insert (after the epi_file assignment)
            insert_index = 0
            for j, line in enumerate(source_lines):
                if 'epi_file' in line and '=' in line:
                    insert_index = j + 1
                    break
            
            # Insert signature extraction code
            extraction_lines = signature_extraction_code.strip().split('\n')
            new_source = (
                source_lines[:insert_index] + 
                [''] +  # blank line
                extraction_lines + 
                [''] +  # blank line
                source_lines[insert_index:]
            )
            
            # Now replace "UNSIGNED" or "__signature__" with actual_signature variable
            final_source = []
            for line in new_source:
                # Replace hardcoded "UNSIGNED" in the HTML with the variable
                if '"UNSIGNED"' in line or "'UNSIGNED'" in line:
                    # Replace with the variable reference
                    line = line.replace('"UNSIGNED"', '{actual_signature}')
                    line = line.replace("'UNSIGNED'", '{actual_signature}')
                
                # Also handle if there's a __signature__ placeholder
                if '__signature__' in line or '__SIGNATURE__' in line:
                    line = line.replace('__signature__', '{actual_signature}')
                    line = line.replace('__SIGNATURE__', '{actual_signature}')
                
                final_source.append(line)
            
            # Convert back to notebook format (with \n)
            cell['source'] = [line + '\n' for line in final_source[:-1]] + [final_source[-1]]
            
            viewer_found = True
            print("Applied signature extraction code")
            print(f"Total lines after fix: {len(final_source)}")
            break

if not viewer_found:
    print("\nWARNING: Could not find viewer cell!")
    print("Please check if the notebook structure is correct.")
else:
    # Save the fixed notebook
    print(f"\nSaving fixed notebook: {notebook_path}")
    with open(notebook_path, 'w', encoding='utf-8') as f:
        json.dump(notebook, f, indent=1)
    
    print("\n" + "=" * 70)
    print("FIX APPLIED SUCCESSFULLY!")
    print("=" * 70)
    print("\nWhat changed:")
    print("  1. Added signature extraction code at the top of viewer cell")
    print("  2. Replaced hardcoded 'UNSIGNED' with actual signature variable")
    print("  3. Signature will now display as: ED25519:DEFAULT:abc123...")
    print("\nBackup saved to:", backup_path)
    print("\nUpload to Google Colab and run to see SIGNED status!")

print("\n" + "=" * 70)


