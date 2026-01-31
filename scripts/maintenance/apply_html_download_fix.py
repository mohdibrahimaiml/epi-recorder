# -*- coding: utf-8 -*-
"""
Apply self-contained HTML download fix to the investor demo notebook.
This extracts viewer.html from the .epi file and downloads it alongside the .epi file,
so investors can double-click to open the evidence in any browser.
"""

import json
import sys
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

NB_PATH = Path(__file__).parent / "epi_investor_demo.ipynb"

print(f"Loading: {NB_PATH}")
with open(NB_PATH, 'r', encoding='utf-8') as f:
    nb = json.load(f)

# New download section code
NEW_DOWNLOAD_SECTION = [
    "    # EXTRACT VIEWER HTML FOR EASY VIEWING\n",
    "    viewer_html_file = Path('SEC_Evidence_Viewer.html')\n",
    "    with zipfile.ZipFile(epi_file, 'r') as z:\n",
    "        if 'viewer.html' in z.namelist():\n",
    "            viewer_html_file.write_bytes(z.read('viewer.html'))\n",
    '            print(f"Extracted: {viewer_html_file.name} (opens in any browser!)")\n',
    "    \n",
    "    # DOWNLOAD BOTH FILES\n",
    '    print("\\n" + "=" * 70)\n',
    """    display(HTML('<div style="background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 25px; border-radius: 12px; text-align: center; margin: 20px 0;"><h2 style="color: white; margin: 0; font-size: 28px;">DOWNLOADING 2 FILES...</h2><p style="font-size: 18px; margin: 15px 0;">1. Cryptographic proof (.epi)   2. Browser viewer (.html)</p></div>'))\n""",
    "    \n",
    "    try:\n",
    "        from google.colab import files\n",
    "        files.download(str(epi_file))\n",
    "        if viewer_html_file.exists():\n",
    "            files.download(str(viewer_html_file))\n",
    """        display(HTML('<div style="background: #f0fdf4; border: 2px solid #10b981; padding: 20px; border-radius: 12px; margin: 15px 0;"><p style="color: #166534; font-weight: bold; font-size: 18px; margin: 0 0 10px 0;">Check your Downloads folder!</p><p style="color: #15803d; margin: 0; font-size: 14px;"><b>Double-click SEC_Evidence_Viewer.html</b> to view evidence in your browser - no installation needed!</p></div>'))\n""",
    "    except:\n",
    '        print("(Use file panel to download both files)")\n',
    "    \n",
    '    print("=" * 70)\n',
]

# Find the demo cell and update the download section
for cell in nb['cells']:
    if cell.get('metadata', {}).get('id') == 'demo':
        source_text = ''.join(cell['source'])
        
        # Find the download section markers
        start_marker = "    # DOWNLOAD\n"
        end_marker = '    print("=" * 70)\nelse:'
        
        start_idx = source_text.find(start_marker)
        end_idx = source_text.find(end_marker)
        
        if start_idx != -1 and end_idx != -1:
            # Replace the section
            new_source_text = (
                source_text[:start_idx] + 
                ''.join(NEW_DOWNLOAD_SECTION) +
                'else:'
            )
            
            # Split back into lines for notebook format
            cell['source'] = [line + '\n' if not line.endswith('\n') else line 
                            for line in new_source_text.split('\n')[:-1]]
            # Add the last line without extra newline
            if new_source_text.endswith('\n'):
                cell['source'][-1] = cell['source'][-1].rstrip('\n') + '\n'
            
            print("[OK] Updated demo cell with self-contained HTML download")
        else:
            print(f"[FAIL] Could not find download section markers")
            print(f"   start_marker found: {start_idx != -1}")
            print(f"   end_marker found: {end_idx != -1}")
        break

# Save the notebook
with open(NB_PATH, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=2, ensure_ascii=False)

print(f"\nNotebook updated: {NB_PATH}")
print("\nCHANGES MADE:")
print("  OLD: Downloads only .epi file (can't open without EPI installed)")
print("  NEW: Downloads BOTH .epi AND viewer.html (double-click to view!)")
print("\nThe investor can now:")
print("  1. Double-click SEC_Evidence_Viewer.html -> Opens in browser")
print("  2. Keep the .epi file for cryptographic verification")


