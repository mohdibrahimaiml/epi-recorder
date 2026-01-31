import zipfile
import json
from pathlib import Path

print("="*70)
print("CHECKING IF FILE IS SIGNED")
print("="*70)

# Find the test file
epi_file = Path("test_signing.epi")

if not epi_file.exists():
    # Check in epi-recordings
    recordings = list(Path("epi-recordings").glob("*.epi"))
    if recordings:
        epi_file = max(recordings, key=lambda p: p.stat().st_mtime)

if epi_file.exists():
    print(f"\nFile: {epi_file.name}")
    print(f"Size: {epi_file.stat().st_size / 1024:.1f} KB\n")
    
    with zipfile.ZipFile(epi_file, 'r') as z:
        print("Contents of ZIP:")
        for f in sorted(z.namelist()):
            print(f"  {f}")
        
        print("\n" + "-"*70)
        
        if 'manifest.json' in z.namelist():
            manifest = json.loads(z.read('manifest.json').decode('utf-8'))
            
            print("MANIFEST.JSON:")
            print("-"*70)
            
            if 'signature' in manifest and manifest['signature']:
                sig = manifest['signature']
                print(f"Signature: {sig[:50]}..." if len(sig) > 50 else f"Signature: {sig}")
                print("\n" + "="*70)
                print("RESULT: FILE IS SIGNED ✓")
                print("="*70)
            else:
                print("Signature: NONE")
                print("\n" + "="*70)
                print("RESULT: FILE IS UNSIGNED ✗")
                print("="*70)
        else:
            print("ERROR: No manifest.json found")
else:
    print("ERROR: No .epi file found")


