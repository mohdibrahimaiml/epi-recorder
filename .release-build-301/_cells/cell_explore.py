# @title Explore EPI Structure { display-mode: "form" }
import zipfile, json
from pathlib import Path
from IPython.display import display, HTML

epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))
epi_file = max(epi_files, key=lambda p: p.stat().st_mtime) if epi_files else None

if epi_file:
    print("=" * 70)
    display(HTML('<h2 style="color: #3b82f6;">Contents of {}</h2>'.format(epi_file.name)))
    print()

    with zipfile.ZipFile(epi_file, 'r') as z:
        file_list = z.namelist()
        manifest = json.loads(z.read('manifest.json').decode('utf-8'))
        for f in sorted(file_list):
            info = z.getinfo(f)
            print("  {:40} {:>8} bytes".format(f, info.file_size))

    print()
    print("-" * 70)
    display(HTML('<h3 style="color: #8b5cf6;">Manifest (Signed Metadata)</h3>'))
    print("  Workflow: {}".format(manifest.get('goal', 'N/A')))
    print("  Created:  {}".format(manifest.get('start_time', manifest.get('created_at', 'N/A'))))
    print("  Duration: {:.2f}s".format(manifest.get('duration_seconds', 0)))

    signing_key = manifest.get('signing_key_id') or manifest.get('signer_key_id') or manifest.get('key_id') or 'N/A'
    print("  Signer:   {}".format(signing_key))

    sig = manifest.get('signature', '')
    if sig:
        print("  Signature: {}...".format(sig[:40]))
    else:
        print("  Signature: UNSIGNED")
    print("=" * 70)
else:
    print("Run the recording cell first")
