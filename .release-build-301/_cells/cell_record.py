# @title Record AI Execution { display-mode: "form" }
import time, os, subprocess, sys
from pathlib import Path
from IPython.display import clear_output, display, HTML

for f in Path('.').glob('*.epi'):
    f.unlink()
for f in Path('.').glob('epi-recordings/*.epi'):
    f.unlink()

print("=" * 70)
display(HTML('<h2 style="color: #ef4444;">RECORDING LIVE...</h2>'))
print()

start = time.time()
subprocess.run([sys.executable, "underwriter_agent.py"], check=False)
elapsed = time.time() - start

epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))
epi_file = max(epi_files, key=lambda p: p.stat().st_mtime) if epi_files else None

if epi_file:
    print()
    print("=" * 70)
    display(HTML(
        '<div style="background: linear-gradient(135deg, #10b981, #059669); padding: 30px; border-radius: 12px; text-align: center; color: white; margin: 20px 0;">'
        '<h2 style="color: white; margin: 0;">EVIDENCE SECURED</h2>'
        '<p style="font-size: 18px; margin: 15px 0;">File: {} | Size: {:.1f} KB | Time: {:.1f}s</p>'
        '<p style="font-size: 16px; opacity: 0.9;">Gemini API calls captured. Ed25519 signature applied.</p>'
        '</div>'.format(epi_file.name, epi_file.stat().st_size / 1024, elapsed)
    ))
    try:
        from google.colab import files
        files.download(str(epi_file))
    except:
        pass
else:
    display(HTML('<h2 style="color: #ef4444;">Recording failed - check output above</h2>'))
