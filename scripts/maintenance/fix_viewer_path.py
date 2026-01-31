
import json
import os

NB_PATH = "c:\\Users\\dell\\epi-recorder\\epi_investor_demo_ULTIMATE.ipynb"
with open(NB_PATH, 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Improved Viewer Code with Recursive Search
viewer_code = r"""import zipfile
import json as json_lib
import glob
import html
from pathlib import Path
from IPython.display import display, HTML

# ---------------------------------------------------------
# 🛠️ THE ULTIMATE VIEWER (IFRAME ISOLATION + SIMULATION)
# ---------------------------------------------------------
# 1. Tries to load REAL recording.
# 2. If missing, loads SIMULATION data (Demo).
# 3. Renders inside an IFRAME to guarantee scripts run.
# ---------------------------------------------------------

# --- A. SAMPLE DATA (for Fallback) ---
SAMPLE_MANIFEST = {
    "workflow_id": "demo-simulation-1",
    "created_at": "2024-03-15T10:30:00Z",
    "cli_command": "epi run financial_analysis.py",
    "file_manifest": {"report.md": "sha256:...", "data.csv": "sha256:..."},
    "spec_version": "1.0"
}
SAMPLE_STEPS = [
    {"index": 1, "timestamp": "2024-03-15T10:30:01Z", "kind": "info", "content": {"message": "Starting Financial Analysis Workflow..."}},
    {"index": 2, "timestamp": "2024-03-15T10:30:05Z", "kind": "llm.request", "content": {"provider": "openai", "model": "gpt-4", "messages": [{"role": "user", "content": "Analyze these Q3 earnings..."}]}},
    {"index": 3, "timestamp": "2024-03-15T10:30:15Z", "kind": "llm.response", "content": {"provider": "openai", "model": "gpt-4", "choices": [{"message": {"content": "Based on the Q3 report, revenue is up 15%..."}}], "usage": {"total_tokens": 540, "latency_seconds": 9.2}}},
    {"index": 4, "timestamp": "2024-03-15T10:30:16Z", "kind": "security.redaction", "content": {"count": 2, "target_step": "Step 2"}},
    {"index": 5, "timestamp": "2024-03-15T10:30:18Z", "kind": "tool.output", "content": {"file": "report.md", "size": 1024}}
]

# --- B. FIND REAL FILE ---
found_file = False
target_file = None

if 'epi_file' in locals() and epi_file and epi_file.exists():
    target_file = epi_file
else:
    # Auto-detect in current AND epi-recordings folder
    search_patterns = ['*.epi', 'epi-recordings/*.epi']
    epi_files = []
    for pattern in search_patterns:
        epi_files.extend(list(Path('.').glob(pattern)))
    
    if epi_files:
        # Pick the most recent one
        target_file = max(epi_files, key=os.path.getmtime)
        print(f"🔄 Auto-detected recording: {target_file}")

# --- C. PREPARE DATA ---
template = None
final_data = None

if target_file and target_file.exists():
    print(f"🔓 Extracting Viewer from REAL RECORDING: {target_file.name}")
    try:
        with zipfile.ZipFile(target_file, 'r') as z:
            # Try to get data from file
            steps = []
            if 'steps.jsonl' in z.namelist():
                steps = [json_lib.loads(line) for line in z.read('steps.jsonl').decode('utf-8').splitlines() if line]
            
            manifest = {}
            if 'manifest.json' in z.namelist():
                    manifest = json_lib.loads(z.read('manifest.json').decode('utf-8'))
            
            final_data = { "manifest": manifest, "steps": steps }
            
            # Try to get template
            html_files = [f for f in z.namelist() if f.endswith('.html')]
            if html_files:
                 template = z.read(html_files[0]).decode('utf-8')
            found_file = True
    except Exception as e:
        print(f"⚠️ Error reading file: {e}. Switching to SIMULATION.")

if not found_file:
    print("🔵 No recording found/readable. Switching to SIMULATION MODE.")
    final_data = { "manifest": SAMPLE_MANIFEST, "steps": SAMPLE_STEPS }

# --- D. BUILD HTML ---
if not template:
    # Robust Minimal Template
    template = r'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>EPI Viewer</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { font-family: ui-sans-serif, system-ui, sans-serif; background: #f9fafb; margin: 0; padding: 20px; }
  .step-card { background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 12px; padding: 16px; transition: transform 0.2s; }
  .step-card:hover { transform: translateX(4px); }
  .badge { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
  .badge-info { background: #e0f2fe; color: #075985; }
  .badge-llm { background: #f3e8ff; color: #6b21a8; }
  .badge-sec { background: #fef3c7; color: #92400e; }
</style>
</head>
<body>
<div id="app" class="max-w-3xl mx-auto">
  <div class="mb-6 flex items-center justify-between">
    <h1 class="text-2xl font-bold text-gray-900">EPI Viewer <span class="text-xs text-gray-500 ml-2">(Embedded)</span></h1>
    <div id="status" class="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium">Ready</div>
  </div>
  <div id="timeline"></div>
</div>

<script id="epi-data" type="application/json">
  __DATA_PLACEHOLDER__
</script>

<script>
  try {
      const data = JSON.parse(document.getElementById('epi-data').textContent);
      const timeline = document.getElementById('timeline');
      
      data.steps.forEach(step => {
         let badgeClass = 'badge-info';
         if (step.kind && step.kind.includes('llm')) badgeClass = 'badge-llm';
         if (step.kind && step.kind.includes('security')) badgeClass = 'badge-sec';
         
         const div = document.createElement('div');
         div.className = 'step-card';
         div.innerHTML = `
           <div class="flex justify-between items-start mb-2">
             <div class="flex items-center gap-2">
               <span class="text-gray-400 font-mono text-xs">#${step.index}</span>
               <span class="badge ${badgeClass}">${step.kind || 'info'}</span>
             </div>
             <span class="text-xs text-gray-400 font-mono">${new Date(step.timestamp || Date.now()).toLocaleTimeString()}</span>
           </div>
           <pre class="text-xs text-gray-600 bg-gray-50 p-2 rounded overflow-x-auto">${JSON.stringify(step.content, null, 2)}</pre>
         `;
         timeline.appendChild(div);
      });
  } catch (e) {
      document.body.innerHTML = `<div class="text-red-600 p-4">Viewer Error: ${e.message}</div>`;
  }
</script>
</body>
</html>'''

# Inject Data
json_str = json_lib.dumps(final_data)

if '__DATA_PLACEHOLDER__' in template:
    final_html = template.replace('__DATA_PLACEHOLDER__', json_str)
else:
    # Surgical Replace
    script_start = '<script id="epi-data" type="application/json">'
    start_idx = template.find(script_start)
    if start_idx != -1:
         end_idx = template.find('</script>', start_idx)
         if end_idx != -1:
             final_html = template[:start_idx + len(script_start)] + json_str + template[end_idx:]
         else:
             final_html = template + f"{script_start}{json_str}</script>"
    else:
         final_html = template.replace('</body>', f"{script_start}{json_str}</script></body>")

# --- E. IFRAME ISOLATION RENDER ---
# We escape the entire HTML to put it inside srcdoc
escaped_html = html.escape(final_html)

iframe_code = f'''
<iframe 
    srcdoc="{escaped_html}" 
    width="100%" 
    height="600" 
    style="border: 1px solid #e5e7eb; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);\" 
    sandbox="allow-scripts allow-same-origin"
></iframe>
'''

print("✨ Rendering Interactive Viewer (IFrame Isolated)...")
display(HTML(iframe_code))
"""

found_code = False
for cell in nb['cells']:
    if cell.get('metadata', {}).get('id') == 'viewer':
        # Split into lines
        lines = []
        for line in viewer_code.splitlines():
             lines.append(line + "\n")
        cell['source'] = lines
        found_code = True
        break

if not found_code:
    print("Warning: Could not find cell with id='viewer'")

# Save
with open(NB_PATH, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=2, ensure_ascii=False)

print(f"Successfully applied Path Fix to {NB_PATH}")


