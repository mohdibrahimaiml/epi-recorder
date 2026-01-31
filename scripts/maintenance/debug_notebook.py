# Debug script to see what's in the demo cell
import json

with open('epi_investor_demo.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

demo = [c for c in nb['cells'] if c.get('metadata',{}).get('id')=='demo'][0]
src = ''.join(demo['source'])

# Find the download section
idx = src.find("# EXTRACT VIEWER")
if idx != -1:
    print("=== DOWNLOAD SECTION ===")
    end_idx = src.find("else:", idx)
    if end_idx != -1:
        section = src[idx:end_idx]
        print(section)
    else:
        print(src[idx:idx+1000])
else:
    print("EXTRACT VIEWER section not found!")
    print("\nSearching for 'DOWNLOAD'...")
    idx2 = src.find("# DOWNLOAD")
    if idx2 != -1:
        print(src[idx2:idx2+800])


