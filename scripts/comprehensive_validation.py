"""
COMPREHENSIVE EPI-RECORDER VALIDATION - ALL COMPONENTS
Complete validation of every module, function, CLI command, and feature
"""
import subprocess
import sys
from pathlib import Path

print("="*80)
print("  EPI-RECORDER v1.1.0 - COMPREHENSIVE VALIDATION TEST SUITE")
print("="*80 + "\n")

total_tests = 0
passed_tests = 0
failed_tests = []

def test_result(name, success, error=None):
    """Record test result"""
    global total_tests, passed_tests, failed_tests
    total_tests += 1
    if success:
        passed_tests += 1
        print(f"  [{passed_tests:3d}] [OK] {name}")
    else:
        failed_tests.append((name, error))
        print(f"  [ X ] [FAIL] {name}")
        if error:
            print(f"        Error: {error}")

print("PHASE 1: Unit Tests (pytest)")
print("-" * 80)
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=no", "-q"],
    capture_output=True,
    text=True
)
test_count = result.stdout.count(" PASSED")
test_result(f"Unit tests ({test_count} tests)", result.returncode == 0, 
            result.stdout.split('\n')[-3] if result.returncode != 0 else None)

print("\nPHASE 2: CLI Commands")
print("-" * 80)

# Test each CLI command
cli_commands = [
    ("epi --help", "Main help"),
    ("epi version", "Version info"),
    ("epi help", "Help command"),
    ("epi keys list", "List keys"),
    ("epi ls", "List recordings"),
]

for cmd, desc in cli_commands:
    result = subprocess.run(
        f"python -m epi_cli.main {cmd.replace('epi ', '')}",
        shell=True,
        capture_output=True,
        text=True
    )
    test_result(f"CLI: {desc} ({cmd})", result.returncode == 0,
                result.stderr[:100] if result.returncode != 0 else None)

print("\nPHASE 3: Python API - Imports")
print("-" * 80)

imports = [
    ("from epi_recorder import record", "Main record function"),
    ("from epi_recorder import EpiRecorderSession", "Session class"),
    ("from epi_core.container import EPIContainer", "Container module"),
    ("from epi_core.trust import sign_manifest, verify_signature", "Trust module"),
    ("from epi_core.schemas import ManifestModel, StepModel", "Schema models"),
    ("from epi_core.redactor import Redactor", "Redactor class"),
    ("from epi_core.serialize import get_canonical_hash", "Serialization"),
    ("from epi_recorder.patcher import patch_openai, patch_requests", "Patcher"),
    ("from epi_recorder.environment import capture_full_environment", "Environment"),
    ("from epi_cli.keys import KeyManager", "Key manager"),
]

for import_stmt, desc in imports:
    try:
        exec(import_stmt)
        test_result(f"Import: {desc}", True)
    except Exception as e:
        test_result(f"Import: {desc}", False, str(e))

print("\nPHASE 4: Core Functionality")
print("-" * 80)

# Test decorator
try:
    from epi_recorder import record
    
    @record
    def test_decorator():
        return "works"
    
    result = test_decorator()
    test_result("Decorator usage", result == "works")
except Exception as e:
    test_result("Decorator usage", False, str(e))

# Test context manager
try:
    from epi_recorder import record
    import time
    
    # Note: record context manager handles path resolution to epi-recordings/ by default if relative
    # We will use absolute path for testing to be sure where it goes
    cwd = Path.cwd()
    test_file = cwd / f"test_{int(time.time())}.epi"
    
    with record(test_file, goal="test", metrics={"x": 1}) as session:
        session.log_step("test", {"data": "test"})
    
    exists = test_file.exists()
    if exists:
        test_file.unlink()
    test_result("Context manager with metadata", exists)
except Exception as e:
    test_result("Context manager with metadata", False, str(e))

# Test artifact logging
try:
    from epi_recorder import record
    from pathlib import Path
    import time
    import zipfile
    
    artifact = Path("artifact_test.txt")
    artifact.write_text("test")
    
    test_file = Path.cwd() / f"artifact_{int(time.time())}.epi"
    with record(test_file) as session:
        session.log_artifact(artifact)
    
    # Check if artifact is in .epi
    with zipfile.ZipFile(test_file) as z:
        has_artifact = any('artifact_test.txt' in name for name in z.namelist())
    
    test_file.unlink()
    artifact.unlink()
    test_result("Artifact embedding", has_artifact)
except Exception as e:
    test_result("Artifact embedding", False, str(e))

# Test redaction
try:
    from epi_core.redactor import Redactor
    
    r = Redactor()
    text = "API key sk-proj-abc123 and token ghp_secret"
    # Redactor.redact returns (redacted_data, count)
    redacted, count = r.redact(text)
    
    safe = "sk-proj-abc123" not in redacted and "ghp_secret" not in redacted
    test_result("Secret redaction", safe)
except Exception as e:
    test_result("Secret redaction", False, str(e))

# Test integrity verification
try:
    from epi_recorder import record
    from epi_core.container import EPIContainer
    import time
    
    test_file = Path.cwd() / f"verify_{int(time.time())}.epi"
    with record(test_file) as session:
        session.log_step("verify", {"test": 1})
    
    integrity_ok, _ = EPIContainer.verify_integrity(test_file)
    test_file.unlink()
    test_result("File integrity verification", integrity_ok)
except Exception as e:
    test_result("File integrity verification", False, str(e))

# Test signing
try:
    from epi_recorder import record
    from epi_core.container import EPIContainer
    import time
    
    # IMPORTANT: Auto-signing uses default key which might need to be generated
    # For this test, valid if file exists and has signature, OR if it warns/skips gracefully
    test_file = Path.cwd() / f"sign_{int(time.time())}.epi"
    
    # Ensure a key exists
    from epi_cli.keys import KeyManager
    km = KeyManager()
    if not km.has_key("default"):
        try:
            km.generate_keypair("default")
        except:
            pass

    with record(test_file, auto_sign=True) as session:
        session.log_step("sign", {"test": 1})
    
    if test_file.exists():
        manifest = EPIContainer.read_manifest(test_file)
        is_signed = manifest.signature is not None
        test_file.unlink()
        test_result("Cryptographic signing", is_signed)
    else:
        test_result("Cryptographic signing", False, "File not created")
except Exception as e:
    test_result("Cryptographic signing", False, str(e))

# Test environment capture
try:
    from epi_recorder.environment import capture_full_environment
    
    env = capture_full_environment()
    complete = all(key in env for key in ['os', 'python', 'packages'])
    test_result("Environment snapshot", complete)
except Exception as e:
    test_result("Environment snapshot", False, str(e))

# Test KeyManager
try:
    from epi_cli.keys import KeyManager
    
    km = KeyManager()
    has_default = km.has_default_key()
    test_result("KeyManager initialization", has_default)
except Exception as e:
    test_result("KeyManager initialization", False, str(e))

print("\nPHASE 5: File Structure")
print("-" * 80)

required_files = [
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "pyproject.toml",
    "epi_core/__init__.py",
    "epi_core/container.py",
    "epi_core/trust.py",
    "epi_core/schemas.py",
    "epi_core/redactor.py",
    "epi_core/serialize.py",
    "epi_recorder/__init__.py",
    "epi_recorder/api.py",
    "epi_recorder/patcher.py",
    "epi_recorder/environment.py",
    "epi_cli/__init__.py",
    "epi_cli/main.py",
    "epi_cli/keys.py",
    "epi_cli/ls.py",
    "epi_cli/verify.py",
    "epi_cli/view.py",
    "epi_cli/run.py",
    "epi_cli/record.py",
]

for file_path in required_files:
    p = Path(file_path)
    test_result(f"File exists: {file_path}", p.exists())

print("\nPHASE 6: Package Build")
print("-" * 80)

dist_files = [
    "dist/epi_recorder-1.1.0.tar.gz",
    "dist/epi_recorder-1.1.0-py3-none-any.whl",
]

for file_path in dist_files:
    p = Path(file_path)
    test_result(f"Build artifact: {p.name}", p.exists())

print("\n" + "=" * 80)
print("  VALIDATION SUMMARY")
print("=" * 80)
print(f"\nTotal Tests: {total_tests}")
print(f"Passed:      {passed_tests} ({passed_tests/total_tests*100:.1f}%)")
print(f"Failed:      {len(failed_tests)}")

if failed_tests:
    print("\nFailed Tests:")
    for name, error in failed_tests:
        print(f"  - {name}")
        if error:
            print(f"    {error}")
    print("\n[FAIL] Validation incomplete - please fix issues above")
    sys.exit(1)
else:
    print("\n" + "="*80)
    print("  ✅ ALL TESTS PASSED - PACKAGE IS PRODUCTION READY")
    print("="*80)
    print("\nNext step: twine upload dist/epi_recorder-1.1.0*")
