#!/usr/bin/env python3
"""EPI Recording Health Check - Windows Compatible (No Emojis)"""
import sys
import os
import json
import time

def test_basic_recording():
    """Test 1: Check if EPI can record a simple step"""
    print("=" * 60)
    print("EPI RECORDING HEALTH CHECK")
    print("=" * 60)
    
    # Check 1: Import works
    try:
        from epi_recorder import record
        from epi_recorder.patcher import get_recording_context
        print("[OK] Import successful")
    except ImportError as e:
        print(f"[FAIL] Import failed: {e}")
        return False
    
    # Check 2: Context is accessible
    print("\n--- Checking Recording Context ---")
    ctx_before = get_recording_context()
    print(f"Context before 'with record()': {ctx_before}")
    
    # Inside context manager
    with record(workflow_name="health_check") as ctx:
        ctx_inside = get_recording_context()
        print(f"Context inside 'with record()': {ctx_inside}")
        
        if ctx_inside is None:
            print("[FAIL] CRITICAL: Context is None - recording won't work!")
            return False
        
        # Check 3: Try to add a manual step
        try:
            ctx.log_step("test.manual", {"message": "Health check step"})
            print("[OK] Manual step added successfully")
        except Exception as e:
            print(f"[FAIL] Failed to add step: {e}")
            return False
    
    # Check 4: File was created
    print("\n--- Checking Output File ---")
    time.sleep(0.5)
    
    import pathlib
    recordings_dir = pathlib.Path("epi-recordings")
    if recordings_dir.exists():
        epi_files = list(recordings_dir.glob("health_check*.epi"))
        if epi_files:
            expected_file = epi_files[0]
            size = expected_file.stat().st_size
            print(f"[OK] File created: {expected_file} ({size} bytes)")
            
            try:
                import zipfile
                with zipfile.ZipFile(expected_file, 'r') as zf:
                    files = zf.namelist()
                    print(f"[OK] Valid ZIP with {len(files)} entries")
                    
                    if 'manifest.json' in files:
                        with zf.open('manifest.json') as f:
                            manifest = json.load(f)
                            print(f"[OK] Manifest: workflow_id = {manifest.get('workflow_id')}")
                            return True
                    else:
                        print("[FAIL] manifest.json not found!")
                        return False
            except Exception as e:
                print(f"[FAIL] Error reading file: {e}")
                return False
        else:
            print(f"[FAIL] No .epi files found in {recordings_dir}")
            return False
    else:
        print(f"[FAIL] Directory not found: {recordings_dir}")
        return False

def diagnose_common_issues():
    """Check for common configuration issues"""
    print("=" * 60)
    print("DIAGNOSTICS")
    print("=" * 60)
    
    import pathlib
    home = pathlib.Path.home()
    epi_dir = home / ".epi"
    
    if epi_dir.exists():
        print(f"[OK] EPI directory exists: {epi_dir}")
        keys_dir = epi_dir / "keys"
        if keys_dir.exists():
            keys = list(keys_dir.glob("*.pem"))
            print(f"[OK] Found {len(keys)} key files")
    else:
        print(f"[WARN] EPI directory not found (will be created)")
    
    try:
        import sqlite3
        print("[OK] SQLite available")
    except ImportError:
        print("[FAIL] SQLite not available!")
    
    test_path = pathlib.Path("epi_write_test.txt")
    try:
        test_path.write_text("test")
        test_path.unlink()
        print("[OK] Write permissions OK")
    except Exception as e:
        print(f"[FAIL] Write permission issue: {e}")

if __name__ == "__main__":
    diagnose_common_issues()
    success = test_basic_recording()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if success:
        print("[OK] ALL CHECKS PASSED - EPI is recording correctly!")
        sys.exit(0)
    else:
        print("[FAIL] RECORDING NOT WORKING")
        sys.exit(1)


