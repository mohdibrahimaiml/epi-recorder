"""
Systematic test of ALL epi-recorder CLI commands.
Tests each command and documents what works/fails.
"""
import subprocess
import sys
from pathlib import Path

def run_cli_command(args, description):
    """Run a CLI command and capture result."""
    cmd = [sys.executable, "-m", "epi_cli.main"] + args
    print(f"\n{'='*60}")
    print(f"TEST: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='replace'  # Handle encoding issues
        )
        
        print(f"Exit Code: {result.returncode}")
        
        if result.stdout:
            print(f"\nSTDOUT:\n{result.stdout[:500]}")  # First 500 chars
        
        if result.stderr:
            print(f"\nSTDERR:\n{result.stderr[:500]}")
        
        status = "PASS" if result.returncode == 0 else "FAIL"
        print(f"\nStatus: {status}")
        
        return {
            "command": ' '.join(args),
            "description": description,
            "exit_code": result.returncode,
            "status": status,
            "stdout_length": len(result.stdout),
            "stderr_length": len(result.stderr)
        }
        
    except subprocess.TimeoutExpired:
        print("TIMEOUT: Command took too long")
        return {
            "command": ' '.join(args),
            "description": description,
            "status": "TIMEOUT"
        }
    except Exception as e:
        print(f"ERROR: {e}")
        return {
            "command": ' '.join(args),
            "description": description,
            "status": "ERROR",
            "error": str(e)
        }

# Test results
results = []

print("="*60)
print("EPI-RECORDER CLI COMPREHENSIVE TEST")
print("="*60)

# 1. Help commands
results.append(run_cli_command(["--help"], "Main help"))
results.append(run_cli_command(["help"], "Extended help"))
results.append(run_cli_command(["version"], "Version info"))

# 2. Keys commands
results.append(run_cli_command(["keys", "list"], "List keys"))
results.append(run_cli_command(["keys", "generate", "--name", "test-key"], "Generate test key"))
results.append(run_cli_command(["keys", "export", "--name", "default"], "Export public key"))

# 3. Ls command
results.append(run_cli_command(["ls"], "List recordings"))

# 4. Verify command (need existing file)
test_epi = Path("test_recording_v1.1.epi")
if test_epi.exists():
    results.append(run_cli_command(["verify", str(test_epi)], "Verify existing .epi file"))
else:
    print(f"\nSkipping verify test - {test_epi} not found")

# 5. View command (dry run check, won't open browser)
if test_epi.exists():
    print("\nSkipping 'view' command - would open browser")
    results.append({
        "command": "view",
        "description": "View recording (skipped - would open browser)",
        "status": "SKIPPED"
    })

# 6. Run command (needs a test script)
# Create minimal test script
test_script = Path("cli_test_minimal.py")
test_script.write_text("""
print("CLI test script running...")
import time
time.sleep(0.1)
print("Done!")
""")

results.append(run_cli_command(
    ["run", str(test_script), "--no-verify", "--no-open"],
    "Run command (with test script)"
))

# Cleanup
if test_script.exists():
    test_script.unlink()

# 7. Record command (advanced)
test_script2 = Path("cli_test_record.py")
test_script2.write_text('print("Recording test")')

results.append(run_cli_command(
    ["record", "--out", "cli_test_output.epi", "--", "python", str(test_script2)],
    "Record command (advanced mode)"
))

# Cleanup
if test_script2.exists():
    test_script2.unlink()
if Path("cli_test_output.epi").exists():
    Path("cli_test_output.epi").unlink()

# Summary
print("\n" + "="*60)
print("SUMMARY OF ALL CLI COMMANDS")
print("="*60)

passed = sum(1 for r in results if r.get("status") == "PASS")
failed = sum(1 for r in results if r.get("status") == "FAIL")
skipped = sum(1 for r in results if r.get("status") == "SKIPPED")
errors = sum(1 for r in results if r.get("status") in ["ERROR", "TIMEOUT"])

print(f"\nTotal Commands Tested: {len(results)}")
print(f"  PASSED: {passed}")
print(f"  FAILED: {failed}")
print(f"  SKIPPED: {skipped}")
print(f"  ERRORS: {errors}")

print("\nDetailed Results:")
for i, r in enumerate(results, 1):
    status_symbol = {
        "PASS": "[OK]",
        "FAIL": "[FAIL]",
        "SKIPPED": "[SKIP]",
        "ERROR": "[ERR]",
        "TIMEOUT": "[TIME]"
    }.get(r.get("status"), "[?]")
    
    print(f"{i:2}. {status_symbol} {r['description']}")
    if r.get("status") == "FAIL":
        print(f"     Exit code: {r.get('exit_code')}")

print("\n" + "="*60)
print("CLI TEST COMPLETE")
print("="*60)


