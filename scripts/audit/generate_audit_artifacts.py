import os
import subprocess
import json
import shutil
from pathlib import Path

# Use the venv in the eval workspace
VENV_PYTHON = Path(".\\venv-editable\\Scripts\\python.exe")
VENV_EPI = Path(".\\venv-editable\\Scripts\\epi.exe")

ARTIFACT_DIR = Path("artifacts_generated")
if ARTIFACT_DIR.exists():
    shutil.rmtree(ARTIFACT_DIR)
ARTIFACT_DIR.mkdir(exist_ok=True)

# Helper to run commands
def run_cmd(args, env=None, check=True):
    print(f"Running: {' '.join(args)}")
    proc = subprocess.run(args, env=env, check=False, capture_output=True, text=True, encoding="utf-8")
    if check and proc.returncode != 0:
        print(f"Error output: {proc.stderr}")
        raise subprocess.CalledProcessError(proc.returncode, args, output=proc.stdout, stderr=proc.stderr)
    return proc

# 1. Generate keys
print("Generating ephemeral keys...")
run_cmd([str(VENV_EPI), "keys", "generate", "--name", "ephemeral_eval", "--overwrite"])

# Define environment
env = os.environ.copy()
env["EPI_ENABLED"] = "1"
env["EPI_ARTIFACT_DIR"] = str(ARTIFACT_DIR.resolve())
# Ensure we use the ephemeral key for signing
env["EPI_SIGNING_KEY"] = "ephemeral_eval"

# 2. Standard Signed Artifact
print("Generating standard signed artifact...")
with open("simple_script.py", "w") as f:
    f.write("from epi_recorder import record\n")
    f.write("def do_standard():\n")
    f.write("    with record('standard_op.epi'):\n")
    f.write("        print('Hello from EPI!')\n")
    f.write("do_standard()\n")

run_cmd([str(VENV_PYTHON), "simple_script.py"], env=env)

# 3. Unsigned Artifact
print("Generating unsigned artifact...")
with open("unsigned_script.py", "w") as f:
    f.write("from epi_recorder import record\n")
    f.write("def do_unsigned():\n")
    f.write("    with record('unsigned_op.epi'):\n")
    f.write("        print('This is unsigned')\n")
    f.write("do_unsigned()\n")

env_no_sign = env.copy()
env_no_sign.pop("EPI_SIGNING_KEY", None)
# To force unsigned, we might need a specific flag or just no default key.
# But EPI usually signs if a key exists. 
# Let's use epi run --no-verify or just no key.
# Actually, let's try to rename the keys dir temporarily.
# Or just use a different EPI_HOME.
env_unsigned = env.copy()
env_unsigned["EPI_HOME"] = str(Path("temp_epi_home").resolve())
if Path("temp_epi_home").exists(): shutil.rmtree("temp_epi_home")
Path("temp_epi_home").mkdir()
run_cmd([str(VENV_PYTHON), "unsigned_script.py"], env=env_unsigned)

# 4. Large Artifact
print("Generating large artifact...")
with open("large_script.py", "w") as f:
    f.write("from epi_recorder import record\n")
    f.write("def do_large():\n")
    f.write("    with record('large_op.epi'):\n")
    f.write("        data = {'items': ['data'] * 100000}\n")
    f.write("        print(f'Generated {len(data['items'])} items')\n")
    f.write("do_large()\n")
run_cmd([str(VENV_PYTHON), "large_script.py"], env=env)

# 5. AGT Imported Artifact
print("Generating AGT imported artifact...")
with open("dummy_agt.json", "w") as f:
    json.dump({
        "metadata": {
            "workflow_id": "00000000-0000-0000-0000-000000000000",
            "system_name": "TestSystem"
        },
        "audit_logs": [
            {"event": "start", "timestamp": "2026-05-16T12:00:00Z"},
            {"event": "action", "timestamp": "2026-05-16T12:00:01Z", "data": "Hello World"}
        ]
    }, f)

# Correct command: epi import agt <INPUT> --out <OUTPUT>
run_cmd([str(VENV_EPI), "import", "agt", "dummy_agt.json", "--out", str(ARTIFACT_DIR / "agt_imported.epi")], env=env)

# 6. Artifact with Redactions
print("Generating artifact with redactions...")
with open("redaction_script.py", "w") as f:
    f.write("from epi_recorder import record\n")
    f.write("def do_redaction():\n")
    f.write("    with record('redacted_op.epi'):\n")
    f.write("        print('My key is sk-proj-1234567890abcdef1234567890abcdef1234567890abcdef')\n")
    f.write("        print('My email is test@example.com')\n")
    f.write("do_redaction()\n")
run_cmd([str(VENV_PYTHON), "redaction_script.py"], env=env)

# 7. Artifact with Policy Evaluation
print("Generating artifact with policy evaluation...")
with open("policy.json", "w") as f:
    json.dump({
        "rules": [
            {"id": "R1", "description": "No errors allowed", "type": "regex", "pattern": "^(?!.*error).*$"}
        ]
    }, f)

env_policy = env.copy()
env_policy["EPI_POLICY_FILE"] = str(Path("policy.json").resolve())
run_cmd([str(VENV_PYTHON), "simple_script.py"], env=env_policy)

# 8. SCITT Artifact (using mock service)
print("Generating SCITT artifact...")
# We need to use the library to create it manually or use a mock server and epi scitt register.
# Let's try to run a mock server in the background and use epi scitt register.
# But for a simple test, let's just use a python script that uses the mock service helper.
with open("gen_scitt.py", "w") as f:
    f.write("import os\n")
    f.write("from pathlib import Path\n")
    f.write("from epi_core.container import EPIContainer\n")
    f.write("from epi_core.scitt import create_scitt_statement, scitt_governance_from_info\n")
    f.write("from tests.helpers.mock_scitt_service import MockSCITTService\n")
    f.write("from epi_cli.keys import KeyManager\n")
    f.write("\n")
    f.write("epi_path = Path('artifacts_generated/standard_op.epi')\n")
    f.write("if not epi_path.exists():\n")
    f.write("    # Use the one in epi-recordings if not in artifacts_generated\n")
    f.write("    epi_path = list(Path('epi-recordings').glob('standard_op*.epi'))[0]\n")
    f.write("\n")
    f.write("manifest = EPIContainer.read_manifest(epi_path)\n")
    f.write("km = KeyManager()\n")
    f.write("priv = km.load_private_key('ephemeral_eval')\n")
    f.write("\n")
    f.write("mock_service = MockSCITTService()\n")
    f.write("stmt = create_scitt_statement(manifest, priv, issuer='test-issuer')\n")
    f.write("rcpt, info = mock_service.register(stmt)\n")
    f.write("\n")
    f.write("gov = scitt_governance_from_info(info, issuer='test-issuer')\n")
    f.write("manifest.governance = {'scitt': gov}\n")
    f.write("\n")
    f.write("# Repack with SCITT artifacts\n")
    f.write("import tempfile, shutil\n")
    f.write("with tempfile.TemporaryDirectory() as tmp:\n")
    f.write("    EPIContainer.unpack(epi_path, Path(tmp))\n")
    f.write("    scitt_dir = Path(tmp) / 'artifacts' / 'scitt'\n")
    f.write("    scitt_dir.mkdir(parents=True)\n")
    f.write("    (scitt_dir / 'statement.cbor').write_bytes(stmt)\n")
    f.write("    (scitt_dir / 'receipt.cbor').write_bytes(rcpt)\n")
    f.write("    EPIContainer.pack(Path(tmp), manifest, Path('artifacts_generated/scitt_op.epi'))\n")

# Need to set PYTHONPATH to find tests.helpers
env_scitt = env.copy()
env_scitt["PYTHONPATH"] = "."
run_cmd([str(VENV_PYTHON), "gen_scitt.py"], env=env_scitt)

print("Artifact generation complete.")
