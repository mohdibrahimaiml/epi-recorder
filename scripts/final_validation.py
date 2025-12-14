"""
FINAL COMPREHENSIVE VALIDATION - epi-recorder v1.1.0
Complete test of all functionality with correct API calls
"""
import subprocess
import sys
from pathlib import Path

print("="*80)
print("  FINAL VALIDATION: epi-recorder v1.1.0")
print("="*80 + "\n")

passed = 0
total = 0

def test(name, condition, error=None):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print(f"  [{passed:3d}] [OK] {name}")
        return True
    else:
        print(f"  [FAIL] {name}")
        if error:
            print(f"         {error}")
        return False

# ==============================================================================
# CRITICAL TESTS - Must all pass
# ==============================================================================

print("\n" + "="*80)
print("CRITICAL TESTS")
print("="*80)

print("\n1. Unit Tests")
print("-"*80)
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
    capture_output=True,
    text=True
)
test_count = result.stdout.count(" passed")
test("All unit tests pass (251 tests)", result.returncode == 0 and test_count >= 250)

print("\n2. File Structure")
print("-"*80)
critical_files = [
    "README.md", "LICENSE", "CHANGELOG.md", "pyproject.toml",
    "epi_core/container.py", "epi_core/trust.py", "epi_recorder/api.py",
    "epi_cli/main.py", "dist/epi_recorder-1.1.0.tar.gz",
    "dist/epi_recorder-1.1.0-py3-none-any.whl"
]
for f in critical_files:
    test(f"File exists: {f}", Path(f).exists())

print("\n3. Module Imports")
print("-"*80)
imports_ok = True
try:
    from epi_recorder import record, EpiRecorderSession
    test("Import epi_recorder", True)
except Exception as e:
    test("Import epi_recorder", False, str(e))
    imports_ok = False

try:
    from epi_core.container import EPIContainer
    from epi_core.trust import sign_manifest
    from epi_core.redactor import Redactor
    test("Import epi_core modules", True)
except Exception as e:
    test("Import epi_core modules", False, str(e))
    imports_ok = False

try:
    from epi_cli.keys import KeyManager
    test("Import epi_cli modules", True)
except Exception as e:
    test("Import epi_cli modules", False, str(e))
    imports_ok = False

#print("\n4. Basic Functionality")
print("-"*80)

# Decorator test
try:
    from epi_recorder import record
    
    @record
    def test_basic():
        return 42
    
    result = test_basic()
    test("Decorator works", result == 42)
except Exception as e:
    test("Decorator works", False, str(e))

# Redaction test
try:
    from epi_core.redactor import Redactor
    r = Redactor()
    text = "key is sk-abc123"
    redacted, count = r.redact(text)
    test("Redaction works", count > 0 and "sk-abc123" not in redacted)
except Exception as e:
    test("Redaction works", False, str(e))

print("\n5. CLI Commands")
print("-"*80)
cli_tests = [
    ("--help", "Help works"),
    ("version", "Version works"),
    ("keys list", "Keys list works"),
    ("ls", "List recordings works"),
]

for cmd, desc in cli_tests:
    result = subprocess.run(
        f"python -m epi_cli.main {cmd}",
        shell=True,
        capture_output=True
    )
    test(f"CLI: {desc}", result.returncode == 0)

# ==============================================================================
# SUMMARY
# ==============================================================================

print("\n" + "="*80)
print("VALIDATION SUMMARY")
print("="*80)
print(f"\nTests Run:    {total}")
print(f"Tests Passed: {passed}")
print(f"Tests Failed: {total - passed}")
print(f"Success Rate: {passed/total*100:.1f}%")

if passed == total:
    print("\n" + "="*80)
    print("  ✅ ALL CRITICAL TESTS PASSED")
    print("  🚀 PACKAGE IS READY FOR PYPI PUBLICATION")
    print("="*80)
    print("\nNext step:")
    print("  twine upload dist/epi_recorder-1.1.0*")
    sys.exit(0)
else:
    print("\n" + "="*80)
    print("  ⚠️  SOME TESTS FAILED")
    print("="*80)
    print(f"\n{total - passed} test(s) need attention")
    sys.exit(1)
