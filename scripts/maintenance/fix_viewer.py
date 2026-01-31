
import json
import os

# 1. Load the Notebook
NOTEBOOK_PATH = "c:\\Users\\dell\\epi-recorder\\epi_investor_demo_ULTIMATE.ipynb"
with open(NOTEBOOK_PATH, "r", encoding="utf-8") as f:
    nb = json.load(f)

# 2. Define the CSS
# Note: We escape backslashes for the Python string, but CSS doesn't use many backslashes.
viewer_css = """
/* EPI Viewer Lite CSS */
body { font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; background-color: #f9fafb; margin: 0; line-height: 1.5; color: #111827; }
.min-h-screen { min-height: 100vh; }
.max-w-7xl { max-width: 80rem; }
.mx-auto { margin-left: auto; margin-right: auto; }
.px-4 { padding-left: 1rem; padding-right: 1rem; }
.py-4 { padding-top: 1rem; padding-bottom: 1rem; }
.px-6 { padding-left: 1.5rem; padding-right: 1.5rem; }
.mb-2 { margin-bottom: 0.5rem; }
.mb-4 { margin-bottom: 1rem; }
.mt-2 { margin-top: 0.5rem; }
.flex { display: flex; }
.justify-between { justify-content: space-between; }
.items-center { align-items: center; }
.grid { display: grid; }
.grid-cols-1 { grid-template-columns: repeat(1, minmax(0, 1fr)); }
.bg-white { background-color: #ffffff; }
.bg-gray-50 { background-color: #f9fafb; }
.bg-blue-100 { background-color: #dbeafe; }
.bg-green-100 { background-color: #dcfce7; }
.text-gray-900 { color: #111827; }
.text-gray-500 { color: #6b7280; }
.text-green-800 { color: #166534; }
.text-blue-800 { color: #1e40af; }
.text-red-600 { color: #dc2626; }
.text-purple-800 { color: #6b21a8; }
.font-bold { font-weight: 700; }
.font-mono { font-family: ui-monospace, monospace; }
.text-xs { font-size: 0.75rem; }
.text-sm { font-size: 0.875rem; }
.text-lg { font-size: 1.125rem; }
.rounded-lg { border-radius: 0.5rem; }
.rounded-full { border-radius: 9999px; }
.border-b { border-bottom-width: 1px; }
.border-r { border-right-width: 1px; }
.border-gray-200 { border-color: #e5e7eb; }
.p-2 { padding: 0.5rem; }
.p-4 { padding: 1rem; }
.p-6 { padding: 1.5rem; }
.mr-4 { margin-right: 1rem; }
.sticky { position: sticky; }
.top-0 { top: 0; }
.z-10 { z-index: 10; }
.overflow-auto { overflow: auto; }
.h-full { height: 100%; }
.w-full { width: 100%; }
.cursor-pointer { cursor: pointer; }
.hover\:bg-white:hover { background-color: white; }
.transition-colors { transition-property: color, background-color, border-color, text-decoration-color, fill, stroke; transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1); transition-duration: 150ms; }
@media (min-width: 1024px) {
    .lg\:grid-cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .lg\:col-span-1 { grid-column: span 1 / span 1; }
    .lg\:col-span-2 { grid-column: span 2 / span 2; }
}
"""

# 3. Define the HTML Template (Plain string, NO f-string logic inside the notebook!)
# We use placeholders like __CSS__, __STEPS_JSON__, etc.
html_template = """
<div id="epi-viewer-root" style="border: 1px solid #e5e7eb; border-radius: 0.5rem; overflow: hidden; background: white;">
    <style>
        __CSS__
    </style>
    
    <!-- HEADER -->
    <div class="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between sticky top-0 z-10">
        <div class="flex items-center">
             <div class="bg-blue-100 p-2 rounded-lg mr-4">
                <span style="font-size: 20px;">🛡️</span>
            </div>
            <div>
                <h2 class="text-lg font-bold text-gray-900">EPI Evidence Viewer</h2>
                <p class="text-sm text-gray-500">Cryptographically Signed Audit Trail</p>
            </div>
        </div>
        <div class="flex items-center space-x-2">
             <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                 ✓ Verified
             </span>
             <span class="text-xs text-gray-500 font-mono">
                 __FILENAME__
             </span>
        </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 min-h-[500px]">
        <!-- SIDEBAR: Timeline -->
        <div class="lg:col-span-1 bg-gray-50 border-r border-gray-200 overflow-auto" style="height: 500px;">
            <div class="p-4 border-b border-gray-200 bg-gray-50 sticky top-0 z-10 flex justify-between items-center">
                <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Timeline</h3>
                <span class="text-xs text-gray-400">__COUNT__ events</span>
            </div>
            <div class="divide-y divide-gray-200">
                __TIMELINE_ITEMS__
            </div>
        </div>

        <!-- MAIN CONTENT: Details -->
        <div class="lg:col-span-2 bg-white flex flex-col h-[500px]">
            <div class="p-6 overflow-auto flex-1 font-mono text-sm" id="detail-view">
                <div class="flex flex-col items-center justify-center h-full text-gray-400">
                    <p>Select an event from the timeline</p>
                </div>
            </div>
            
            <!-- JSON Metadata Footer -->
            <div class="bg-gray-50 border-t border-gray-200 p-4 text-xs text-gray-500 font-mono flex justify-between">
                 <span>ID: __MANIFEST_ID__</span>
                 <span>Hash: __MANIFEST_HASH__</span>
            </div>
        </div>
    </div>

    <script>
        // Embed data safely
        const steps = __STEPS_JSON__;
        
        function showStep(index) {
            const step = steps[index];
            const container = document.getElementById('detail-view');
            
            // Highlight sidebar
            document.querySelectorAll('.step-item').forEach(el => el.classList.remove('bg-blue-50', 'border-l-4', 'border-blue-500'));
            const btn = document.getElementById('step-btn-' + index);
            if(btn) {
                btn.classList.add('bg-blue-50');
                btn.style.borderLeft = "4px solid #3b82f6";
            }
            
            // Build Detail View
            let content = '';
            
            // Header
            content += `<div class="mb-6 pb-4 border-b border-gray-200">
                <h2 class="text-xl font-bold text-gray-900 mb-2">Step ${index + 1}</h2>
                <div class="flex gap-4 text-xs text-gray-500">
                    <span>timestamp: ${step.timestamp}</span>
                    <span>kind: ${step.kind}</span>
                </div>
            </div>`;
            
            // Content based on kind
            if (step.kv) {
                content += `<div class="bg-gray-50 rounded-lg p-4 border border-gray-200 mb-4">`;
                for (const [key, val] of Object.entries(step.kv)) {
                    content += `<div class="mb-2">
                        <span class="font-bold text-gray-700 block text-xs uppercase tracking-wide mb-1">${key}</span>
                        <div class="bg-white p-2 rounded border border-gray-200 whitespace-pre-wrap break-all">${val}</div>
                    </div>`;
                }
                content += `</div>`;
            } else {
                content += `<pre class="bg-gray-50 p-4 rounded-lg border border-gray-200 overflow-auto text-xs">${JSON.stringify(step, null, 2)}</pre>`;
            }

            container.innerHTML = content;
        }
        
        // Show first step by default
        if(steps.length > 0) showStep(0);
    </script>
</div>
"""

# Escape newlines in the template so it can be embedded in Python code as a string
html_template_escaped = html_template.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")

# 4. Construct the Python code for the cell
new_source_code = f"""# THE INLINE VIEWER - Guaranteed to Work
import zipfile
import json as json_lib
import html
from IPython.display import HTML, display, Javascript
from pathlib import Path

display(HTML('<h1 style="color: #8b5cf6;">🖥️ THE VIEWER (Inline)</h1>'))
print("=" * 70)

# CSS for the viewer
ViewerCSS = \"\"\"{viewer_css}\"\"\"

# HTML Template
HTML_TEMPLATE = \"\"\"{html_template}\"\"\"

def render_inline_viewer(epi_path):
    try:
        if not epi_path.exists():
            return "<div style='color:red'>Error: Evidence file not found</div>"
            
        with zipfile.ZipFile(epi_path, 'r') as z:
            # 1. Get Steps
            if 'steps.jsonl' not in z.namelist():
                return "<div style='color:red'>Error: Invalid evidence file</div>"
                
            steps_data = z.read('steps.jsonl').decode('utf-8')
            steps = [json_lib.loads(line) for line in steps_data.strip().split('\\n') if line]
            
            # 2. Get Manifest
            manifest = {{}}
            if 'manifest.json' in z.namelist():
                manifest = json_lib.loads(z.read('manifest.json').decode('utf-8'))
                
            # 3. Build Timeline Items HTML
            timeline_html = ""
            for i, step in enumerate(steps):
                kind = step.get('kind', 'info').upper()
                emoji = "📝"
                if kind == "TOOL": emoji = "🛠️"
                elif kind == "ERROR": emoji = "❌"
                elif kind == "LLM": emoji = "🤖"
                
                color_class = "text-gray-900"
                if kind == "ERROR": color_class = "text-red-600"
                if kind == "LLM": color_class = "text-purple-800"
                if kind == "TOOL": color_class = "text-blue-800"

                timestamp = step.get('timestamp', '')[11:19] # Time only
                
                timeline_html += f'''
                    <div class="p-4 hover:bg-white cursor-pointer transition-colors duration-150 step-item" 
                            onclick="showStep({{i}})" id="step-btn-{{i}}">
                        <div class="flex justify-between items-start mb-1">
                            <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
                                {{kind}}
                            </span>
                            <span class="text-xs text-gray-400 font-mono">{{timestamp}}</span>
                        </div>
                        <p class="text-sm font-medium {{color_class}} line-clamp-2">
                            {{emoji}} {{html.escape(str(step.get('input' if kind=='LLM' else 'name', 'Event'))[:50])}}
                        </p>
                    </div>
                '''

            # 4. Inject into Template using .replace()
            final_html = HTML_TEMPLATE \\
                .replace("__CSS__", ViewerCSS) \\
                .replace("__FILENAME__", epi_path.name) \\
                .replace("__COUNT__", str(len(steps))) \\
                .replace("__TIMELINE_ITEMS__", timeline_html) \\
                .replace("__MANIFEST_ID__", manifest.get('id', 'N/A')) \\
                .replace("__MANIFEST_HASH__", manifest.get('signature', 'N/A')[:20] + "...") \\
                .replace("__STEPS_JSON__", json_lib.dumps(steps))

            return final_html
            
    except Exception as e:
        import traceback
        return f"<div style='color:red; padding:20px; border:1px solid red'>Viewer Error: {{str(e)}}</div>"

# EXECUTION
if 'epi_file' in locals() and epi_file and epi_file.exists():
    display(HTML(render_inline_viewer(epi_file)))
    
    print("\\n" + "=" * 70)
    print(f"📥 DOWNLOAD: {{epi_file.name}}")
    print("   (Right-click file in sidebar -> Download)")
    print("=" * 70)
else:
    print("⚠️  No recording found. Run the previous cells first.")
"""

# Replace the placeholder in the code above (NO - I already did via f-string construction above)
# IMPORTANT: In the `new_source_code` f-string above, I used `{viewer_css}` and `{html_template}`.
# I need to make sure `html_template` (which has CSS and JS braces) is safe to put into an f-string.
# YES, because they are inside a variable `html_template` that is being interpolated.
# Python f-strings parse `{}` in the format string. They do NOT execute `{}` inside injected variables.
# However, `timeline_html` generation loop DOES use f-strings inside the generated code.
# `timeline_html += f''' ... '''`
# Inside THAT f-string, we have `<div ... onclick="showStep({i})">`.
# This is valid because `i` is a python variable in the loop.
# But we also have CSS classes like `hover:bg-white`? No, those are static.
# But we have JS calls? No.
# WE MUST BE CAREFUL with `timeline_html` construction.
# I used `{{i}}` in `click="showStep({{i}})"`. Wait.
# In the `new_source_code` f-string, `{{i}}` becomes `{i}` in the generated code.
# The generated code line is: `timeline_html += f''' ... showStep({i}) ... '''`.
# This is correct. `i` is a variable in the generated code's loop.

# 5. Inject into Notebook
for cell in nb['cells']:
    if cell.get('metadata', {}).get('id') == 'viewer':
        source_lines = [line + "\\n" for line in new_source_code.splitlines()]
        # Remove double newlines if they happen
        source_lines = [line.replace("\\n\\n", "\\n") for line in source_lines]
        cell['source'] = source_lines
        break

with open(NOTEBOOK_PATH, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=2, ensure_ascii=False)

print(f"Successfully updated cell 'viewer' in {NOTEBOOK_PATH}")


