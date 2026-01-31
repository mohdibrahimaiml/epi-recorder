import json

# Load notebook
with open('epi_investor_demo_ULTIMATE.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Direct fix - cell 5 is the record cell (code cell #3)
# The source list contains the Python code as individual lines
record_cell = nb['cells'][5]

print(f"Cell type: {record_cell['cell_type']}")
print(f"Cell ID: {record_cell['metadata'].get('id')}")
print(f"Number of source lines: {len(record_cell['source'])}")

# The error is in the source array - look for the except line
for i, line in enumerate(record_cell['source']):
    if 'except Exception as e:' in line:
        print(f"\nLine {i}: {repr(line)}")
        if line.startswith('\\n'):
            print("ERROR FOUND - fixing...")
            record_cell['source'][i] = line.lstrip('\\n')
            print(f"Fixed to: {repr(record_cell['source'][i])}")

# Save
with open('epi_investor_demo_ULTIMATE.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=4, ensure_ascii=False)

print("\nNotebook saved")


