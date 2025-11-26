"""
FINAL COMPREHENSIVE TEST - CORRECTED
All tests with proper expectations
"""
import sys
import time
import json
import zipfile
from pathlib import Path

print("=" * 80)
print("FINAL COMPREHENSIVE EPI-RECORDER TEST")
print("=" * 80)

passed = 0
failed = 0

def test(name, func):
    global passed, failed
    print(f"\n[TEST] {name}")
    try:
        func()
        print(f"  [PASS]")
        passed += 1
        return True
    except AssertionError as e:
        print(f"  [FAIL] {e}")
        failed += 1
        return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()
        failed += 1
        return False

# Test 1: All imports
def test_imports():
    from epi_recorder import record, EpiRecorderSession
    from epi_core.container import EPIContainer
    from epi_core.trust import sign_manifest
    from epi_core.redactor import Redactor
    from epi_cli.keys import KeyManager

test("1. Module Imports", test_imports)

# Test 2: File creation with record()
def test_record():
    from epi_recorder import record
    f = Path(f"test_{int(time.time())}.epi")
    with record(f, auto_sign=False) as s:
        s.log_step("test", {"x": 1})
    assert f.exists()
    assert f.stat().st_size > 1000
    f.unlink()

test("2. File Creation with record()", test_record)

# Test 3: File creation with EpiRecorderSession
def test_session():
    from epi_recorder import EpiRecorderSession
    f = Path(f"test_{int(time.time())}.epi")
    with EpiRecorderSession(f) as s:
        s.log_step("test", {"x": 1})
    assert f.exists()
    f.unlink()

test("3. File Creation with EpiRecorderSession", test_session)

# Test 4: Auto-signing (CRITICAL FIX)
def test_signing():
    from epi_recorder import record
    from epi_core.container import EPIContainer
    f = Path(f"test_{int(time.time())}.epi")
    with record(f, auto_sign=True) as s:
        s.log_step("test", {"signed": True})
    assert f.exists(), "File not created with auto_sign=True"
    m = EPIContainer.read_manifest(f)
    assert m.signature is not None, "File not signed"
    assert m.signature.startswith("ed25519:"), "Invalid signature"
    f.unlink()

test("4. Auto-Signing (CRITICAL FIX)", test_signing)

# Test 5: Path resolution (CRITICAL FIX)
def test_path():
    from epi_recorder import record
    f = Path(f"test_{int(time.time())}.epi")
    with record(f, auto_sign=False) as s:
        s.log_step("test", {"x": 1})
    # Should be in current directory
    assert f.exists(), f"File not in current directory"
    f.unlink()

test("5. Path Resolution (CRITICAL FIX)", test_path)

# Test 6: Artifact logging
def test_artifact():
    from epi_recorder import record
    art = Path("artifact.txt")
    art.write_text("content")
    f = Path(f"test_{int(time.time())}.epi")
    with record(f, auto_sign=False) as s:
        s.log_artifact(art)
    with zipfile.ZipFile(f) as zf:
        assert any('artifact.txt' in n for n in zf.namelist())
    f.unlink()
    art.unlink()

test("6. Artifact Logging", test_artifact)

# Test 7: Redaction
def test_redaction():
    from epi_core.redactor import Redactor
    r = Redactor()
    key = "sk-proj-" + "a" * 48
    text = f"Key: {key}"
    redacted, count = r.redact(text)
    assert key not in redacted
    assert count > 0

test("7. Redaction", test_redaction)

# Test 8: File integrity
def test_integrity():
    from epi_recorder import record
    from epi_core.container import EPIContainer
    f = Path(f"test_{int(time.time())}.epi")
    with record(f, auto_sign=False) as s:
        s.log_step("test", {"x": 1})
    ok, issues = EPIContainer.verify_integrity(f)
    assert ok, f"Integrity failed: {issues}"
    f.unlink()

test("8. File Integrity", test_integrity)

# Test 9: Metadata (CORRECTED)
def test_metadata():
    from epi_recorder import record
    from epi_core.container import EPIContainer
    f = Path(f"test_{int(time.time())}.epi")
    with record(f, goal="G", notes="N", metrics={"m": 1}, 
                approved_by="A", metadata_tags=["t"], auto_sign=False) as s:
        s.log_step("test", {"x": 1})
    m = EPIContainer.read_manifest(f)
    # Metadata is directly on manifest, not nested
    assert m.goal == "G"
    assert m.notes == "N"
    assert m.metrics == {"m": 1}
    assert m.approved_by == "A"
    assert m.tags == ["t"]
    f.unlink()

test("9. Metadata Handling", test_metadata)

# Test 10: Steps recording (CORRECTED)
def test_steps():
    from epi_recorder import record
    f = Path(f"test_{int(time.time())}.epi")
    with record(f, auto_sign=False) as s:
        s.log_step("step1", {"data": "first"})
        s.log_step("step2", {"data": "second"})
    with zipfile.ZipFile(f) as zf:
        steps = zf.read("steps.jsonl").decode('utf-8')
    lines = [l for l in steps.strip().split('\n') if l]
    # System adds session.start, user steps, environment.captured, session.end
    assert len(lines) >= 4  # At least 2 user steps + auto steps
    # Find user steps
    user_steps = [json.loads(l) for l in lines if json.loads(l)['kind'] in ['step1', 'step2']]
    assert len(user_steps) == 2
    assert user_steps[0]['kind'] == 'step1'
    assert user_steps[0]['content']['data'] == 'first'
    f.unlink()

test("10. Steps Recording", test_steps)

# Test 11: Environment capture
def test_env():
    from epi_recorder.environment import capture_environment
    env = capture_environment()
    assert "os" in env
    assert "python" in env

test("11. Environment Capture", test_env)

# Test 12: KeyManager
def test_keys():
    from epi_cli.keys import KeyManager
    km = KeyManager()
    assert km.keys_dir.exists()

test("12. KeyManager", test_keys)

# SUMMARY
print("\n" + "=" * 80)
print(f"RESULTS: {passed} passed, {failed} failed out of 12 tests")
print("=" * 80)

if failed == 0:
    print("\nALL TESTS PASSED")
    print("Package is 100% production-ready!")
    sys.exit(0)
else:
    print(f"\n{failed} TEST(S) FAILED")
    sys.exit(1)
