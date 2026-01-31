import json

# Load notebook
with open('epi_investor_demo_ULTIMATE.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

# The record cell is at index 5 (6th cell)
record_cell = nb['cells'][5]

# The error is at source index 57 (the line with "\nexcept Exception as e:\n")
# Let's find it properly
source = record_cell['source']
fixed = False

for i, line in enumerate(source):
    if 'except Exception as e:' in line and line.startswith('\\n'):
        print(f"Line {i}: Found error - fixing...")
        # Remove leading \n
        source[i] = 'except Exception as e:\\n'
        fixed = True
        break

if fixed:
    # Save
    with open('epi_investor_demo_ULTIMATE.ipynb', 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=4, ensure_ascii=False)
    print("FIXED: Notebook saved successfully")
else:
    print("ERROR: Could not find the problematic line")


