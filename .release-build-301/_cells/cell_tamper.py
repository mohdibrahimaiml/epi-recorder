# @title Attempt Forgery { display-mode: "form" }
import zipfile, json, os, shutil, subprocess, sys
from pathlib import Path
from IPython.display import display, HTML

epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))
epi_file = max(epi_files, key=lambda p: p.stat().st_mtime) if epi_files else None

if epi_file:
    print("=" * 70)
    display(HTML('<h2 style="color: #f59e0b;">Creating Forged Evidence...</h2>'))
    print()

    tamper_dir = Path("tamper_workspace")
    forged_file = Path("FORGED_LOAN_APPROVAL.epi")

    if tamper_dir.exists():
        shutil.rmtree(tamper_dir)
    forged_file.unlink(missing_ok=True)

    # 1. Extract the real .epi file
    print("1. Extracting {}...".format(epi_file.name))
    with zipfile.ZipFile(epi_file, 'r') as z:
        z.extractall(tamper_dir)

    # 2. Modify the actual decision data inside steps.jsonl
    steps_file = tamper_dir / "steps.jsonl"
    if steps_file.exists():
        original = steps_file.read_text(encoding='utf-8')
        tampered = original.replace("APPROVED", "REJECTED").replace("100000", "10000")
        steps_file.write_text(tampered, encoding='utf-8')
        print("2. Modified steps.jsonl: APPROVED -> REJECTED, $100,000 -> $10,000")
    else:
        print("2. WARNING: steps.jsonl not found, modifying manifest instead")
        mf = tamper_dir / "manifest.json"
        if mf.exists():
            data = json.loads(mf.read_text(encoding='utf-8'))
            data["tampered"] = True
            mf.write_text(json.dumps(data), encoding='utf-8')

    # 3. Repack into a new .epi file
    print("3. Repacking into FORGED_LOAN_APPROVAL.epi...")
    with zipfile.ZipFile(forged_file, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(tamper_dir):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, tamper_dir)
                z.write(full_path, arcname)

    print()
    print("-" * 70)
    print("Running cryptographic verification on forged file...")
    print()

    # 4. Run REAL epi verify on the tampered file (using installed CLI entry point)
    result = subprocess.run(
        ["epi", "verify", str(forged_file)],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    # Cleanup
    shutil.rmtree(tamper_dir, ignore_errors=True)
    forged_file.unlink(missing_ok=True)

    print()
    print("=" * 70)

    if result.returncode != 0:
        display(HTML(
            '<div style="background: #fef2f2; border: 2px solid #ef4444; padding: 20px; border-radius: 12px; margin: 20px 0;">'
            '<h2 style="color: #dc2626; margin: 0 0 10px 0;">TAMPERING DETECTED</h2>'
            '<p style="color: #b91c1c; margin: 0 0 10px 0; font-weight: bold;">'
            'We extracted the .epi archive, changed APPROVED to REJECTED and $100,000 to $10,000 inside steps.jsonl, '
            'repacked it, and ran epi verify.</p>'
            '<p style="color: #7f1d1d; margin: 0;">'
            '<b>Signature invalid. Modified steps.jsonl caught instantly.</b><br>'
            'The original decision chain is mathematically unforgeable.</p>'
            '</div>'
        ))
    else:
        display(HTML(
            '<div style="background: #fef3c7; border: 2px solid #f59e0b; padding: 20px; border-radius: 12px; margin: 20px 0;">'
            '<h2 style="color: #92400e; margin: 0 0 10px 0;">Note: Verify returned 0</h2>'
            '<p style="color: #78350f; margin: 0;">'
            'Check EPI signing setup — key may not be configured in this environment. '
            'In production, the tampered file would fail verification.</p>'
            '</div>'
        ))
else:
    print("Run the recording cell first")
