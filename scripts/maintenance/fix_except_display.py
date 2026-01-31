import json

# Read the notebook
with open('epi_investor_demo_ULTIMATE.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Cell 6 is the record cell
record_cell = nb['cells'][6]
print(f"Cell ID: {record_cell['metadata']['id']}")
print(f"Total source lines: {len(record_cell['source'])}\n")

# Find the problematic line
print("Checking lines around 'except Exception':\n")
for i, line in enumerate(record_cell['source']):
    if 'except Exception' in line:
        print(f"Line {i}: {repr(line)}")
        
        # Check if it starts with newline escape
        if line.startswith('\\n') or line.startswith('\n'):
            print(f"  -> ERROR: Line starts with newline character")
            print(f"  -> Fixing...")
            
            # Remove leading newline
            record_cell['source'][i] = line.lstrip('\n').lstrip('\\n')
            print(f"  -> Fixed to: {repr(record_cell['source'][i])}")

# Save
with open('epi_investor_demo_ULTIMATE.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=2, ensure_ascii=False)

print("\nNotebook saved with proper formatting")


