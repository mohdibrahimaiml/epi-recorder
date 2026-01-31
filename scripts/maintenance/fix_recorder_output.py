
import json
import os

NB_PATH = "c:\\Users\\dell\\epi-recorder\\epi_investor_demo_ULTIMATE.ipynb"
with open(NB_PATH, 'r', encoding='utf-8') as f:
    nb = json.load(f)

# The Improved Recorder Code (No Silencing)
recorder_code = r"""# IMPROVED: Record & Deliver to Investor
import os
import glob
import time
from pathlib import Path
from google.colab import files
from IPython.display import display, HTML

display(HTML('<h1 style="color: #3b82f6;">🎬 LIGHTS, CAMERA, ACTION...</h1>'))
print("="*70)

record_start = time.time()
record_success = False
epi_file = None

try:
    # 1. Run EPI recorder (VERBOSE MODE - Show output!)
    print("📹 Recording AI execution...\n")
    
    # REMOVED: > /dev/null 2>&1
    # We WANT to see the output if it fails!
    !epi run trading_agent.py --no-open
    
    record_time = time.time() - record_start
    
    # 2. Find the file
    # Look in the standard recording folder
    epi_files = glob.glob('epi-recordings/*.epi')
    
    if epi_files:
        epi_file = Path(max(epi_files, key=os.path.getmtime))
        record_success = True
        
        print("\n" + "="*70)
        print(f"✅ RECORDING COMPLETE ({record_time:.1f}s)")
        print(f"📁 Evidence saved: {epi_file}")
        print("="*70)
        
        # 3. Trigger Download
        print("⬇️ Downloading cryptographic proof...")
        files.download(str(epi_file))
    else:
        print("\n❌ Recording finished but NO FILE FOUND.")
        print("   Checking current directory...")
        # Fallback check
        epi_files = glob.glob('*.epi')
        if epi_files:
             epi_file = Path(max(epi_files, key=os.path.getmtime))
             record_success = True
             print(f"✅ Found file in root: {epi_file}")
             files.download(str(epi_file))
        else: 
             print("   Please check the logs above for errors.")

except Exception as e:
    print(f"\n❌ RECORDING FAILED: {e}")

if not record_success:
    print("\n⚠️ Simulation Mode will be active in Step 4.")
"""

found_code = False
for cell in nb['cells']:
    if cell.get('metadata', {}).get('id') == 'record':
        # Split into lines
        lines = []
        for line in recorder_code.splitlines():
             lines.append(line + "\n")
        cell['source'] = lines
        found_code = True
        break

if not found_code:
    print("Warning: Could not find cell with id='record'")

# Save
with open(NB_PATH, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=2, ensure_ascii=False)

print(f"Successfully fixed Recorder Output in {NB_PATH}")


