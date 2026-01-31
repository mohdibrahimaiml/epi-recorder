# -*- coding: utf-8 -*-
"""
Check and show the current VIEW cell code.
"""

import json
import sys
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

NB_PATH = Path(__file__).parent / "epi_investor_demo.ipynb"

with open(NB_PATH, 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Find the view cell
for cell in nb['cells']:
    if cell.get('metadata', {}).get('id') == 'view':
        src = ''.join(cell['source'])
        print("=" * 80)
        print("VIEW CELL SOURCE CODE:")
        print("=" * 80)
        print(src)
        
        print("\n" + "=" * 80)
        print("CHECKING FOR SIGNATURE INJECTION:")
        print("=" * 80)
        
        if 're.sub(' in src or 'pattern' in src:
            print("[OK] Has regex substitution for signature injection")
        else:
            print("[MISSING] No regex substitution - signature won't be injected!")
        
        if 'manifest.get' in src or '"manifest":' in src:
            print("[OK] References manifest")
        else:
            print("[MISSING] No manifest reference")
        
        if '.signature' in src or "signature" in src:
            print("[OK] References signature")
        else:
            print("[MISSING] No signature reference")
        break


