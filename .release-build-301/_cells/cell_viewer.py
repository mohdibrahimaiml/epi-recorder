# @title Launch Interactive Viewer { display-mode: "form" }
import zipfile, json, html, re
from pathlib import Path
from IPython.display import display, HTML

epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))
epi_file = max(epi_files, key=lambda p: p.stat().st_mtime) if epi_files else None

if epi_file:
    print("=" * 70)
    display(HTML('<h2 style="color: #3b82f6;">Loading Evidence Viewer...</h2>'))

    viewer_html = None
    manifest = None
    steps = []

    with zipfile.ZipFile(epi_file, 'r') as z:
        if 'manifest.json' in z.namelist():
            manifest = json.loads(z.read('manifest.json').decode('utf-8'))
        if 'steps.jsonl' in z.namelist():
            for line in z.read('steps.jsonl').decode('utf-8').strip().split('\n'):
                if line:
                    try:
                        steps.append(json.loads(line))
                    except:
                        pass
        if 'viewer.html' in z.namelist():
            viewer_html = z.read('viewer.html').decode('utf-8')

    if viewer_html and manifest:
        updated_data = {"manifest": manifest, "steps": steps}
        data_json = json.dumps(updated_data, indent=2)
        pattern = r'<script id="epi-data" type="application/json">.*?</script>'
        replacement = '<script id="epi-data" type="application/json">' + data_json + '</script>'
        viewer_html = re.sub(pattern, replacement, viewer_html, flags=re.DOTALL)

        viewer_file = Path('EPI_Evidence_Viewer.html')
        viewer_file.write_text(viewer_html, encoding='utf-8')

        escaped = html.escape(viewer_html)
        sig = manifest.get('signature', '')[:30] + "..." if manifest.get('signature') else "UNSIGNED"
        sig_color = "#10b981" if manifest.get('signature') else "#f59e0b"

        iframe_html = (
            '<div style="border: 4px solid {}; border-radius: 16px; overflow: hidden; margin: 25px 0;">'
            '<div style="background: linear-gradient(135deg, {}, #059669); color: white; padding: 18px 24px; display: flex; justify-content: space-between; align-items: center;">'
            '<span style="font-size: 22px; font-weight: bold;">EPI EVIDENCE VIEWER</span>'
            '<span style="font-family: monospace; font-size: 14px; background: rgba(255,255,255,0.25); padding: 8px 14px; border-radius: 8px;">SIGNED: {}</span>'
            '</div>'
            '<iframe srcdoc="{}" width="100%" height="600" style="border: none;" sandbox="allow-scripts allow-same-origin"></iframe>'
            '</div>'.format(sig_color, sig_color, sig, escaped)
        )
        display(HTML(iframe_html))
        display(HTML('<p style="color: #10b981; font-weight: bold;">Saved: {} (open in any browser)</p>'.format(viewer_file.name)))
    else:
        display(HTML('<p style="color: #ef4444;">Viewer not found in EPI file</p>'))
else:
    print("Run the recording cell first")
