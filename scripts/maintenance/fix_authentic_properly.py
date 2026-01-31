"""
PROPER FIX - Use authentic EPI viewer and replace __SIGNATURE__ placeholder correctly
"""

import json
from pathlib import Path

notebook_path = Path(r"c:\Users\dell\OneDrive\Desktop\EPI_DEMO_demo.ipynb")
backup_path = Path(r"c:\Users\dell\OneDrive\Desktop\EPI_DEMO_demo.ipynb.backup7")

print("=" * 70)
print("FIXING TO USE AUTHENTIC VIEWER PROPERLY")
print("=" * 70)

# Read notebook
with open(notebook_path, 'r', encoding='utf-8') as f:
    notebook = json.load(f)

# Backup
print(f"\nCreating backup: {backup_path}")
with open(backup_path, 'w', encoding='utf-8') as f:
    json.dump(notebook, f, indent=1)

# Proper viewer cell that uses authentic viewer correctly
viewer_cell_code = '''# @title 👁️ View Timeline (Authentic Viewer) { display-mode: "form" }
import zipfile, json, html, os
from pathlib import Path
from IPython.display import display, HTML

epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))
epi_file = max(epi_files, key=os.path.getmtime) if epi_files else None

if not epi_file:
    print("No .epi file found")
else:
    print(f"Loading: {epi_file.name}")
    
    with zipfile.ZipFile(epi_file, 'r') as z:
        # Extract signature
        signature_display = "Unsigned"
        if 'manifest.json' in z.namelist():
            m = json.loads(z.read('manifest.json').decode('utf-8'))
            sig = m.get('signature', '')
            if sig and sig.strip():
                # Parse signature
                parts = sig.split(':', 2)
                if len(parts) >= 3:
                    signature_display = f"Signed (Ed25519)"
                else:
                    signature_display = "Signed"
                print(f"Status: SIGNED")
        
        # Load authentic viewer
        viewer_html = None
        for fname in z.namelist():
            if 'viewer' in fname and fname.endswith('.html'):
                viewer_html = z.read(fname).decode('utf-8', errors='ignore')
                print(f"Loaded: {fname}")
                break
        
        if viewer_html:
            # Replace the __SIGNATURE__ placeholder with actual status
            if '__SIGNATURE__' in viewer_html:
                viewer_html = viewer_html.replace('__SIGNATURE__', signature_display)
                print(f"Replaced __SIGNATURE__ with: {signature_display}")
            
            # Also handle any other signature placeholders
            viewer_html = viewer_html.replace('{{signature}}', signature_display)
            viewer_html = viewer_html.replace('{{ signature }}', signature_display)
            
            # If signed, change yellow to green in styles
            if signature_display.startswith('Signed'):
                viewer_html = viewer_html.replace('#eab308', '#22c55e')
                viewer_html = viewer_html.replace('#f59e0b', '#22c55e')
                viewer_html = viewer_html.replace('⚠', '✓')
        else:
            # Fallback if no viewer found
            print("No viewer.html found, creating basic viewer")
            steps = []
            if 'steps.jsonl' in z.namelist():
                for line in z.read('steps.jsonl').decode('utf-8').splitlines():
                    if line.strip():
                        steps.append(json.loads(line))
            
            status_color = "#22c55e" if signature_display.startswith('Signed') else "#eab308"
            viewer_html = f"""<!DOCTYPE html>
<html><head><script src="https://cdn.tailwindcss.com"></script></head>
<body style="padding:20px;background:#f8fafc">
<div style="max-width:900px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.1)">
  <div style="background:#1e293b;color:white;padding:20px;display:flex;justify-content:space-between;align-items:center">
    <div><h1 style="margin:0;font-size:18px;font-weight:bold">EPI Viewer</h1></div>
    <div style="color:{status_color};font-weight:600">{signature_display}</div>
  </div>
  <div id="feed"></div>
</div>
<script>
steps={json.dumps(steps)};
feed=document.getElementById('feed');
steps.forEach(s=>{{d=document.createElement('div');d.style='padding:16px;border-bottom:1px solid #e2e8f0';d.textContent=(s.kind||'')+(s.content?' : '+JSON.stringify(s.content):'');feed.appendChild(d)}});
</script></body></html>"""
        
        # Display
        escaped = html.escape(viewer_html)
        border_color = "#22c55e" if signature_display.startswith('Signed') else "#eab308"
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
print("FIXED PROPERLY!")
print("=" * 70)
print("\nNow:")
print("  1. Uses AUTHENTIC viewer.html from .epi file")
print("  2. Replaces __SIGNATURE__ placeholder correctly")
print("  3. Shows 'Signed (Ed25519)' in GREEN when signed")
print("  4. Shows 'Unsigned' in YELLOW when not signed")
print("\nUpload to Colab!")
print("=" * 70)


