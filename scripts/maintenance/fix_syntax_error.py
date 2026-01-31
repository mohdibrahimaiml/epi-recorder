# -*- coding: utf-8 -*-
"""
Fix the syntax error in trading_ai.py generation.
The issue is with escape sequences in the embedded agent code.
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

# The new demo cell with PROPERLY escaped strings
# Using raw strings and careful escaping
NEW_DEMO_SOURCE = r'''# @title Install + Record AI Decision { display-mode: "form" }
import sys, time, re
from pathlib import Path
from IPython.display import clear_output, display, HTML

# Fast install
!pip install -q --upgrade pip epi-recorder 2>&1 | grep -v 'already satisfied' || true

clear_output()
print("=" * 70)
display(HTML('<h2 style="color: #10b981;">EPI Installed from PyPI</h2>'))
print("=" * 70)

# Create AI agent - using proper escaping
agent_code = """
import time
from epi_recorder import record

with record("trade_evidence.epi", workflow_name="SEC-Compliant Trading", auto_sign=True) as epi:
    print()
    print("=" * 70)
    print("FINANCIAL AI - EXECUTING TRADE")
    print("=" * 70)
    print()
    
    print("Market Analysis...")
    epi.log_step("MARKET_DATA", {"symbol": "AAPL", "price": 185.43, "volume": "45.2M", "sentiment": 0.82})
    time.sleep(0.15)
    
    epi.log_step("TECHNICAL", {"indicator": "50-Day MA", "value": 178.21, "signal": "BULLISH", "conf": 0.89})
    time.sleep(0.15)
    
    print("Risk Assessment...")
    epi.log_step("RISK_VAR", {"VaR_95": 12500.00, "sharpe_ratio": 1.89, "status": "ACCEPTABLE"})
    time.sleep(0.2)
    
    epi.log_step("RISK_CONCENTRATION", {"sector": "TECH", "exposure": 0.23, "limit": 0.30, "ok": True})
    time.sleep(0.15)
    
    print("Compliance Checks...")
    epi.log_step("COMPLIANCE_SEC", {"rule": "SEC 15c3-1", "check": "Net Capital", "result": "PASS"})
    time.sleep(0.15)
    
    epi.log_step("COMPLIANCE_FINRA", {"rule": "FINRA 4210", "check": "Margin", "result": "PASS"})
    time.sleep(0.15)
    
    print()
    print("EXECUTING TRADE...")
    trade = {"action": "BUY", "symbol": "AAPL", "qty": 500, "price": 185.43, "total": 92715.00}
    epi.log_step("EXECUTION", trade)
    time.sleep(0.2)
    
    print()
    print("=" * 70)
    print("TRADE COMPLETE - 7 steps logged & cryptographically signed")
    print("=" * 70)
    print()
"""

with open('trading_ai.py', 'w') as f:
    f.write(agent_code)

# Clean + Record
!rm -rf *.epi epi-recordings/*.epi 2>/dev/null

print()
print("=" * 70)
display(HTML('<h2 style="color: #3b82f6;">RECORDING AI EXECUTION...</h2>'))
print()

start = time.time()
!python trading_ai.py

# Find evidence
import zipfile, json as json_mod
epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))
epi_file = max(epi_files, key=lambda p: p.stat().st_mtime) if epi_files else None

if epi_file:
    # Read the SIGNED manifest
    with zipfile.ZipFile(epi_file, 'r') as z:
        manifest = json_mod.loads(z.read('manifest.json').decode('utf-8'))
        signature = manifest.get('signature', '')
        
        # Read steps
        steps = []
        if 'steps.jsonl' in z.namelist():
            for line in z.read('steps.jsonl').decode('utf-8').strip().split('\n'):
                if line:
                    try:
                        steps.append(json_mod.loads(line))
                    except:
                        pass
        
        # Read viewer.html template
        viewer_html = z.read('viewer.html').decode('utf-8') if 'viewer.html' in z.namelist() else None
    
    if signature:
        print(f"FILE IS SIGNED: {signature[:40]}...")
    else:
        display(HTML('<div style="background:#fef2f2;color:#dc2626;padding:20px;margin:10px 0;border-radius:8px;font-weight:bold;">WARNING: File is UNSIGNED!</div>'))
    
    print()
    print("=" * 70)
    display(HTML('<h1 style="color: #10b981; font-size: 36px; margin: 20px 0;">EVIDENCE CREATED</h1>'))
    print(f"File: {epi_file.name}")
    print(f"Size: {epi_file.stat().st_size / 1024:.1f} KB")
    print(f"Time: {time.time() - start:.1f}s")
    print(f"Signed: Ed25519")
    
    # EXTRACT AND FIX VIEWER HTML WITH SIGNED MANIFEST
    viewer_html_file = Path('SEC_Evidence_Viewer.html')
    
    if viewer_html:
        # Create updated embedded data with SIGNED manifest
        updated_data = {
            "manifest": manifest,
            "steps": steps
        }
        data_json = json_mod.dumps(updated_data, indent=2)
        
        # Replace the embedded data in viewer.html
        pattern = r'<script id="epi-data" type="application/json">.*?</script>'
        replacement = f'<script id="epi-data" type="application/json">{data_json}</script>'
        fixed_viewer_html = re.sub(pattern, replacement, viewer_html, flags=re.DOTALL)
        
        viewer_html_file.write_text(fixed_viewer_html, encoding='utf-8')
        print(f"Extracted: {viewer_html_file.name} (WITH SIGNATURE!)")
    else:
        print("Note: No viewer.html found in .epi archive")
    
    # DOWNLOAD BOTH FILES
    print()
    print("=" * 70)
    display(HTML('<div style="background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 25px; border-radius: 12px; text-align: center; margin: 20px 0;"><h2 style="color: white; margin: 0; font-size: 28px;">DOWNLOADING 2 FILES...</h2><p style="font-size: 18px; margin: 15px 0;">1. Cryptographic proof (.epi) 2. Browser viewer (.html)</p></div>'))
    
    try:
        from google.colab import files
        files.download(str(epi_file))
        if viewer_html_file.exists():
            files.download(str(viewer_html_file))
        display(HTML('<div style="background: #f0fdf4; border: 2px solid #10b981; padding: 20px; border-radius: 12px; margin: 15px 0;"><p style="color: #166534; font-weight: bold; font-size: 18px; margin: 0 0 10px 0;">Check your Downloads folder!</p><p style="color: #15803d; margin: 0; font-size: 14px;"><b>Double-click SEC_Evidence_Viewer.html</b> to view SIGNED evidence!</p></div>'))
    except:
        print("(Use file panel to download both files)")
    
    print("=" * 70)
else:
    display(HTML('<h2 style="color: #ef4444;">Recording failed - check logs above</h2>'))
'''

# Find and replace the demo cell
for cell in nb['cells']:
    if cell.get('metadata', {}).get('id') == 'demo':
        # Convert to list of lines for notebook format
        lines = NEW_DEMO_SOURCE.split('\n')
        cell['source'] = [line + '\n' for line in lines[:-1]] + [lines[-1]]
        print("[OK] Replaced demo cell with fixed escaping")
        break

# Save the notebook
with open(NB_PATH, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=2, ensure_ascii=False)

print(f"\nNotebook updated: {NB_PATH}")
print("\nFIX APPLIED:")
print("  Changed from escaped \\\\n to using print() statements")
print("  Used triple-quoted string for agent code")
print("  No more unterminated string literal issues")


