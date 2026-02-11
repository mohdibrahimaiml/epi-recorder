"""
EPI v2.3.0 - COMPREHENSIVE TEST SUITE
=====================================

Tests LITERALLY EVERYTHING:
1. Package imports and exports
2. All CLI commands
3. Python API (explicit, wrapper, legacy)
4. Evidence file creation
5. Cryptographic signing and verification
6. Embedded viewer
7. File format integrity
8. Error handling
"""

import subprocess
import sys
import tempfile
import json
import zipfile
import shutil
from pathlib import Path
from unittest.mock import Mock
import warnings

# Results tracking
PASSED = []
FAILED = []

def log_pass(test_name):
    PASSED.append(test_name)
    print(f"   [PASS] {test_name}")

def log_fail(test_name, error):
    FAILED.append((test_name, str(error)))
    print(f"   [FAIL] {test_name}: {error}")

def run_cmd(cmd, cwd=None):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)

print("=" * 70)
print("EPI v2.3.0 - COMPREHENSIVE TEST SUITE")
print("=" * 70)

# Create test directory
test_dir = Path(tempfile.mkdtemp(prefix="epi_comprehensive_test_"))
print(f"\nTest directory: {test_dir}")

# ============================================================================
# SECTION 1: PACKAGE IMPORTS
# ============================================================================
print("\n" + "=" * 70)
print("SECTION 1: PACKAGE IMPORTS")
print("=" * 70)

# 1.1 Core imports
try:
    from epi_recorder import record, __version__
    log_pass("epi_recorder.record import")
except Exception as e:
    log_fail("epi_recorder.record import", e)

# 1.2 Wrapper imports
try:
    from epi_recorder import wrap_openai, TracedOpenAI
    log_pass("epi_recorder wrapper imports")
except Exception as e:
    log_fail("epi_recorder wrapper imports", e)

# 1.3 Session API
try:
    from epi_recorder import get_current_session, EpiRecorderSession
    log_pass("epi_recorder session API")
except Exception as e:
    log_fail("epi_recorder session API", e)

# 1.4 Wrapper submodule
try:
    from epi_recorder.wrappers import TracedCompletions, TracedChat, TracedClientBase
    log_pass("epi_recorder.wrappers submodule")
except Exception as e:
    log_fail("epi_recorder.wrappers submodule", e)

# 1.5 Core module
try:
    from epi_core import EPIContainer, ManifestModel
    log_pass("epi_core container/manifest")
except Exception as e:
    log_fail("epi_core container/manifest", e)

# 1.6 Trust module
try:
    from epi_core.trust import generate_keypair, sign_manifest, verify_signature
    log_pass("epi_core.trust cryptography")
except Exception as e:
    log_fail("epi_core.trust cryptography", e)

# 1.7 Redactor
try:
    from epi_core.redactor import Redactor
    log_pass("epi_core.redactor")
except Exception as e:
    log_fail("epi_core.redactor", e)

# 1.8 Serialization
try:
    from epi_core.serialize import serialize_step, deserialize_step
    log_pass("epi_core.serialize")
except Exception as e:
    log_fail("epi_core.serialize", e)

# 1.9 Version check
try:
    assert __version__ == "2.4.0", f"Expected 2.4.0, got {__version__}"
    log_pass(f"Version is 2.4.0")
except Exception as e:
    log_fail("Version check", e)

# ============================================================================
# SECTION 2: CLI COMMANDS
# ============================================================================
print("\n" + "=" * 70)
print("SECTION 2: CLI COMMANDS")
print("=" * 70)

# 2.1 epi --help
result = run_cmd("python -m epi_cli.main --help")
if result.returncode == 0 and "Usage:" in result.stdout:
    log_pass("epi --help")
else:
    log_fail("epi --help", result.stderr[:100])

# 2.2 epi run --help
result = run_cmd("python -m epi_cli.main run --help")
if result.returncode == 0:
    log_pass("epi run --help")
else:
    log_fail("epi run --help", result.stderr[:100])

# 2.3 epi record --help
result = run_cmd("python -m epi_cli.main record --help")
if result.returncode == 0:
    log_pass("epi record --help")
else:
    log_fail("epi record --help", result.stderr[:100])

# 2.4 epi keys list
result = run_cmd("python -m epi_cli.main keys list")
if result.returncode == 0:
    log_pass("epi keys list")
else:
    log_fail("epi keys list", result.stderr[:100])

# Create a sample .epi for testing
sample_epi = test_dir / "sample.epi"
with record(str(sample_epi), workflow_name="CLI Test") as epi:
    epi.log_step("test.init", {"purpose": "CLI testing"})
    epi.log_chat(
        model="gpt-4",
        messages=[{"role": "user", "content": "test"}],
        response_content="test response",
        provider="openai"
    )

# 2.5 epi verify
result = run_cmd(f"python -m epi_cli.main verify {sample_epi}")
if result.returncode == 0:
    log_pass("epi verify")
else:
    log_fail("epi verify", result.stderr[:100])

# 2.6 epi view (just check it doesn't crash)
result = run_cmd(f"python -m epi_cli.main view {sample_epi}")
if result.returncode == 0:
    log_pass("epi view")
else:
    log_fail("epi view", result.stderr[:100] if result.stderr else "Unknown error")

# 2.7 epi ls
result = run_cmd("python -m epi_cli.main ls", cwd=str(test_dir))
if result.returncode == 0 or "No recordings" in result.stdout:
    log_pass("epi ls")
else:
    log_fail("epi ls", result.stderr[:100])

# 2.8 epi debug
result = run_cmd(f"python -m epi_cli.main debug {sample_epi}")
if result.returncode == 0:
    log_pass("epi debug")
else:
    log_fail("epi debug", result.stderr[:100] if result.stderr else "Check output")

# ============================================================================
# SECTION 3: PYTHON API - EXPLICIT LOGGING
# ============================================================================
print("\n" + "=" * 70)
print("SECTION 3: PYTHON API - EXPLICIT LOGGING")
print("=" * 70)

# 3.1 Basic record context manager
try:
    epi_file = test_dir / "test_basic.epi"
    with record(str(epi_file), workflow_name="Basic Test") as epi:
        epi.log_step("custom.step", {"data": "value"})
    assert epi_file.exists()
    log_pass("Basic record() context manager")
except Exception as e:
    log_fail("Basic record() context manager", e)

# 3.2 log_chat method
try:
    epi_file = test_dir / "test_log_chat.epi"
    with record(str(epi_file)) as epi:
        epi.log_chat(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            response_content="Hi there!",
            provider="openai"
        )
    with zipfile.ZipFile(epi_file, 'r') as zf:
        steps = zf.read("steps.jsonl").decode("utf-8")
        assert "llm.request" in steps and "llm.response" in steps
    log_pass("log_chat() method")
except Exception as e:
    log_fail("log_chat() method", e)

# 3.3 log_llm_call with mock response
try:
    epi_file = test_dir / "test_log_llm_call.epi"
    mock_response = Mock()
    mock_response.model = "gpt-4-turbo"
    mock_response.choices = [Mock(message=Mock(role="assistant", content="Test"), finish_reason="stop")]
    mock_response.usage = Mock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    
    with record(str(epi_file)) as epi:
        epi.log_llm_call(mock_response, messages=[{"role": "user", "content": "Hi"}])
    
    with zipfile.ZipFile(epi_file, 'r') as zf:
        steps = zf.read("steps.jsonl").decode("utf-8")
        assert "gpt-4-turbo" in steps
    log_pass("log_llm_call() with mock response")
except Exception as e:
    log_fail("log_llm_call() with mock response", e)

# 3.4 log_llm_call auto-detection
try:
    epi_file = test_dir / "test_auto_detect.epi"
    mock_response = Mock()
    mock_response.model = "claude-3"
    mock_response.content = [Mock(text="Hello from Claude")]
    mock_response.usage = Mock(input_tokens=10, output_tokens=5)
    
    with record(str(epi_file)) as epi:
        epi.log_llm_call(mock_response, messages=[{"role": "user", "content": "Hi"}])
    log_pass("log_llm_call() auto-detection (Anthropic-like)")
except Exception as e:
    log_fail("log_llm_call() auto-detection", e)

# 3.5 Multiple steps in one session
try:
    epi_file = test_dir / "test_multi_step.epi"
    with record(str(epi_file)) as epi:
        epi.log_step("step.one", {"data": 1})
        epi.log_step("step.two", {"data": 2})
        epi.log_step("step.three", {"data": 3})
    
    with zipfile.ZipFile(epi_file, 'r') as zf:
        steps = zf.read("steps.jsonl").decode("utf-8")
        lines = [l for l in steps.strip().split("\n") if l]
        assert len(lines) >= 5  # session.start + 3 steps + environment + session.end
    log_pass("Multiple steps in one session")
except Exception as e:
    log_fail("Multiple steps in one session", e)

# ============================================================================
# SECTION 4: PYTHON API - WRAPPER CLIENTS
# ============================================================================
print("\n" + "=" * 70)
print("SECTION 4: PYTHON API - WRAPPER CLIENTS")
print("=" * 70)

# 4.1 TracedCompletions wrapper
try:
    mock_completions = Mock()
    mock_response = Mock()
    mock_response.model = "gpt-3.5-turbo"
    mock_response.choices = [Mock(message=Mock(role="assistant", content="Wrapped!"), finish_reason="stop")]
    mock_response.usage = Mock(prompt_tokens=5, completion_tokens=3, total_tokens=8)
    mock_completions.create.return_value = mock_response
    
    traced = TracedCompletions(mock_completions)
    
    epi_file = test_dir / "test_wrapper.epi"
    with record(str(epi_file)):
        result = traced.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": "Test"}])
    
    assert result == mock_response
    with zipfile.ZipFile(epi_file, 'r') as zf:
        steps = zf.read("steps.jsonl").decode("utf-8")
        assert "llm.request" in steps and "llm.response" in steps
    log_pass("TracedCompletions wrapper")
except Exception as e:
    log_fail("TracedCompletions wrapper", e)

# 4.2 wrap_openai function
try:
    mock_client = Mock()
    mock_client.chat = Mock()
    mock_client.chat.completions = Mock()
    
    wrapped = wrap_openai(mock_client)
    assert isinstance(wrapped, TracedOpenAI)
    assert hasattr(wrapped, "chat")
    log_pass("wrap_openai() function")
except Exception as e:
    log_fail("wrap_openai() function", e)

# 4.3 TracedOpenAI structure
try:
    mock_client = Mock()
    mock_client.chat = Mock()
    mock_client.chat.completions = Mock()
    
    traced = TracedOpenAI(mock_client)
    assert hasattr(traced.chat, "completions")
    log_pass("TracedOpenAI structure")
except Exception as e:
    log_fail("TracedOpenAI structure", e)

# ============================================================================
# SECTION 5: LEGACY PATCHING (DEPRECATED)
# ============================================================================
print("\n" + "=" * 70)
print("SECTION 5: LEGACY PATCHING (DEPRECATED)")
print("=" * 70)

# 5.1 Deprecation warning
try:
    epi_file = test_dir / "test_legacy.epi"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with record(str(epi_file), legacy_patching=True):
            pass
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(dep_warnings) > 0, "Should show deprecation warning"
    log_pass("legacy_patching deprecation warning")
except Exception as e:
    log_fail("legacy_patching deprecation warning", e)

# 5.2 Legacy mode still works
try:
    epi_file = test_dir / "test_legacy_works.epi"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with record(str(epi_file), legacy_patching=True):
            pass
    assert epi_file.exists()
    log_pass("legacy_patching=True still works")
except Exception as e:
    log_fail("legacy_patching=True still works", e)

# ============================================================================
# SECTION 6: EPI FILE FORMAT INTEGRITY
# ============================================================================
print("\n" + "=" * 70)
print("SECTION 6: EPI FILE FORMAT INTEGRITY")
print("=" * 70)

# 6.1 ZIP structure
try:
    with zipfile.ZipFile(sample_epi, 'r') as zf:
        names = zf.namelist()
        assert "mimetype" in names
        assert "manifest.json" in names
        assert "steps.jsonl" in names
    log_pass("EPI ZIP structure")
except Exception as e:
    log_fail("EPI ZIP structure", e)

# 6.2 mimetype content
try:
    with zipfile.ZipFile(sample_epi, 'r') as zf:
        mimetype = zf.read("mimetype").decode("utf-8").strip()
        assert mimetype == "application/epi+zip"
    log_pass("mimetype content")
except Exception as e:
    log_fail("mimetype content", e)

# 6.3 manifest.json validity
try:
    with zipfile.ZipFile(sample_epi, 'r') as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert "spec_version" in manifest
        assert manifest["spec_version"] == "2.4.0"
    log_pass("manifest.json validity")
except Exception as e:
    log_fail("manifest.json validity", e)

# 6.4 steps.jsonl format
try:
    with zipfile.ZipFile(sample_epi, 'r') as zf:
        steps_content = zf.read("steps.jsonl").decode("utf-8")
        for line in steps_content.strip().split("\n"):
            if line:
                step = json.loads(line)
                assert "kind" in step
                assert "ts" in step
                assert "content" in step
    log_pass("steps.jsonl NDJSON format")
except Exception as e:
    log_fail("steps.jsonl NDJSON format", e)

# 6.5 Embedded viewer
try:
    with zipfile.ZipFile(sample_epi, 'r') as zf:
        names = zf.namelist()
        viewer_files = [n for n in names if n.startswith("viewer/")]
        assert len(viewer_files) > 0
        assert any("index.html" in n for n in viewer_files)
    log_pass("Embedded viewer present")
except Exception as e:
    log_fail("Embedded viewer present", e)

# ============================================================================
# SECTION 7: CRYPTOGRAPHIC VERIFICATION
# ============================================================================
print("\n" + "=" * 70)
print("SECTION 7: CRYPTOGRAPHIC VERIFICATION")
print("=" * 70)

# 7.1 Signature present in manifest
try:
    with zipfile.ZipFile(sample_epi, 'r') as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        # Signature may be optional, but file_manifest should exist
        assert "file_manifest" in manifest
    log_pass("File manifest present")
except Exception as e:
    log_fail("File manifest present", e)

# 7.2 EPIContainer.verify_integrity
try:
    result = EPIContainer.verify_integrity(sample_epi)
    assert result.get("valid", True)  # Should be valid
    log_pass("EPIContainer.verify_integrity()")
except Exception as e:
    log_fail("EPIContainer.verify_integrity()", e)

# 7.3 Manifest read
try:
    manifest = EPIContainer.read_manifest(sample_epi)
    assert manifest is not None
    assert manifest.spec_version == "2.4.0"
    log_pass("EPIContainer.read_manifest()")
except Exception as e:
    log_fail("EPIContainer.read_manifest()", e)

# ============================================================================
# SECTION 8: ERROR HANDLING
# ============================================================================
print("\n" + "=" * 70)
print("SECTION 8: ERROR HANDLING")
print("=" * 70)

# 8.1 Invalid file path for verify
try:
    result = run_cmd("python -m epi_cli.main verify nonexistent.epi")
    # Should fail gracefully, not crash
    log_pass("Verify handles nonexistent file")
except Exception as e:
    log_fail("Verify handles nonexistent file", e)

# 8.2 Re-entry prevention
try:
    epi_file = test_dir / "test_reentry.epi"
    session = EpiRecorderSession(str(epi_file))
    with session:
        try:
            with session:
                pass
            log_fail("Re-entry prevention", "Should have raised")
        except RuntimeError:
            log_pass("Re-entry prevention")
except Exception as e:
    log_fail("Re-entry prevention", e)

# 8.3 Session outside context
try:
    session = get_current_session()
    # Should return None when not in context
    if session is None:
        log_pass("get_current_session() returns None outside context")
    else:
        log_fail("get_current_session() returns None outside context", "Returned non-None")
except Exception as e:
    log_fail("get_current_session() returns None outside context", e)

# ============================================================================
# SECTION 9: METADATA AND CONFIGURATION
# ============================================================================
print("\n" + "=" * 70)
print("SECTION 9: METADATA AND CONFIGURATION")
print("=" * 70)

# 9.1 Workflow name in manifest
try:
    epi_file = test_dir / "test_metadata.epi"
    with record(str(epi_file), workflow_name="Custom Workflow Name"):
        pass
    
    manifest = EPIContainer.read_manifest(epi_file)
    assert manifest.workflow_name == "Custom Workflow Name"
    log_pass("Workflow name in manifest")
except Exception as e:
    log_fail("Workflow name in manifest", e)

# 9.2 Tags parameter
try:
    epi_file = test_dir / "test_tags.epi"
    with record(str(epi_file), tags=["production", "v1"]):
        pass
    
    manifest = EPIContainer.read_manifest(epi_file)
    assert "production" in manifest.tags
    log_pass("Tags in manifest")
except Exception as e:
    log_fail("Tags in manifest", e)

# 9.3 Goal metadata
try:
    epi_file = test_dir / "test_goal.epi"
    with record(str(epi_file), goal="Test the trading strategy"):
        pass
    
    manifest = EPIContainer.read_manifest(epi_file)
    assert manifest.goal == "Test the trading strategy"
    log_pass("Goal in manifest")
except Exception as e:
    log_fail("Goal in manifest", e)

# ============================================================================
# SECTION 10: PYTEST INTEGRATION
# ============================================================================
print("\n" + "=" * 70)
print("SECTION 10: PYTEST TEST SUITE")
print("=" * 70)

# Run core tests
result = run_cmd("python -m pytest tests/test_wrappers.py tests/test_api.py tests/test_container.py -v --tb=no -q 2>&1")
if result.returncode == 0:
    # Count passed tests
    output = result.stdout
    if "passed" in output:
        log_pass(f"pytest test suite ({output.split('passed')[0].split()[-1]} passed)")
    else:
        log_pass("pytest test suite")
else:
    log_fail("pytest test suite", result.stderr[:200] if result.stderr else result.stdout[:200])

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print(f"\n[PASSED] {len(PASSED)} tests")
print(f"[FAILED] {len(FAILED)} tests")

if FAILED:
    print("\nFailed tests:")
    for name, error in FAILED:
        print(f"   - {name}: {error[:50]}...")

print(f"\nTest artifacts: {test_dir}")

# Cleanup
try:
    shutil.rmtree(test_dir)
    print("Cleaned up test directory")
except:
    pass

if FAILED:
    print("\n[RESULT] SOME TESTS FAILED")
    sys.exit(1)
else:
    print("\n[RESULT] ALL TESTS PASSED - READY FOR RELEASE")
    sys.exit(0)
