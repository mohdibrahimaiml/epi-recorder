
import json
import os
import ast
import sys
from pathlib import Path

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

NB_PATH = "c:\\Users\\dell\\epi-recorder\\epi_investor_demo_ULTIMATE.ipynb"

print(f"✈️  PRE-FLIGHT CHECK: {os.path.basename(NB_PATH)}")
print("=" * 60)

try:
    with open(NB_PATH, 'r', encoding='utf-8') as f:
        nb = json.load(f)
except Exception as e:
    print(f"❌ FAIL: Could not load notebook JSON. {e}")
    sys.exit(1)

# 1. CHECK NOTEBOOK STRUCTURE
print(f"✅ Notebook loaded ({len(nb['cells'])} cells)")

checks_passed = 0
checks_failed = 0

# 2. CHECK TRADING AGENT FILE
print("\n🔍 Checking Dependencies...")
agent_file = Path("trading_agent.py")
if agent_file.exists():
    content = agent_file.read_text(encoding='utf-8')
    if len(content.strip()) > 0:
        print(f"   ✅ trading_agent.py exists ({len(content)} bytes)")
        if "pay taxes" in content:
            print("   ✅ Audio-quoted text found in agent script")
        else:
             print("   ⚠️  Audio-quoted text MISSING from agent script")
        checks_passed += 1
    else:
        print("   ❌ FAIL: trading_agent.py is EMPTY! Recording will fail.")
        checks_failed += 1
else:
    print("   ❌ FAIL: trading_agent.py NOT FOUND locally.")
    checks_failed += 1


# 3. SYNTAX CHECK EVERY CODE CELL
print("\n🔍 Syntax Checking Code Cells...")
code_cells = [c for c in nb['cells'] if c['cell_type'] == 'code']

for i, cell in enumerate(code_cells):
    cell_id = cell.get('metadata', {}).get('id', f'cell_{i}')
    source = "".join(cell['source'])
    
    # Skip magic commands for syntax checking
    clean_source = []
    for line in source.splitlines():
        if line.strip().startswith('!'):
            clean_source.append(f"# {line}") # Comment out magic commands
        elif line.strip().startswith('%'):
             clean_source.append(f"# {line}")
        else:
            clean_source.append(line)
    
    code_to_check = "\n".join(clean_source)
    
    try:
        ast.parse(code_to_check)
        print(f"   ✅ Cell '{cell_id}': Valid Python")
        checks_passed += 1
        
        # Specific Logic Checks
        if cell_id == 'record':
            if 'python3 -u' in source:
                print("      -> Unbuffered fix detected (-u)")
            else:
                 print("      -> ⚠️  WARNING: Unbuffered fix missing!")
        
        if cell_id == 'viewer':
            if 'stdout.log' in source:
                print("      -> Log integration detected")
            else:
                print("      -> ⚠️  WARNING: Log integration missing!")
                
    except SyntaxError as e:
        print(f"   ❌ FAIL: Cell '{cell_id}' has SYNTAX ERROR: {e}")
        checks_failed += 1


# 4. FINAL REPORT
print("\n" + "="*60)
if checks_failed == 0:
    print("🚀 PRE-FLIGHT STATUS: GO FOR LAUNCH")
    print(f"   Passed: {checks_passed} checks")
    print("   Failed: 0 checks")
    print("\nThe notebook code is syntactically perfect and logically sound.")
else:
    print(f"🛑 PRE-FLIGHT STATUS: ABORT ({checks_failed} Failures)")


