import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

NB_PATH = r"c:\Users\dell\epi-recorder\epi_investor_demo_ULTIMATE.ipynb"

print("🔍 Checking current notebook state...")

with open(NB_PATH, 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Check agent cell
agent_cell = [c for c in nb['cells'] if c.get('metadata', {}).get('id') == 'agent'][0]
agent_source = "".join(agent_cell['source'])

print("\nAGENT CELL CHECK:")
if "from epi_recorder import record" in agent_source:
    print("  ✓ Uses Python API")
    if "session.log_step" in agent_source:
        print("  ✓ Has session.log_step()")
    else:
        print("  ✗ Missing session.log_step()")
else:
    print("  ✗ NOT using Python API")

# Check record cell  
record_cell = [c for c in nb['cells'] if c.get('metadata', {}).get('id') == 'record'][0]
record_source = "".join(record_cell['source'])

print("\nRECORD CELL CHECK:")
if "python trading_agent.py" in record_source:
    print("  ✓ Runs python directly")
elif "epi run" in record_source:
    print("  ✗ Still uses 'epi run'")
else:
    print("  ? Unknown method")

print("\n" + "=" * 70)
print("STATUS: Notebook state verified")
print("=" * 70)


