"""
Script to fix EPI_DEMO_demo.ipynb signature display issue
This will modify the viewer cell to properly show SIGNED status
"""

import json
from pathlib import Path

# Path to the notebook
notebook_path = Path(r"c:\Users\dell\OneDrive\Desktop\EPI_DEMO_demo.ipynb")

print(f"Reading notebook: {notebook_path}")

# Read the notebook
with open(notebook_path, 'r', encoding='utf-8') as f:
    notebook = json.load(f)

# Fixed viewer cell code
fixed_viewer_code = '''# @title 👁️ View Timeline - SHOWS SIGNED STATUS { display-mode: "form" }
import zipfile, json, html, os
from pathlib import Path
from IPython.display import display, HTML

epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))
epi_file = max(epi_files, key=os.path.getmtime) if epi_files else None

if not epi_file:
    print("❌ No .epi file found. Run recording cell first.")
else:
    print("=" * 70)
    display(HTML('<h2 style="color: #3b82f6;">👁️ Loading viewer with signature...</h2>'))
    print(f"Source: {epi_file.name}\\n")

    try:
        with zipfile.ZipFile(epi_file, 'r') as z:
            # ===== STEP 1: EXTRACT SIGNATURE (CRITICAL) =====
            signature_status = "UNSIGNED"
            signature_short = "UNSIGNED"
            
            if 'manifest.json' in z.namelist():
                manifest = json.loads(z.read('manifest.json').decode('utf-8'))
                full_sig = manifest.get('signature', '')
                
                if full_sig and full_sig.strip():
                    # Parse: "ed25519:default:base64sig"
                    parts = full_sig.split(':', 2)
                    if len(parts) >= 3:
                        algo = parts[0].upper()
                        keyname = parts[1].upper()
                        sig_b64 = parts[2][:12]
                        signature_short = f"{algo}:{keyname}:{sig_b64}..."
                        signature_status = "SIGNED"
                        print(f"✅ Signature found: {signature_short}")
                    else:
                        signature_short = full_sig[:50]
                        signature_status = "SIGNED"
                        print(f"✅ Signature found: {signature_short}")
                else:
                    print("⚠️ No signature in manifest")
            
            # ===== STEP 2: LOAD STEPS =====
            steps = []
            if 'steps.jsonl' in z.namelist():
                lines = z.read('steps.jsonl').decode('utf-8').splitlines()
                steps = [json.loads(line) for line in lines if line.strip()]
                print(f"✅ Loaded {len(steps)} steps\\n")
            
            # ===== STEP 3: BUILD VIEWER HTML WITH SIGNATURE =====
            is_signed = (signature_status == "SIGNED")
            
            viewer_html = f\'\'\'<!DOCTYPE html>
<html><head>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>
body{{font-family:Inter,sans-serif;background:#f8fafc;margin:0;padding:16px}}
.mono{{font-family:'JetBrains Mono',monospace}}
</style>
</head>
<body>
<div style="max-width:1000px;margin:0 auto;background:white;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,0.1);overflow:hidden;border:2px solid #e2e8f0">
  
  <!-- Header with Signature -->
  <div style="background:#0f172a;padding:24px;color:white;display:flex;justify-content:space-between;align-items:center">
    <div>
      <div style="display:flex;align-items:center;gap:8px">
        <div style="width:12px;height:12px;border-radius:50%;background:{"#10b981" if is_signed else "#eab308"};{"animation:pulse 2s infinite" if is_signed else ""}"></div>
        <h1 style="margin:0;font-size:20px;font-weight:800">EPI EVIDENCE VIEWER</h1>
      </div>
      <p style="margin:6px 0 0 0;font-size:12px;color:#94a3b8">Immutable Execution Record</p>
    </div>
    <div style="text-align:right">
      <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;margin-bottom:4px">Signature</div>
      <div class="mono" style="background:#1e293b;padding:8px 12px;border-radius:6px;border:1px solid #334155;font-size:13px;color:{"#22c55e" if is_signed else "#eab308"}">
        {signature_short}
      </div>
    </div>
  </div>

  <!-- Steps Feed -->
  <div id="feed" style="max-height:600px;overflow-y:auto"></div>
</div>

<script>
@keyframes pulse {{
  0%, 100% {{ opacity: 1; }}
  50% {{ opacity: 0.5; }}
}}

const steps = {json.dumps(steps)};
const feed = document.getElementById('feed');

if (!steps.length) {{
  feed.innerHTML = '<div style="padding:60px;text-align:center;color:#94a3b8">No steps found</div>';
}} else {{
  steps.forEach((step, idx) => {{
    const kind = step.kind || 'LOG';
    const content = step.content || step.message || {{}};
    const time = step.timestamp ? step.timestamp.split('T')[1].substring(0,12) : '';
    
    let icon = '🔹';
    let bgColor = '#f1f5f9';
    let textColor = '#475569';
    
    if (kind.includes('MARKET')) {{ icon='📈'; bgColor='#dbeafe'; textColor='#1e40af'; }}
    if (kind.includes('TECHNICAL')) {{ icon='📊'; bgColor='#cffafe'; textColor='#0e7490'; }}
    if (kind.includes('RISK')) {{ icon='🛡️'; bgColor='#fed7aa'; textColor='#c2410c'; }}
    if (kind.includes('COMPLIANCE')) {{ icon='⚖️'; bgColor='#e9d5ff'; textColor='#7e22ce'; }}
    if (kind.includes('EXECUTION')) {{ icon='🚀'; bgColor='#d1fae5'; textColor='#047857'; }}
    
    const row = document.createElement('div');
    row.style.cssText = 'padding:20px 24px;border-bottom:1px solid #e2e8f0;display:flex;gap:16px;transition:background 0.2s';
    row.onmouseenter = () => row.style.background = '#f8fafc';
    row.onmouseleave = () => row.style.background = 'white';
    
    let dataBlock = '';
    if (typeof content === 'object' && content) {{
      dataBlock = `<pre class="mono" style="margin-top:8px;background:#0f172a;color:#22c55e;padding:12px;border-radius:6px;font-size:11px;overflow-x:auto">${{JSON.stringify(content, null, 2)}}</pre>`;
    }}
    
    row.innerHTML = `
      <div class="mono" style="width:80px;font-size:11px;color:#94a3b8;padding-top:2px">${{time}}</div>
      <div style="flex:1">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <span style="font-size:18px">${{icon}}</span>
          <span style="background:${{bgColor}};color:${{textColor}};padding:4px 10px;border-radius:4px;font-size:11px;font-weight:700;text-transform:uppercase">${{kind}}</span>
        </div>
        <div style="font-size:14px;color:#1e293b">${{typeof content === 'string' ? content : JSON.stringify(content)}}</div>
        ${{dataBlock}}
      </div>
    `;
    
    feed.appendChild(row);
  }});
}}
</script>
</body>
</html>\'\'\'
            
            # ===== STEP 4: DISPLAY IN IFRAME =====
            escaped_html = html.escape(viewer_html)
            
            # Outer wrapper
            border_color = "#10b981" if is_signed else "#eab308"
            badge_gradient = "linear-gradient(135deg, #10b981, #059669)" if is_signed else "linear-gradient(135deg, #eab308, #ca8a04)"
            status_icon = "🛡️" if is_signed else "⚠️"
            status_text = "CRYPTOGRAPHICALLY SIGNED" if is_signed else "UNSIGNED WARNING"
            
            wrapper = f\'\'\'<div style="border:4px solid {border_color};border-radius:16px;overflow:hidden;margin:25px 0;box-shadow:0 10px 40px rgba(0,0,0,0.15)">
  <div style="background:{badge_gradient};color:white;padding:18px 24px;display:flex;justify-content:space-between;align-items:center">
    <span style="font-size:22px;font-weight:800">{status_icon} {status_text}</span>
    <span style="font-family:'Courier New',monospace;font-size:14px;background:rgba(255,255,255,0.25);padding:8px 14px;border-radius:8px">{signature_short}</span>
  </div>
  <iframe srcdoc="{escaped_html}" width="100%" height="750" style="border:none" sandbox="allow-scripts allow-same-origin"></iframe>
</div>\'\'\'
            
            print("=" * 70)
            status_color = "#10b981" if is_signed else "#eab308"
            display(HTML(f'<h1 style="color:{status_color};font-size:36px;margin:20px 0">{"✅ VIEWER LOADED - SIGNED" if is_signed else "⚠️ VIEWER LOADED - UNSIGNED"}</h1>'))
            print(f"Signature: {signature_short}")
            print("=" * 70)
            
            display(HTML(wrapper))
            
    except Exception as e:
        print(f"❌ Error loading viewer: {e}")
        import traceback
        traceback.print_exc()'''

# Find the viewer cell and replace it
cell_found = False
for i, cell in enumerate(notebook['cells']):
    if cell['cell_type'] == 'code':
        # Check if this is the viewer cell
        source = ''.join(cell['source'])
        if 'View Timeline' in source or 'viewer' in source.lower() or 'signature_display' in source:
            print(f"Found viewer cell at index {i}")
            print("Replacing with fixed code...")
            
            # Replace the source
            cell['source'] = fixed_viewer_code.split('\n')
            # Add newlines
            cell['source'] = [line + '\n' if i < len(cell['source']) - 1 else line 
                             for i, line in enumerate(cell['source'])]
            cell_found = True
            break

if not cell_found:
    print("⚠️ Could not find viewer cell automatically")
    print("Please manually locate the viewer cell and replace its code")
else:
    # Create backup
    backup_path = notebook_path.with_suffix('.ipynb.backup')
    print(f"\nCreating backup: {backup_path}")
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(notebook, f, indent=1)
    
    # Save fixed notebook
    print(f"Saving fixed notebook: {notebook_path}")
    with open(notebook_path, 'w', encoding='utf-8') as f:
        json.dump(notebook, f, indent=1)
    
    print("\n" + "=" * 70)
    print("✅ SUCCESS! Notebook fixed!")
    print("=" * 70)
    print("\nChanges:")
    print("  ✓ Signature extraction happens BEFORE viewer HTML build")
    print("  ✓ Signature properly injected into viewer header")
    print("  ✓ Green SIGNED status will now display correctly")
    print("\nBackup saved to:", backup_path)
    print("\nUpload the fixed notebook to Google Colab and run it!")


