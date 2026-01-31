
import json
import ast
from pathlib import Path

target_file = r"C:\Users\dell\epi-recorder\EPI_Rainmatter_MVD.ipynb"

print(f"Checking: {target_file}")

try:
    with open(target_file, 'r', encoding='utf-8') as f:
        nb = json.load(f)
    print("[PASS] JSON is valid.")
except Exception as e:
    print(f"[FAIL] JSON verify failed: {e}")
    exit(1)

# Check Cells
cells = nb.get('cells', [])
print(f"Total Cells: {len(cells)}")

code_cells = [c for c in cells if c['cell_type'] == 'code']
markdown_cells = [c for c in cells if c['cell_type'] == 'markdown']

# 1. semantic check
found_seal = False
for cell in code_cells:
    source = "".join(cell['source'])
    if "notary.seal_state = notary.log_step" in source:
        print("[PASS] Semantic Alias 'seal_state' found.")
        found_seal = True
        break

if not found_seal:
    print("[WARN] 'seal_state' alias NOT found in code cells.")

# 2. Syntax Check
print("Checking Python Syntax in cells...")
for i, cell in enumerate(code_cells):
    source = "".join(cell['source'])
    # formatting for notebook magic commands
    clean_source = []
    for line in source.split('\n'):
        if line.strip().startswith('!'):
            clean_source.append(f"# {line}") # Comment out magic commands
        elif line.strip().startswith('%'):
             clean_source.append(f"# {line}")
        else:
            clean_source.append(line)
    
    try:
        ast.parse("\n".join(clean_source))
        print(f"  [PASS] Cell {i} Syntax OK.")
    except SyntaxError as e:
        print(f"  [FAIL] Cell {i} Syntax Error: {e}")
        print("-" * 20)
        print(source)
        print("-" * 20)

# 3. Check Bit Flip Logic
found_bitflip = False
for cell in code_cells:
    source = "".join(cell['source'])
    if "b'\\x00\\xFF\\xFF\\x00'" in source: # Identifying the corruption bytes
        found_bitflip = True
        print("[PASS] Bit-Flip Logic found.")
        break

if not found_bitflip:
    print("[WARN] Bit-Flip specific logic not found.")

print("Verification Compelte.")


