# Check the full demo cell structure
import json

with open('epi_investor_demo.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

demo = [c for c in nb['cells'] if c.get('metadata',{}).get('id')=='demo'][0]
src = ''.join(demo['source'])

# Print the entire "if epi_file:" block
idx = src.find("if epi_file:")
if idx != -1:
    # Find the corresponding else
    end_idx = src.find("\nelse:", idx)
    if end_idx == -1:
        end_idx = len(src)
    
    block = src[idx:end_idx]
    print("=== FULL 'if epi_file:' BLOCK ===")
    for i, line in enumerate(block.split('\n')):
        # Show leading spaces count
        spaces = len(line) - len(line.lstrip())
        print(f"{spaces:2d}|{line}")


