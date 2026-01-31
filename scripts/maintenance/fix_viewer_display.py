"""
REAL FIX - This modifies the VIEWER HTML itself, not just the Python code
This will make the viewer DISPLAY show SIGNED
"""

import json
from pathlib import Path

notebook_path = Path(r"c:\Users\dell\OneDrive\Desktop\EPI_DEMO_demo.ipynb")
backup_path = Path(r"c:\Users\dell\OneDrive\Desktop\EPI_DEMO_demo.ipynb.backup3")

print("=" * 70)
print("FIXING VIEWER HTML TO SHOW SIGNED")
print("=" * 70)

# Read notebook
with open(notebook_path, 'r', encoding='utf-8') as f:
    notebook = json.load(f)

# Backup
print(f"\nCreating backup: {backup_path}")
with open(backup_path, 'w', encoding='utf-8') as f:
    json.dump(notebook, f, indent=1)

# Find viewer cell and completely replace the viewer HTML generation
viewer_cell_code = '''# @title 👁️ View Timeline - SHOWS SIGNED { display-mode: "form" }
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
        # EXTRACT SIGNATURE FIRST
        sig_text = "Unsigned"
        sig_color = "#eab308"
        if 'manifest.json' in z.namelist():
            m = json.loads(z.read('manifest.json').decode('utf-8'))
            sig = m.get('signature', '')
            if sig:
                parts = sig.split(':', 2)
                if len(parts) >= 3:
                    sig_text = f"{parts[0].upper()}:{parts[1].upper()}:{parts[2][:12]}..."
                    sig_color = "#22c55e"
                    print(f"Signed: {sig_text}")
        
        # Load steps
        steps = []
        if 'steps.jsonl' in z.namelist():
            for line in z.read('steps.jsonl').decode('utf-8').splitlines():
                if line.strip():
                    steps.append(json.loads(line))
        
        # BUILD VIEWER HTML WITH SIGNATURE INJECTED
        viewer_html = f"""<!DOCTYPE html>
<html><head>
<script src="https://cdn.tailwindcss.com"></script>
<style>body{{margin:0;font-family:system-ui}}</style>
</head><body style="background:#f8fafc;padding:20px">
<div style="max-width:900px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.1)">
  <div style="background:#1e293b;color:white;padding:20px;display:flex;justify-content:space-between;align-items:center">
    <div>
      <h1 style="margin:0;font-size:18px;font-weight:bold">EPI Viewer</h1>
      <p style="margin:4px 0 0;font-size:12px;opacity:0.7">Evidence Packaged Infrastructure for AI Workflows</p>
    </div>
    <div style="background:rgba(255,255,255,0.1);padding:8px 16px;border-radius:6px;font-size:13px;color:{sig_color};font-weight:600">
      ⚠ {sig_text}
    </div>
  </div>
  <div id="steps" style="max-height:500px;overflow-y:auto"></div>
</div>
<script>
const steps = {json.dumps(steps)};
const container = document.getElementById('steps');
if(!steps.length){{
  container.innerHTML='<div style="padding:40px;text-align:center;color:#94a3b8">No steps recorded</div>';
}}else{{
  steps.forEach(s=>{{
    const kind = s.kind||'LOG';
    const content = s.content||s.message||{{}};
    let icon='🔹',bg='#f1f5f9',color='#475569';
    if(kind.includes('MARKET')){{icon='📈';bg='#dbeafe';color='#1e40af'}};
    if(kind.includes('TECHNICAL')){{icon='📊';bg='#cffafe';color='#0e7490'}};
    if(kind.includes('RISK')){{icon='🛡️';bg='#fed7aa';color='#c2410c'}};
    if(kind.includes('COMPLIANCE')){{icon='⚖️';bg='#e9d5ff';color='#7e22ce'}};
    if(kind.includes('EXECUTION')){{icon='🚀';bg='#d1fae5';color='#047857'}};
    
    const div=document.createElement('div');
    div.style='padding:16px 20px;border-bottom:1px solid #e2e8f0';
    div.innerHTML=`
      <div style="display:flex;gap:12px;align-items:start">
        <span style="font-size:20px">${{icon}}</span>
        <div style="flex:1">
          <div style="background:${{bg}};color:${{color}};display:inline-block;padding:4px 10px;border-radius:4px;font-size:11px;font-weight:700;text-transform:uppercase;margin-bottom:6px">${{kind}}</div>
          <div style="font-size:14px;color:#1e293b">${{typeof content==='string'?content:JSON.stringify(content)}}</div>
          ${{typeof content==='object'&&content?'<pre style="margin-top:8px;background:#0f172a;color:#22c55e;padding:10px;border-radius:6px;font-size:11px;overflow-x:auto">'+JSON.stringify(content,null,2)+'</pre>':''}}
        </div>
      </div>
    `;
    container.appendChild(div);
  }});
}}
</script>
</body></html>"""
        
        # Display in iframe
        escaped = html.escape(viewer_html)
        wrapper = f'<iframe srcdoc="{escaped}" width="100%" height="700" style="border:2px solid {sig_color};border-radius:12px"></iframe>'
        display(HTML(wrapper))
'''

# Find and replace viewer cell
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
print("FIXED! The viewer HTML now includes the signature!")
print("=" * 70)
print("\nThe viewer will show:")
print("  - 'Unsigned' in yellow if no signature")
print("  - 'ED25519:DEFAULT:abc...' in GREEN if signed")
print("\nUpload to Colab and run!")
print("=" * 70)


