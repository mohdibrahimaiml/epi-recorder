import shutil
import zipfile
import json
import subprocess
import sys
from pathlib import Path

# Ensure we can print UTF-8 to console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

VENV_EPI = Path(".\\venv-editable\\Scripts\\epi.exe")

def run_verify(path):
    proc = subprocess.run([str(VENV_EPI), "verify", str(path)], capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr

def test_tamper():
    original = Path("artifacts_generated/standard_op.epi")
    tampered_dir = Path("tamper_tests")
    if tampered_dir.exists(): shutil.rmtree(tampered_dir)
    tampered_dir.mkdir()

    # 1. Content Tamper (steps.jsonl)
    print("\n[Test 1] Tampering with steps.jsonl...")
    t1 = tampered_dir / "tampered_steps.epi"
    
    extract_path = tampered_dir / "extract_t1"
    with zipfile.ZipFile(original, 'r') as z:
        z.extractall(extract_path)
    
    steps_file = extract_path / "steps.jsonl"
    content = steps_file.read_text()
    steps_file.write_text(content + "\n{\"tampered\": true}")
    
    with zipfile.ZipFile(t1, 'w') as z:
        mimetype_path = extract_path / "mimetype"
        if mimetype_path.exists():
            z.write(mimetype_path, "mimetype")
        for f in extract_path.rglob("*"):
            if f.is_file() and f.name != "mimetype":
                z.write(f, f.relative_to(extract_path))
    
    rc, stdout, stderr = run_verify(t1)
    if "DECISION: FAIL" in stdout and "Integrity compromised" in stdout:
        print("[PASS] Tampered steps detected.")
    else:
        print(f"[FAIL] Tampered steps NOT detected. RC={rc}")
        print(f"Stdout: {stdout}")

    # 2. Manifest Tamper (signature)
    print("\n[Test 2] Tampering with manifest signature...")
    t2 = tampered_dir / "tampered_sig.epi"
    
    extract_path2 = tampered_dir / "extract_t2"
    with zipfile.ZipFile(original, 'r') as z:
        z.extractall(extract_path2)
    
    manifest_file = extract_path2 / "manifest.json"
    manifest = json.loads(manifest_file.read_text())
    sig = manifest["signature"]
    manifest["signature"] = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    manifest_file.write_text(json.dumps(manifest, indent=2))
    
    with zipfile.ZipFile(t2, 'w') as z:
        mimetype_path = extract_path2 / "mimetype"
        if mimetype_path.exists():
            z.write(mimetype_path, "mimetype")
        for f in extract_path2.rglob("*"):
            if f.is_file() and f.name != "mimetype":
                z.write(f, f.relative_to(extract_path2))
    
    rc, stdout, stderr = run_verify(t2)
    if "DECISION: FAIL" in stdout and "Invalid signature" in stdout:
        print("[PASS] Tampered signature detected.")
    else:
        print(f"[FAIL] Tampered signature NOT detected. RC={rc}")
        print(f"Stdout: {stdout}")

    # 3. Manifest Tamper (hash)
    print("\n[Test 3] Tampering with manifest file hash...")
    t3 = tampered_dir / "tampered_hash.epi"
    
    extract_path3 = tampered_dir / "extract_t3"
    with zipfile.ZipFile(original, 'r') as z:
        z.extractall(extract_path3)
    
    manifest_file = extract_path3 / "manifest.json"
    manifest = json.loads(manifest_file.read_text())
    h = manifest["file_manifest"]["steps.jsonl"]
    manifest["file_manifest"]["steps.jsonl"] = h[:-1] + ("0" if h[-1] != "0" else "1")
    manifest_file.write_text(json.dumps(manifest, indent=2))
    
    with zipfile.ZipFile(t3, 'w') as z:
        mimetype_path = extract_path3 / "mimetype"
        if mimetype_path.exists():
            z.write(mimetype_path, "mimetype")
        for f in extract_path3.rglob("*"):
            if f.is_file() and f.name != "mimetype":
                z.write(f, f.relative_to(extract_path3))
    
    rc, stdout, stderr = run_verify(t3)
    if "DECISION: FAIL" in stdout:
        print("[PASS] Tampered manifest hash detected.")
    else:
        print(f"[FAIL] Tampered manifest hash NOT detected. RC={rc}")
        print(f"Stdout: {stdout}")

if __name__ == "__main__":
    test_tamper()
