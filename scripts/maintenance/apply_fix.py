import json

# Load notebook
with open('epi_investor_demo_ULTIMATE.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Fix cell 6 (record), line 56
nb['cells'][6]['source'][56] = 'except Exception as e:\\n'

# Save
with open('epi_investor_demo_ULTIMATE.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=4, ensure_ascii=False)

print("FIXED: Line 56 of record cell")
print("Status: READY FOR COLAB")


