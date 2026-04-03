# @title Verify Signature { display-mode: "form" }
import subprocess, sys
from pathlib import Path
from IPython.display import display, HTML

epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))
epi_file = max(epi_files, key=lambda p: p.stat().st_mtime) if epi_files else None

if epi_file:
    print("=" * 70)
    display(HTML('<h2 style="color: #3b82f6;">Verifying Cryptographic Signature...</h2>'))
    print()

    result = subprocess.run(
        ["epi", "verify", str(epi_file)],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if result.returncode == 0:
        display(HTML(
            '<div style="background: #f0fdf4; border: 2px solid #10b981; padding: 20px; border-radius: 12px; margin: 20px 0; text-align: center;">'
            '<h2 style="color: #166534; margin: 0;">SIGNATURE VALID</h2>'
            '<p style="color: #15803d; margin: 10px 0;">This evidence has not been tampered with.</p>'
            '<p style="color: #6b7280; font-size: 14px;">Algorithm: Ed25519 | Military-grade cryptography</p>'
            '</div>'
        ))
    else:
        display(HTML(
            '<div style="background: #fef2f2; border: 2px solid #ef4444; padding: 20px; border-radius: 12px; margin: 20px 0; text-align: center;">'
            '<h2 style="color: #dc2626; margin: 0;">Verification Output</h2>'
            '<p style="color: #b91c1c; margin: 10px 0;">Return code: {}</p>'
            '</div>'.format(result.returncode)
        ))

    print()
    print("=" * 70)
else:
    print("Run the recording cell first")
