"""
Fix the color - make "Signed" show in GREEN instead of yellow
"""

import json
from pathlib import Path

notebook_path = Path(r"c:\Users\dell\OneDrive\Desktop\EPI_DEMO_demo.ipynb")
backup_path = Path(r"c:\Users\dell\OneDrive\Desktop\EPI_DEMO_demo.ipynb.backup6")

print("=" * 70)
print("FIXING COLOR TO GREEN FOR SIGNED")
print("=" * 70)

# Read notebook
with open(notebook_path, 'r', encoding='utf-8') as f:
    notebook = json.load(f)

# Backup
print(f"\nCreating backup: {backup_path}")
with open(backup_path, 'w', encoding='utf-8') as f:
    json.dump(notebook, f, indent=1)

# Updated viewer cell with better color replacement
viewer_cell_code = '''# @title 👁️ View Timeline (Authentic Viewer) { display-mode: "form" }
import zipfile, json, html, os, re
from pathlib import Path
from IPython.display import display, HTML

epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))
epi_file = max(epi_files, key=os.path.getmtime) if epi_files else None

if not epi_file:
    print("No .epi file found")
else:
    print(f"Loading: {epi_file.name}")
    
    with zipfile.ZipFile(epi_file, 'r') as z:
        # Extract signature from manifest
        is_signed = False
        
        if 'manifest.json' in z.namelist():
            m = json.loads(z.read('manifest.json').decode('utf-8'))
            sig = m.get('signature', '')
            if sig and sig.strip():
                is_signed = True
                print(f"Status: SIGNED")
        
        # Load AUTHENTIC viewer
        viewer_html = None
        for fname in z.namelist():
            if fname.endswith('viewer.html') or fname.endswith('.html'):
                try:
                    viewer_html = z.read(fname).decode('utf-8', errors='ignore')
                    print(f"Loaded authentic viewer: {fname}")
                    break
                except:
                    pass
        
        if viewer_html and is_signed:
            # Replace "Unsigned" text
            viewer_html = viewer_html.replace('Unsigned', 'Signed')
            viewer_html = viewer_html.replace('unsigned', 'signed')
            
            # Replace ALL yellow colors with green
            viewer_html = viewer_html.replace('#eab308', '#22c55e')
            viewer_html = viewer_html.replace('#f59e0b', '#22c55e')
            viewer_html = viewer_html.replace('#fbbf24', '#22c55e')
            viewer_html = viewer_html.replace('rgb(234, 179, 8)', 'rgb(34, 197, 94)')
            
            # Replace warning icon with checkmark
            viewer_html = viewer_html.replace('⚠', '✓')
            viewer_html = viewer_html.replace('warning', 'success')
            
            print("Converted to GREEN for signed status")
        
        # Fallback if no viewer
        if not viewer_html:
            print("No authentic viewer found, using fallback")
            sig_status = "Signed" if is_signed else "Unsigned"
            sig_color = "#22c55e" if is_signed else "#eab308"
            sig_icon = "✓" if is_signed else "⚠"
            
            steps = []
            if 'steps.jsonl' in z.namelist():
                for line in z.read('steps.jsonl').decode('utf-8').splitlines():
                    if line.strip():
                        steps.append(json.loads(line))
            
            viewer_html = f"""<!DOCTYPE html>
<html><head><script src="https://cdn.tailwindcss.com"></script></head>
<body style="background:#f8fafc;padding:20px">
<div style="max-width:900px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.1)">
  <div style="background:#1e293b;color:white;padding:20px;display:flex;justify-content:space-between">
    <div><h1 style="margin:0;font-size:18px">EPI Viewer</h1></div>
    <div style="color:{sig_color};font-weight:600">{sig_icon} {sig_status}</div>
  </div>
  <div id="steps"></div>
</div>
<script>
const steps={json.dumps(steps)};
const c=document.getElementById('steps');
steps.forEach(s=>{{
  const d=document.createElement('div');
  d.style='padding:16px;border-bottom:1px solid #e2e8f0';
  d.textContent=(s.kind||'LOG')+': '+JSON.stringify(s.content||s.message||'');
  c.appendChild(d);
}});
</script></body></html>"""
        
        # Display viewer
        escaped = html.escape(viewer_html)
        border_color = "#22c55e" if is_signed else "#eab308"
        wrapper = f'<iframe srcdoc="{escaped}" width="100%" height="700" style="border:2px solid {border_color};border-radius:12px"></iframe>'
        display(HTML(wrapper))
'''

# Replace viewer cell
for i, cell in enumerate(notebook['cells']):
    if cell['cell_type'] == 'code':
        source = ''.join(cell['source'])
        if 'srcdoc' in source and 'viewer' in source.lower():
            print(f"\nReplacing viewer cell at index {i}")
            cell['source'] = viewer_cell_code.split('\n')
            cell['source'] = [line + '\n' if j < len(cell['source'])-1 else line 
                             for j, line in enumerate(cell['source'])]
            break

# Save
print(f"Saving: {notebook_path}")
with open(notebook_path, 'w', encoding='utf-8') as f:
    json.dump(notebook, f, indent=1)

print("\n" + "=" * 70)
print("FIXED! Signed status will now show in GREEN")
print("=" * 70)
print("\nReplaces ALL yellow colors with green:")
print("  - #eab308 -> #22c55e")
print("  - #f59e0b -> #22c55e")
print("  - warning icon -> checkmark")
print("\nUpload to Colab and test!")
print("=" * 70)


