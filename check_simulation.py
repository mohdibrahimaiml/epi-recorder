import zipfile
import json
import re
from collections import Counter

epi_path = 'epi-recordings/simulate_agent_20260130_234646.epi'
print(f"Checking: {epi_path}")

try:
    with zipfile.ZipFile(epi_path, 'r') as z:
        # Check files
        print(f"Files: {z.namelist()}")
        if 'steps.jsonl' in z.namelist():
            print(f"steps.jsonl size: {z.getinfo('steps.jsonl').file_size} bytes")
        
        # Check viewer content
        if 'viewer.html' in z.namelist():
            html = z.read('viewer.html').decode('utf-8')
            match = re.search(r'<script id="epi-data" type="application/json">(.*?)</script>', html, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                steps = data.get('steps', [])
                print(f"Total steps in viewer: {len(steps)}")
                
                # Analyze step types
                counts = Counter(s['kind'] for s in steps)
                print("Step types breakdown:")
                for kind, count in counts.items():
                    print(f"  - {kind}: {count}")
                
                # Check for critical steps
                has_tool = any(s['kind'] == 'tool.execution' for s in steps)
                has_file = any(s['kind'] == 'file.write' for s in steps)
                print(f"Has tool execution: {has_tool}")
                print(f"Has file write: {has_file}")
            else:
                print("ERROR: No epi-data found in viewer!")
        else:
            print("ERROR: No viewer.html found!")
            
except Exception as e:
    print(f"ERROR: {e}")


