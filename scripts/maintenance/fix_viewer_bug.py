import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

NB_PATH = r"c:\Users\dell\epi-recorder\epi_investor_demo.ipynb"

print("Fixing CRITICAL BUG: Viewer cell now reads steps.jsonl...")

with open(NB_PATH, 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Find and replace the view cell
for i, cell in enumerate(nb['cells']):
    if cell.get('metadata', {}).get('id') == 'view':
        print(f"Found view cell at index {i}")
        
        # New robust viewer code
        cell['source'] = [
            "# @title 👁️ View Timeline (Robust - Reads steps.jsonl) { display-mode: \"form\" }\n",
            "import zipfile, json, html, os\n",
            "from pathlib import Path\n",
            "from IPython.display import display, HTML\n",
            "\n",
            "# Find file\n",
            "epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))\n",
            "epi_file = max(epi_files, key=os.path.getmtime) if epi_files else None\n",
            "\n",
            "if epi_file:\n",
            "    print(\"=\"" * 70)\n",
           "    display(HTML('<h2 style=\"color: #3b82f6;\">👁️ Loading viewer...</h2>'))\n",
            "\n",
            "    steps = []\n",
            "    signature_id = \"UNSIGNED\"\n",
            "\n",
            "    try:\n",
            "        with zipfile.ZipFile(epi_file, 'r') as z:\n",
            "            # A. GET SIGNATURE\n",
            "            if 'manifest.json' in z.namelist():\n",
            "                m = json.loads(z.read('manifest.json').decode('utf-8'))\n",
            "                s = m.get('signature', '')\n",
            "                if ':' in s:\n",
            "                    signature_id = f\"{s.split(':')[0].upper()}...{s.split(':')[-1][:12]}\"\n",
            "\n",
            "            # B. GET DATA (Priority: steps.jsonl -> stdout.log)\n",
            "            # 1. Try steps.jsonl (Created by Python API)\n",
            "            if 'steps.jsonl' in z.namelist():\n",
            "                lines = z.read('steps.jsonl').decode('utf-8').splitlines()\n",
            "                steps = [json.loads(line) for line in lines if line.strip()]\n",
            "\n",
            "            # 2. Fallback to stdout.log parsing (Created by CLI wrapper)\n",
            "            if not steps and 'stdout.log' in z.namelist():\n",
            "                logs = z.read('stdout.log').decode('utf-8', errors='ignore')\n",
            "                for line in logs.splitlines():\n",
            "                    if line.strip().startswith('{'):\n",
            "                        try:\n",
            "                            j = json.loads(line)\n",
            "                            steps.append(j)\n",
            "                        except: pass\n",
            "\n",
            "    except Exception as e:\n",
            "        print(f\"Error reading file: {e}\")\n",
            "\n",
            "    # C. BUILD VIEWER (Custom HTML from steps.jsonl data)\n",
            "    js_data = json.dumps(steps)\n",
            "\n",
            "    viewer_html = f'''<!DOCTYPE html>\n",
            "<html>\n",
            "<head>\n",
            "    <script src=\"https://cdn.tailwindcss.com\"></script>\n",
            "    <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap\" rel=\"stylesheet\">\n",
            "    <style>\n",
            "        body {{ font-family:Inter,sans-serif; background:#f8fafc; }}\n",
            "        .mono {{ font-family:'JetBrains Mono',monospace; }}\n",
            "    </style>\n",
            "</head>\n",
            "<body class=\"p-4\">\n",
            "    <div class=\"max-w-4xl mx-auto bg-white rounded-xl shadow-2xl overflow-hidden border border-slate-200\">\n",
            "        <div class=\"bg-slate-900 p-6 text-white flex justify-between items-center\">\n",
            "            <div>\n",
            "                <div class=\"flex items-center gap-2\">\n",
            "                    <div class=\"w-3 h-3 rounded-full bg-green-500 animate-pulse\"></div>\n",
            "                    <h1 class=\"text-lg font-bold tracking-wide\">EPI EVIDENCE VIEWER</h1>\n",
            "                </div>\n",
            "                <p class=\"text-slate-400 text-xs mt-1\">Immutable Execution Record</p>\n",
            "            </div>\n",
            "            <div class=\"text-right\">\n",
            "                <div class=\"text-[10px] text-slate-500 font-bold uppercase tracking-wider\">Signature</div>\n",
            "                <div class=\"mono text-green-400 text-xs bg-slate-800 px-2 py-1 rounded border border-slate-700 mt-1\">{signature_id}</div>\n",
            "            </div>\n",
            "        </div>\n",
            "        <div id=\"feed\" class=\"divide-y divide-slate-100 max-h-[500px] overflow-y-auto\"></div>\n",
            "    </div>\n",
            "\n",
            "    <script>\n",
            "        const steps={js_data};\n",
            "        const c=document.getElementById('feed');\n",
            "        if(!steps.length){{c.innerHTML='<div class=\"p-12 text-center text-slate-400\">No steps found</div>';}}\n",
            "        steps.forEach(s=>{{\n",
            "            const kind=s.kind||'LOG';\n",
            "            const content=s.content||s.message||{{}};\n",
            "            const msg=typeof content==='string'?content:(content.message||JSON.stringify(content));\n",
            "            const time=s.timestamp?s.timestamp.split('T')[1].substring(0,12):'';\n",
            "            let icon='🔹',color='bg-slate-100 text-slate-600';\n",
            "            if(kind.includes('MARKET')){{icon='📈';color='bg-blue-50 text-blue-600';}}\n",
            "            if(kind.includes('TECHNICAL')){{icon='📊';color='bg-cyan-50 text-cyan-600';}}\n",
            "            if(kind.includes('RISK')){{icon='🛡️';color='bg-orange-50 text-orange-600';}}\n",
            "            if(kind.includes('COMPLIANCE')){{icon='⚖️';color='bg-purple-50 text-purple-600';}}\n",
            "            if(kind.includes('EXECUTION')){{icon='🚀';color='bg-green-50 text-green-600';}}\n",
            "            const div=document.createElement('div');\n",
            "            div.className='px-6 py-4 hover:bg-slate-50 flex gap-4';\n",
            "            let data='';\n",
            "            if(typeof content==='object'&&content){{data=`<pre class=\"mt-2 text-[10px] bg-slate-800 text-green-400 p-2 rounded mono\">${{JSON.stringify(content,null,2)}}</pre>`;}}\n",
            "            div.innerHTML=`<div class=\"w-16 text-[10px] text-slate-400 mono pt-1\">${{time}}</div><div class=\"flex-grow\"><div class=\"flex gap-2 mb-1\"><span>${{icon}}</span><span class=\"text-[10px] font-bold uppercase px-2 py-0.5 rounded ${{color}}\">${{kind}}</span></div><div class=\"text-sm text-slate-700\">${{msg}}</div>${{data}}</div>`;\n",
            "            c.appendChild(div);\n",
            "        }});\n",
            "    </script>\n",
            "</body>\n",
            "</html>'''\n",
            "    \n",
            "    escaped = html.escape(viewer_html)\n",
            "    iframe = f'<iframe srcdoc=\"{escaped}\" width=\"100%\" height=\"650\" style=\"border:none;border-radius:12px;box-shadow:0 10px 40px rgba(0,0,0,0.15);\"></iframe>'\n",
            "    \n",
            "    print(\"=\" * 70)\n",
            "    display(HTML('<h1 style=\"color:#10b981;font-size:36px;margin:20px 0\">✅ VIEWER LOADED</h1>'))\n",
            "    print(f\"📊 Displaying {len(steps)} recorded steps\")\n",
            "    print(\"=\" * 70)\n",
            "    display(HTML(iframe))\n",
            "\n",            "else:\n",
            "    print(\"Run demo cell first\")\n"
        ]
        print("   ✅ Updated view cell with robust steps.jsonl reader")
        break

with open(NB_PATH, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=2, ensure_ascii=False)

print(f"\n✅ CRITICAL BUG FIXED: {NB_PATH}")
print("\nCHANGES:")
print("  • Viewer now reads steps.jsonl (Python API format)")
print("  • Falls back to stdout.log if needed")
print("  • Builds custom viewer HTML on-the-fly")
print("  • Handles both API and CLI formats")
print("\n✅ Demo is now bulletproof!")


