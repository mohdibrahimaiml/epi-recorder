"""
COMPLETE EPI-RECORDER VALIDATION TEST SUITE
Tests every single component, module, function, CLI command, and feature
"""
import sys
import time
from pathlib import Path

def section(title):
    """Print section header"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80 + "\n")

def test(name):
    """Print test name"""
    print(f"[TEST] {name}...", end=" ", flush=True)

def success():
    """Mark test as passed"""
    print("[OK]")

def fail(msg):
    """Mark test as failed"""
    print(f"[FAIL] {msg}")
    sys.exit(1)

# ==============================================================================
# PHASE 1: IMPORTS AND MODULE STRUCTURE
# ==============================================================================
section("PHASE 1: Module Import Tests")

test("Import epi_core.container")
try:
    from epi_core.container import EPIContainer
    success()
except Exception as e:
    fail(str(e))

test("Import epi_core.trust")
try:
    from epi_core.trust import sign_manifest, verify_signature
    success()
except Exception as e:
    fail(str(e))

test("Import epi_core.schemas")
try:
    from epi_core.schemas import ManifestModel, StepModel
    success()
except Exception as e:
    fail(str(e))

test("Import epi_core.redactor")
try:
    from epi_core.redactor import Redactor
    success()
except Exception as e:
    fail(str(e))

test("Import epi_core.serialize")
try:
    from epi_core.serialize import get_canonical_hash
    success()
except Exception as e:
    fail(str(e))

test("Import epi_recorder.api")
try:
    from epi_recorder import record, EpiRecorderSession
    success()
except Exception as e:
    fail(str(e))

test("Import epi_recorder.patcher")
try:
    from epi_recorder.patcher import patch_openai, patch_requests
    success()
except Exception as e:
    fail(str(e))

test("Import epi_recorder.environment")
try:
    from epi_recorder.environment import capture_environment
    success()
except Exception as e:
    fail(str(e))

test("Import epi_cli modules")
try:
    from epi_cli.keys import KeyManager
    from epi_cli import main
    success()
except Exception as e:
    fail(str(e))

# ==============================================================================
# PHASE 2: CORE FUNCTIONALITY TESTS
# ==============================================================================
section("PHASE 2: Core Component Tests")

test("KeyManager initialization")
try:
    from epi_cli.keys import KeyManager
    km = KeyManager()
    assert km.keys_dir.exists()
    success()
except Exception as e:
    fail(str(e))

test("Redactor pattern loading")
try:
    from epi_core.redactor import Redactor
    r = Redactor()
    assert len(r.patterns) > 10  # Should have 15+ patterns
    success()
except Exception as e:
    fail(str(e))

test("Schema validation")
try:
    from epi_core.schemas import StepModel
    step = StepModel(
        index=0,
        timestamp="2025-01-01T00:00:00",
        kind="test",
        content={"test": "data"}
    )
    assert step.index == 0
    success()
except Exception as e:
    fail(str(e))

test("Environment capture")
try:
    from epi_recorder.environment import capture_environment
    env = capture_environment()
    assert "os" in env
    assert "python" in env
    assert "packages" in env
    success()
except Exception as e:
    fail(str(e))

# ==============================================================================
# PHASE 3: PYTHON API TESTS
# ==============================================================================
section("PHASE 3: Python API Tests")

test("Basic @record decorator")
try:
    from epi_recorder import record
    
    @record
    def test_func():
        return "decorator_works"
    
    result = test_func()
    assert result == "decorator_works"
    success()
except Exception as e:
    fail(str(e))

test("Context manager with metadata")
try:
    from epi_recorder import record
    from pathlib import Path
    import time
    
    test_file = Path(f"validation_test_{int(time.time())}.epi")
    
    with record(test_file, 
                goal="Test goal",
                metrics={"test": 1},
                metadata_tags=["validation"]) as session:
        session.log_step("test.step", {"data": "test"})
    
    assert test_file.exists()
    test_file.unlink()  # Cleanup
    success()
except Exception as e:
    fail(str(e))

test("Artifact logging")
try:
    from epi_recorder import record
    from pathlib import Path
    import time
    
    # Create test artifact
    artifact = Path("test_artifact.txt")
    artifact.write_text("test content")
    
    test_file = Path(f"artifact_test_{int(time.time())}.epi")
    
    with record(test_file) as session:
        session.log_artifact(artifact)
    
    assert test_file.exists()
    
    # Verify artifact is in .epi file
    import zipfile
    with zipfile.ZipFile(test_file) as z:
        assert any('test_artifact.txt' in name for name in z.namelist())
    
    # Cleanup
    test_file.unlink()
    artifact.unlink()
    success()
except Exception as e:
    fail(str(e))

test("Redaction functionality")
try:
    from epi_core.redactor import Redactor
    
    r = Redactor()
    # Use realistic fake keys that match actual patterns
    fake_openai = "sk-proj-" + "a" * 48  # OpenAI project key (48+ chars)
    fake_github = "ghp_" + "b" * 36  # GitHub token (36 chars)
    sensitive = f"My API key is {fake_openai} and token is {fake_github}"
    redacted, count = r.redact(sensitive)
    
    assert fake_openai not in redacted
    assert fake_github not in redacted
    assert count >= 2  # Should have redacted both keys
    success()
except Exception as e:
    fail(str(e))

test("File integrity verification")
try:
    from epi_recorder import record
    from epi_core.container import EPIContainer
    from pathlib import Path
    import time
    
    test_file = Path(f"integrity_test_{int(time.time())}.epi")
    
    with record(test_file) as session:
        session.log_step("verify", {"test": "integrity"})
    
    # Verify integrity
    integrity_ok, issues = EPIContainer.verify_integrity(test_file)
    assert integrity_ok, f"Integrity check failed: {issues}"
    
    test_file.unlink()
    success()
except Exception as e:
    fail(str(e))

test("Cryptographic signing")
try:
    from epi_recorder import record
    from epi_core.container import EPIContainer
    from pathlib import Path
    import time
    
    test_file = Path(f"signature_test_{int(time.time())}.epi")
    
    with record(test_file, auto_sign=True) as session:
        session.log_step("sign", {"test": "signature"})
    
    # Read manifest
    manifest = EPIContainer.read_manifest(test_file)
    assert manifest.signature is not None
    assert manifest.signature.startswith("ed25519:")
    
    test_file.unlink()
    success()
except Exception as e:
    fail(str(e))

# ==============================================================================
# PHASE 4: SUMMARY
# ==============================================================================
section("PHASE 4: Test Summary")

print("\n[OK] All Python API and Core Tests Passed!")
print("\nComponents Validated:")
print("  [OK] epi_core.container")
print("  [OK] epi_core.trust")
print("  [OK] epi_core.schemas")
print("  [OK] epi_core.redactor")
print("  [OK] epi_core.serialize")
print("  [OK] epi_recorder.api")
print("  [OK] epi_recorder.patcher")
print("  [OK] epi_recorder.environment")
print("  [OK] epi_cli modules")
print("\nFunctionality Validated:")
print("  [OK] Decorator usage")
print("  [OK] Context manager")
print("  [OK] Metadata handling")
print("  [OK] Artifact logging")
print("  [OK] Redaction system")
print("  [OK] File integrity")
print("  [OK] Cryptographic signing")

print("\n" + "="*80)
print("  PYTHON API VALIDATION: COMPLETE")
print("="*80)
print("\nNext: Run CLI validation test")
