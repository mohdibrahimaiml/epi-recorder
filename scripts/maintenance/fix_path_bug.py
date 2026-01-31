import json

# Load notebook
with open('epi_investor_demo_complete.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Fix the bug in cell 7 (the "view" cell - index 6 after the inserted viewer note)
# The cell that extracts and displays data
cell = nb['cells'][7]  # This is the view cell
src = cell['source']

# Replace the incorrect workspace/ path
new_src = []
for line in src:
    # Fix the workspace/ path
    new_line = line.replace("extract_dir / 'workspace' / 'trade_audit.json'", 
                           "extract_dir / 'trade_audit.json'")
    new_src.append(new_line)

cell['source'] = new_src

# Save
with open('epi_investor_demo_complete.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=2)

print("SUCCESS: Fixed workspace/ path bug")
print("Changed: extract_dir / 'workspace' / 'trade_audit.json'")
print("To:      extract_dir / 'trade_audit.json'")


