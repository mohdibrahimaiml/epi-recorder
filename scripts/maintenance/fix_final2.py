import json

# Load notebook
with open('epi_investor_demo_ULTIMATE.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

# List all cells to find the right one
for i, cell in enumerate(nb['cells']):
    cell_type = cell['cell_type']
    cell_id = cell['metadata'].get('id', 'no-id')
    print(f"Cell {i}: {cell_type:10s} - ID: {cell_id}")
    
    # If it's the record code cell, check for the error
    if cell_type == 'code' and cell_id == 'record':
        print(f"  -> FOUND RECORD CELL at index {i}")
        print(f"  -> Source lines: {len(cell['source'])}")
        
        # Find the except line
        for j, line in enumerate(cell['source']):
            if 'except Exception as e' in line:
                print(f"  -> Line {j}: {repr(line[:50])}")  # Show first 50 chars
                if line.startswith('\\n'):
                    print("  -> ERROR: Starts with \\n - FIXING...")
                    cell['source'][j] = line.lstrip('\\n')
                    
                    # Save
                    with open('epi_investor_demo_ULTIMATE.ipynb', 'w', encoding='utf-8') as f:
                        json.dump(nb, f, indent=4, ensure_ascii=False)
                    print("  -> FIXED AND SAVED!")


