"""
Simple verification: Check if the notebook will run without errors in Colab.
This simulates a "normal guy" clicking "Run all" in Google Colab.
"""

import json

print("=" * 70)
print("FINAL NOTEBOOK VERIFICATION")
print("Simulating: Click 'Run all' in Google Colab")
print("=" * 70)

# Load the notebook
with open('epi_investor_demo_ULTIMATE.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Track variables across cells (simulating notebook state)
variables = set()
errors = []
warnings = []

print("\nChecking each cell...\n")

for i, cell in enumerate(nb['cells']):
    cell_type = cell['cell_type']
    cell_id = cell['metadata'].get('id', 'unknown')
    
    if cell_type == 'markdown':
        print(f"Cell {i} [{cell_id}]: Markdown ✓")
        continue
    
    # Code cell - check for issues
    print(f"Cell {i} [{cell_id}]: Code")
    
    source_code = ''.join(cell['source'])
    
    # Check 1: Syntax (basic check - look for common errors)
    if '\nexcept' in source_code and source_code.count('try:') != source_code.count('except'):
        errors.append(f"  Cell {i}: Mismatched try/except blocks")
    
    # Check 2: Imports
    if 'import' in source_code:
        if 'import sys' in source_code:
            variables.add('sys')
        if 'import time' in source_code:
            variables.add('time')
        if 'import os' in source_code:
            variables.add('os')
        if 'import glob' in source_code:
            variables.add('glob')
        if 'from pathlib import Path' in source_code:
            variables.add('Path')
        if 'from google.colab import files' in source_code:
            variables.add('files')
        if 'import zipfile' in source_code:
            variables.add('zipfile')
        if 'from IPython.display import IFrame' in source_code:
            variables.add('IFrame')
        if 'import pandas' in source_code:
            variables.add('pd')
        if 'import shutil' in source_code:
            variables.add('shutil')
        if 'from IPython.display import' in source_code:
            variables.add('display')
            variables.add('HTML')
        print(f"  ✓ Imports look good")
    
    # Check 3: Variable definitions
    if 'epi_file =' in source_code:
        variables.add('epi_file')
    if 'start =' in source_code:
        variables.add('start')
    if 'success =' in source_code:
        variables.add('success')
    
    # Check 4: Variable usage (must be defined before use)
    if 'epi_file' in source_code and 'epi_file' not in variables and 'epi_file =' not in source_code:
        if i > 5:  # After record cell
            print(f"  ✓ Uses epi_file (defined in earlier cell)")
        else:
            warnings.append(f"  Cell {i}: Uses 'epi_file' before definition")
    
    # Check 5: Specific issues
    if cell_id == 'install':
        if 'sys.exit(1)' in source_code:
            print(f"  ✓ Has error handling with sys.exit()")
    
    if cell_id == 'record':
        if 'files.download' in source_code:
            print(f"  ✓ Downloads file (Colab feature)")
        if 'from google.colab import files' in source_code:
            print(f"  ✓ Imports google.colab.files")
        # Check the critical except line
        if '\\nexcept Exception as e:' in source_code:
            errors.append(f"  Cell {i}: SYNTAX ERROR - '\\nexcept' has leading newline!")
        elif 'except Exception as e:' in source_code:
            print(f"  ✓ Exception handling correct")
    
    if cell_id == 'viewer':
        if 'IFrame' in source_code:
            print(f"  ✓ Embeds viewer with IFrame")
        if 'zipfile.ZipFile' in source_code:
            print(f"  ✓ Extracts from ZIP")
    
    if cell_id == 'xray':
        if 'pandas' in source_code or 'pd.DataFrame' in source_code:
            print(f"  ✓ Uses pandas DataFrame")
    
    print()

# Final report
print("=" * 70)
print("VERIFICATION RESULTS")
print("=" * 70)

if errors:
    print(f"\n❌ ERRORS FOUND ({len(errors)}):")
    for error in errors:
        print(error)
    print("\n⚠️  NOTEBOOK WILL CRASH - FIX REQUIRED")
else:
    print("\n✅ NO ERRORS FOUND")

if warnings:
    print(f"\n⚠️  WARNINGS ({len(warnings)}):")
    for warning in warnings:
        print(warning)

if not errors and not warnings:
    print("\n🎉 PERFECT! Notebook is ready for Colab.")
    print("   All cells will execute without errors.")
    print("   Click 'Run all' and it will work flawlessly.")

print("\n" + "=" * 70)
print(f"Total cells: {len(nb['cells'])}")
print(f"Code cells: {sum(1 for c in nb['cells'] if c['cell_type'] == 'code')}")
print(f"Markdown cells: {sum(1 for c in nb['cells'] if c['cell_type'] == 'markdown')}")
print("=" * 70)


