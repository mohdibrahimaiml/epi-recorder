import json

# Load notebook
with open('epi_investor_demo_complete.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

print("Checking for errors...")

# Find and fix the error in the record cell (cell index 6)
record_cell = nb['cells'][6]

print("\\nChecking record cell...")
print(f"Cell type: {record_cell['cell_type']}")
print(f"Cell ID: {record_cell['metadata']['id']}")

# Find the problematic line
source = record_cell['source']
for i, line in enumerate(source):
    if '\\nexcept Exception as e:' in line:
        print(f"\\nFOUND ERROR at line {i}!")
        print(f"Current: {repr(line)}")
        
        # Fix it
        source[i] = line.replace('\\nexcept Exception as e:', 'except Exception as e:')
        
        print(f"Fixed to: {repr(source[i])}")
        print("Error corrected!")
        break

# Save the corrected notebook
with open('epi_investor_demo_complete.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=2)

print("\\nNOTEBOOK FIXED AND SAVED")
print("\\nFile: epi_investor_demo_complete.ipynb")
print("Status: READY FOR COLAB")


