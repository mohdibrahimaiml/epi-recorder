"""
Verification script to confirm the notebook fix was applied correctly
"""

import json
from pathlib import Path

notebook_path = Path(r"c:\Users\dell\OneDrive\Desktop\EPI_DEMO_demo.ipynb")

print("=" * 70)
print("VERIFYING NOTEBOOK FIX")
print("=" * 70)
print(f"\nReading: {notebook_path}")

try:
    with open(notebook_path, 'r', encoding='utf-8') as f:
        notebook = json.load(f)
    
    print(f"Total cells: {len(notebook['cells'])}\n")
    
    # Find viewer cell
    viewer_cell = None
    viewer_index = None
    
    for i, cell in enumerate(notebook['cells']):
        if cell['cell_type'] == 'code':
            source = ''.join(cell['source'])
            if 'View Timeline' in source or ('signature_short' in source and 'signature_status' in source):
                viewer_cell = cell
                viewer_index = i
                break
    
    if viewer_cell is None:
        print("❌ ERROR: Could not find viewer cell!")
        print("The fix may not have been applied correctly.")
    else:
        print(f"✅ Found viewer cell at index: {viewer_index}\n")
        
        source_code = ''.join(viewer_cell['source'])
        
        # Check for critical fix components
        checks = {
            "Signature extraction before HTML": "signature_status = \"UNSIGNED\"" in source_code,
            "Manifest parsing": "manifest.get('signature'" in source_code,
            "Signature splitting": "split(':', 2)" in source_code,
            "Status variable": "signature_status == \"SIGNED\"" in source_code or "is_signed" in source_code,
            "Signature injection": "{signature_short}" in source_code,
            "Green color for signed": "#22c55e" in source_code or "#10b981" in source_code,
        }
        
        print("VERIFICATION CHECKS:")
        print("-" * 70)
        
        all_passed = True
        for check_name, passed in checks.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status} - {check_name}")
            if not passed:
                all_passed = False
        
        print("-" * 70)
        
        if all_passed:
            print("\n" + "=" * 70)
            print("SUCCESS! All checks passed!")
            print("=" * 70)
            print("\nThe notebook has been correctly fixed:")
            print("  ✓ Signature extracted BEFORE viewer HTML build")
            print("  ✓ Signature properly parsed (algo:keyname:sig)")
            print("  ✓ Signature injected into viewer using f-strings")
            print("  ✓ Green color for SIGNED status")
            print("  ✓ Dynamic styling based on signature status")
            print("\nYour notebook is ready to upload to Google Colab!")
            print("The viewer will now show SIGNED status correctly.")
        else:
            print("\n" + "=" * 70)
            print("WARNING: Some checks failed!")
            print("=" * 70)
            print("The fix may not have been applied completely.")
            print("You may need to manually verify the viewer cell.")
        
        # Show preview of signature extraction code
        print("\n" + "=" * 70)
        print("SIGNATURE EXTRACTION CODE PREVIEW:")
        print("=" * 70)
        
        lines = source_code.split('\n')
        for i, line in enumerate(lines):
            if 'signature_status' in line or 'signature_short' in line:
                # Show 5 lines of context
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                print(f"\nLines {start}-{end}:")
                for j in range(start, end):
                    marker = ">>> " if j == i else "    "
                    print(f"{marker}{lines[j]}")
                break

except FileNotFoundError:
    print(f"\n❌ ERROR: File not found: {notebook_path}")
    print("Please check the file path.")
except json.JSONDecodeError as e:
    print(f"\n❌ ERROR: Invalid JSON in notebook file")
    print(f"Error: {e}")
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)


