# Show what the pip install line actually is
import json

with open('epi_investor_demo.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

for cell in nb['cells']:
    if cell.get('metadata', {}).get('id') == 'demo':
        src = ''.join(cell['source'])
        # Find pip line
        for line in src.split('\n'):
            if 'pip' in line.lower():
                print(f"Found: {line}")


