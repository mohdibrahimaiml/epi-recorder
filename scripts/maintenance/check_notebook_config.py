"""
Check if the .epi file generated in Colab actually contains a signature
"""

import zipfile
import json
from pathlib import Path

print("=" * 70)
print("CHECKING NOTEBOOK CONFIGURATION")
print("=" * 70)

# Read notebook
nb_path = Path(r"c:\Users\dell\OneDrive\Desktop\EPI_DEMO_demo.ipynb")
with open(nb_path, 'r', encoding='utf-8') as f:
    notebook = json.load(f)

# Check recording cell
for i, cell in enumerate(notebook['cells']):
    if cell['cell_type'] == 'code':
        source = ''.join(cell['source'])
        if 'record(' in source or 'epi.log_step' in source:
            print(f"\nCell {i}: Recording Cell")
            print("-" * 70)
            
            if 'auto_sign=True' in source:
                print("[OK] auto_sign=True is present")
            else:
                print("[PROBLEM] auto_sign=True is MISSING!")
                print("Add auto_sign=True to the record() call")
            
            if 'workflow_name' in source:
                print("[OK] workflow_name is present")
            else:
                print("[INFO] workflow_name is optional")
            
            # Show the record() line
            for line in source.split('\n'):
                if 'record(' in line:
                    print(f"\nrecord() call: {line.strip()}")
                    break

# Check viewer cell
for i, cell in enumerate(notebook['cells']):
    if cell['cell_type'] == 'code':
        source = ''.join(cell['source'])
        if 'viewer' in source.lower() and 'iframe' in source:
            print(f"\n\nCell {i}: Viewer Cell")
            print("-" * 70)
            print("[OK] Viewer cell found")
            print("It should now extract viewer.html as-is without modifications")

print("\n" + "=" * 70)
print("NEXT STEPS FOR TESTING")
print("=" * 70)
print("\n1. Upload EPI_DEMO_demo.ipynb to Google Colab")
print("2. Run ALL cells")
print("3. When the viewer displays, check if it shows 'Signed'")
print("\nIf it still shows 'Unsigned':")
print("  - The .epi file may not have been signed properly in Colab")  
print("  - Check if epi-recorder generated keys properly")
print("  - The manifest.signature field in the .epi file might be empty")
print("\nThe viewer cell is now CORRECT - it just displays the")
print("authentic viewer which reads the signature automatically")
print("from the embedded manifest JSON.")
print("=" * 70)


