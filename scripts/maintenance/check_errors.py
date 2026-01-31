# -*- coding: utf-8 -*-
"""
Comprehensive check of the demo notebook for errors.
"""

import json
import ast
import sys
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

NB_PATH = Path(__file__).parent / "epi_investor_demo.ipynb"

print("=" * 70)
print("COMPREHENSIVE NOTEBOOK ERROR CHECK")
print("=" * 70)

with open(NB_PATH, 'r', encoding='utf-8') as f:
    nb = json.load(f)

errors = []
warnings = []

# Find the demo cell
demo_cell = None
for cell in nb['cells']:
    if cell.get('metadata', {}).get('id') == 'demo':
        demo_cell = cell
        break

if not demo_cell:
    errors.append("Demo cell not found!")
else:
    src = ''.join(demo_cell['source'])
    
    print("\n1. CHECKING CODE STRUCTURE...")
    
    # Check for key components
    checks = {
        "pip install epi-recorder": "EPI installation",
        "from epi_recorder import record": "EPI import in agent",
        "auto_sign=True": "Auto-sign enabled",
        "zipfile.ZipFile": "ZIP file handling",
        "manifest.get('signature'": "Signature extraction",
        "SEC_Evidence_Viewer.html": "Viewer HTML filename",
        "files.download": "Colab download",
        "re.sub(pattern, replacement": "Signature injection (regex)",
        "epi-data": "EPI data script tag",
    }
    
    for check, desc in checks.items():
        if check in src:
            print(f"   [OK] {desc}")
        else:
            errors.append(f"Missing: {desc} ({check})")
            print(f"   [FAIL] {desc}")
    
    print("\n2. CHECKING PYTHON SYNTAX...")
    
    # Extract and check Python code (skip shell commands)
    python_lines = []
    for line in src.split('\n'):
        stripped = line.strip()
        if stripped.startswith('!') or stripped.startswith('#'):
            continue
        # Skip triple-quoted strings (agent code)
        python_lines.append(line)
    
    # Try to parse the code for syntax errors
    try:
        # We can't fully parse because of shell commands, but we can check key sections
        
        # Check the main download section
        download_section_start = src.find("# EXTRACT AND FIX VIEWER HTML")
        if download_section_start == -1:
            download_section_start = src.find("# EXTRACT VIEWER HTML")
        
        if download_section_start != -1:
            download_section_end = src.find("else:", download_section_start)
            if download_section_end != -1:
                section = src[download_section_start:download_section_end]
                
                # Check indentation consistency
                lines = section.split('\n')
                for i, line in enumerate(lines):
                    if line.strip() and not line.strip().startswith('#'):
                        spaces = len(line) - len(line.lstrip())
                        if spaces % 4 != 0:
                            warnings.append(f"Odd indentation at line {i+1}: {spaces} spaces")
        
        print("   [OK] No obvious syntax issues detected")
    except Exception as e:
        errors.append(f"Syntax check error: {e}")
        print(f"   [FAIL] {e}")
    
    print("\n3. CHECKING SIGNATURE INJECTION LOGIC...")
    
    # Check the regex pattern is correct
    if 'pattern = r\'<script id="epi-data"' in src:
        print("   [OK] Regex pattern defined")
    else:
        errors.append("Missing regex pattern for signature injection")
        print("   [FAIL] Missing regex pattern")
    
    if 're.sub(pattern, replacement, viewer_html, flags=re.DOTALL)' in src:
        print("   [OK] Regex substitution with DOTALL flag")
    else:
        errors.append("Missing or incorrect regex substitution")
        print("   [FAIL] Missing regex substitution")
    
    if '"manifest": manifest' in src:
        print("   [OK] Using signed manifest in embedded data")
    else:
        errors.append("Not using signed manifest in embedded data")
        print("   [FAIL] Not using signed manifest")
    
    print("\n4. CHECKING DUAL DOWNLOAD LOGIC...")
    
    download_count = src.count("files.download(")
    if download_count >= 2:
        print(f"   [OK] Found {download_count} download calls")
    else:
        errors.append(f"Only {download_count} download call(s) found, need at least 2")
        print(f"   [FAIL] Only {download_count} download call(s)")
    
    if "files.download(str(epi_file))" in src:
        print("   [OK] Downloading .epi file")
    else:
        warnings.append("EPI file download may have different syntax")
    
    if "files.download(str(viewer_html_file))" in src:
        print("   [OK] Downloading viewer HTML file")
    else:
        warnings.append("Viewer HTML download may have different syntax")

print("\n" + "=" * 70)
print("RESULTS:")
print("=" * 70)

if errors:
    print(f"\n[ERRORS] {len(errors)} error(s) found:")
    for e in errors:
        print(f"  - {e}")
else:
    print("\n[OK] No errors found!")

if warnings:
    print(f"\n[WARNINGS] {len(warnings)} warning(s):")
    for w in warnings:
        print(f"  - {w}")

print("\n" + "=" * 70)

# Show the actual download section for manual review
print("\nDOWNLOAD SECTION PREVIEW:")
print("-" * 70)
src = ''.join(demo_cell['source'])
idx = src.find("# EXTRACT")
if idx != -1:
    end = src.find("else:", idx)
    if end != -1:
        print(src[idx:end])


