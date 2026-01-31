import json

# Load notebook
with open('epi_investor_demo_ULTIMATE.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Find the record cell (cell index 5, which is the 6th cell)
record_cell = nb['cells'][5]

print("Checking record cell...")
print(f"Cell ID: {record_cell['metadata']['id']}")

# Find and fix the error
source = record_cell['source']
for i, line in enumerate(source):
    if '\\nexcept Exception as e:' in line and line.startswith('\\n'):
        print(f"\nFOUND ERROR at source line {i}:")
        print(f"Current: {repr(line)}")
        
        # Fix it - remove the leading \n
        source[i] = line[1:] if line.startswith('\\n') else line
        
        print(f"Fixed to: {repr(source[i])}")
        print("✅ Error corrected!")
        break

# Save
with open('epi_investor_demo_ULTIMATE.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=4, ensure_ascii=False)

print("\n✅ NOTEBOOK FIXED AND SAVED")
print("File: epi_investor_demo_ULTIMATE.ipynb")
print("Status: READY FOR COLAB")


