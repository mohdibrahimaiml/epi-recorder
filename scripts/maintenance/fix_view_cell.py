# -*- coding: utf-8 -*-
"""
Fix the VIEW cell to properly inject the signed manifest into the viewer.html
so it shows SIGNED status like the downloaded HTML file does.
"""

import json
import sys
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

NB_PATH = Path(__file__).parent / "epi_investor_demo.ipynb"

print(f"Loading: {NB_PATH}")
with open(NB_PATH, 'r', encoding='utf-8') as f:
    nb = json.load(f)

# New VIEW cell with proper signature injection - using single quotes to avoid escaping issues
NEW_VIEW_SOURCE = '''# @title View Timeline { display-mode: "form" }
import zipfile, json, html, os, re
from pathlib import Path
from IPython.display import display, HTML

epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))
epi_file = max(epi_files, key=os.path.getmtime) if epi_files else None

if epi_file:
    print("=" * 70)
    display(HTML('<h2 style="color: #3b82f6;">Loading viewer...</h2>'))
    print(f"Source: {epi_file.name}")
    
    viewer_html = None
    manifest = None
    steps = []
    signature = ""
    
    try:
        with zipfile.ZipFile(epi_file, 'r') as z:
            # Read the SIGNED manifest
            if 'manifest.json' in z.namelist():
                manifest = json.loads(z.read('manifest.json').decode('utf-8'))
                signature = manifest.get('signature', '')
                if signature:
                    print(f"Signature: {signature[:40]}...")
                else:
                    print("WARNING: File is UNSIGNED")
            
            # Read steps
            if 'steps.jsonl' in z.namelist():
                for line in z.read('steps.jsonl').decode('utf-8').strip().split('\\n'):
                    if line:
                        try:
                            steps.append(json.loads(line))
                        except:
                            pass
            
            # Read viewer.html template
            if 'viewer.html' in z.namelist():
                viewer_html = z.read('viewer.html').decode('utf-8')
                print("Found viewer.html")
        
        # INJECT SIGNED MANIFEST INTO VIEWER HTML
        if viewer_html and manifest:
            updated_data = {"manifest": manifest, "steps": steps}
            data_json = json.dumps(updated_data, indent=2)
            pattern = r'<script id="epi-data" type="application/json">.*?</script>'
            replacement = '<script id="epi-data" type="application/json">' + data_json + '</script>'
            viewer_html = re.sub(pattern, replacement, viewer_html, flags=re.DOTALL)
            print("Injected signed manifest into viewer")
        
    except Exception as e:
        print(f"Error: {e}")
    
    if viewer_html:
        sig_display = signature[:30] + "..." if signature else "UNSIGNED"
        sig_color = "#10b981" if signature else "#f59e0b"
        status = "SIGNED" if signature else "UNSIGNED"
        
        escaped = html.escape(viewer_html)
        
        iframe = '<div style="border: 4px solid ' + sig_color + '; border-radius: 16px; overflow: hidden; margin: 25px 0;">'
        iframe += '<div style="background: linear-gradient(135deg, ' + sig_color + ', #059669); color: white; padding: 18px 24px; display: flex; justify-content: space-between; align-items: center;">'
        iframe += '<span style="font-size: 22px; font-weight: bold;">EPI EVIDENCE VIEWER</span>'
        iframe += '<span style="font-family: Courier New, monospace; font-size: 14px; background: rgba(255,255,255,0.25); padding: 8px 14px; border-radius: 8px;">' + status + ': ' + sig_display + '</span>'
        iframe += '</div>'
        iframe += '<iframe srcdoc="' + escaped + '" width="100%" height="700" style="border: none;" sandbox="allow-scripts allow-same-origin"></iframe>'
        iframe += '</div>'
        
        print("=" * 70)
        display(HTML('<h1 style="color: ' + sig_color + '; font-size: 36px; margin: 20px 0;">VIEWER - ' + status + '</h1>'))
        print("=" * 70)
        display(HTML(iframe))
    else:
        display(HTML('<h2 style="color: #ef4444;">Failed to load viewer</h2>'))
else:
    print("Run demo cell first")
'''

# Find and replace the view cell
for cell in nb['cells']:
    if cell.get('metadata', {}).get('id') == 'view':
        lines = NEW_VIEW_SOURCE.split('\n')
        cell['source'] = [line + '\n' for line in lines[:-1]] + [lines[-1]]
        print("[OK] Replaced VIEW cell with signature injection fix")
        break

# Save the notebook
with open(NB_PATH, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=2, ensure_ascii=False)

print(f"\nNotebook updated: {NB_PATH}")
print("\nBOTH VIEWERS WILL NOW SHOW SIGNED:")
print("  1. In-Colab viewer (VIEW cell)")
print("  2. Downloaded SEC_Evidence_Viewer.html")


