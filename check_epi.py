import zipfile
import json

# Quick check of the EPI file
epi_path = 'epi-recordings/simulate_agent_20260130_234211.epi'
z = zipfile.ZipFile(epi_path, 'r')

# Check manifest
m = json.loads(z.read('manifest.json'))
print('=== MANIFEST ===')
print('spec_version:', m.get('spec_version'))
print('signature present:', bool(m.get('signature')))
print('public_key present:', bool(m.get('public_key')))

# Check files
print('\n=== FILES ===')
for f in z.namelist():
    info = z.getinfo(f)
    print(f'  {f}: {info.file_size} bytes')

# Check viewer for steps
print('\n=== VIEWER CHECK ===')
html = z.read('viewer.html').decode('utf-8')
print('EPI v2.2.0 in footer:', 'EPI v2.2.0' in html)

# Find embedded data
import re
data_match = re.search(r'<script id="epi-data" type="application/json">(.*?)</script>', html, re.DOTALL)
if data_match:
    try:
        data = json.loads(data_match.group(1))
        print('Steps in viewer:', len(data.get('steps', [])))
        print('Manifest has signature:', bool(data.get('manifest', {}).get('signature')))
        print('Manifest spec_version:', data.get('manifest', {}).get('spec_version'))
        if data.get('steps'):
            print('First step kind:', data['steps'][0].get('kind'))
    except json.JSONDecodeError as e:
        print('JSON parse error:', e)
else:
    print('No epi-data found in viewer')

z.close()


