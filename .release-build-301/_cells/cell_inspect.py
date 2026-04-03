# @title Inspect Captured Evidence { display-mode: "form" }
import zipfile, json
from pathlib import Path
from IPython.display import display, HTML

epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))
epi_file = max(epi_files, key=lambda p: p.stat().st_mtime) if epi_files else None

if epi_file:
    with zipfile.ZipFile(epi_file, 'r') as z:
        manifest = json.loads(z.read('manifest.json').decode('utf-8'))
        steps = []
        if 'steps.jsonl' in z.namelist():
            for line in z.read('steps.jsonl').decode('utf-8').strip().split('\n'):
                if line:
                    steps.append(json.loads(line))

    print("=" * 70)
    display(HTML('<h2 style="color: #3b82f6;">Evidence Contents</h2>'))
    print("Workflow: {}".format(manifest.get('goal', 'N/A')))
    print("Total Steps: {}".format(len(steps)))

    signing_key = manifest.get('signing_key_id') or manifest.get('key_id') or manifest.get('public_key') or 'Not Found'
    sig = manifest.get('signature', 'UNSIGNED')
    print("Signed by: {}".format(signing_key))
    print("Signature: {}...".format(sig[:50]))
    print()

    llm_steps = [s for s in steps if s.get('kind', '').startswith('llm.')]
    display(HTML('<h3 style="color: #8b5cf6;">Gemini API Calls Captured: {}</h3>'.format(len(llm_steps))))

    for i, step in enumerate(llm_steps[:4]):
        kind = step.get('kind')
        content = step.get('content', {})

        if kind == 'llm.request':
            prompt = str(content.get('contents', ''))[:200]
            display(HTML(
                '<div style="background: #eff6ff; border-left: 4px solid #3b82f6; padding: 15px; margin: 10px 0; border-radius: 0 8px 8px 0;">'
                '<b style="color: #1e40af;">REQUEST #{}</b>'
                '<p style="font-family: monospace; font-size: 12px; color: #1e3a8a; margin: 10px 0;">Model: {}</p>'
                '<p style="font-family: monospace; font-size: 11px; color: #374151; margin: 0;">{}...</p>'
                '</div>'.format(i+1, content.get('model'), prompt)
            ))
        elif kind == 'llm.response':
            response = str(content.get('response', ''))[:200]
            tokens = content.get('usage', {})
            display(HTML(
                '<div style="background: #f0fdf4; border-left: 4px solid #10b981; padding: 15px; margin: 10px 0; border-radius: 0 8px 8px 0;">'
                '<b style="color: #166534;">RESPONSE</b>'
                '<p style="font-family: monospace; font-size: 11px; color: #374151; margin: 10px 0;">{}...</p>'
                '<p style="font-size: 11px; color: #6b7280; margin: 0;">Tokens: {}</p>'
                '</div>'.format(response, tokens.get('total_tokens', 'N/A'))
            ))

    print("=" * 70)
else:
    print("Run the recording cell first")
