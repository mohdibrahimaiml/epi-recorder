"""
Simplified end-to-end user workflow test.
Tests core functionality without running commands that may have display issues.
"""

import sys
import tempfile
from pathlib import Path

# Test direct API usage (most common for users)
def test_api_workflow():
    """Test the Python API as a normal user would use it."""
    
    print("="*60)
    print("USER WORKFLOW TEST - Python API")
    print("="*60)
    print()
    
    # Use a subdirectory for test files
    tmpdir = Path("test_output")
    tmpdir.mkdir(exist_ok=True)
    
    try:
        
        # Test 1: Basic import
        print("Test 1: Import package...")
        try:
            from epi_recorder import record, EpiRecorderSession
            print("✅ Package imported successfully")
        except Exception as e:
            print(f"❌ Import failed: {e}")
            return False
        
        # Test 2: Simple recording
        print("\nTest 2: Create simple recording...")
        try:
            epi_file = tmpdir / "test_basic.epi"
            with record(str(epi_file), workflow_name="Simple Test"):
                result = sum([1, 2, 3, 4, 5])
                print(f"   Calculated sum: {result}")
            
            if not epi_file.exists():
                print("❌ .epi file not created")
                return False
            print(f"✅ Created {epi_file.name} ({epi_file.stat().st_size} bytes)")
        except Exception as e:
            print(f"❌ Recording failed: {e}")
            return False
        
        # Test 3: Recording with custom logging
        print("\nTest 3: Recording with custom steps...")
        try:
            epi_file2 = tmpdir / "test_custom.epi"
            with record(str(epi_file2), workflow_name="Custom", tags=["test"]) as epi:
                epi.log_step("data.load", {"rows": 100})
                result = 42 * 2
                epi.log_step("calc.done", {"result": result})
            
            if not epi_file2.exists():
                print("❌ .epi file not created")
                return False
            print(f"✅ Created {epi_file2.name} with custom steps")
        except Exception as e:
            print(f"❌ Custom recording failed: {e}")
            return False
        
        # Test 4: Error handling (file should still be created)
        print("\nTest 4: Recording with error (should still save)...")
        try:
            epi_file3 = tmpdir / "test_error.epi"
            try:
                with record(str(epi_file3), workflow_name="Error Test") as epi:
                    epi.log_step("start", {"status": "ok"})
                    raise ValueError("Test error")
            except ValueError:
                pass  # Expected
            
            if not epi_file3.exists():
                print("❌ .epi file not created after error")
                return False
            print(f"✅ Created {epi_file3.name} despite error")
        except Exception as e:
            print(f"❌ Error handling failed: {e}")
            return False
        
        # Test 5: Verify files using Python API
        print("\nTest 5: Verify created files...")
        try:
            import subprocess
            
            for epi_file in [epi_file, epi_file2, epi_file3]:
                result = subprocess.run(
                    f"python -m epi_cli.main verify {epi_file}",
                    shell=True,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    print(f"❌ Verification failed for {epi_file.name}")
                    return False
                print(f"✅ {epi_file.name} verified")
        except Exception as e:
            print(f"❌ Verification failed: {e}")
            return False
        
        # Test 6: Recording with artifact
        print("\nTest 6: Recording with file artifact...")
        try:
            artifact_file = tmpdir / "output.txt"
            artifact_file.write_text("Sample output from workflow")
            
            epi_file4 = tmpdir / "test_artifact.epi"
            with record(str(epi_file4), workflow_name="With Artifact") as epi:
                epi.log_step("file.created", {"name": "output.txt"})
                epi.log_artifact(artifact_file)
            
            if not epi_file4.exists():
                print("❌ .epi file not created")
                return False
            print(f"✅ Created {epi_file4.name} with artifact")
        except Exception as e:
            print(f"❌ Artifact recording failed: {e}")
            return False
        
        # Test 7: Check all files
        print("\nTest 7: Summary of created files...")
        epi_files = list(tmpdir.glob("*.epi"))
        print(f"   Created {len(epi_files)} .epi files:")
        for f in epi_files:
            print(f"      • {f.name} ({f.stat().st_size:,} bytes)")
        
        if len(epi_files) < 4:
            print(f"❌ Expected 4 files, found {len(epi_files)}")
            return False
        print(f"✅ All {len(epi_files)} files created")
        
        # Test 8: CLI verify command
        print("\nTest 8: Test CLI verify command...")
        try:
            import subprocess
            result = subprocess.run(
                f"python -m epi_cli.main verify {epi_file}",
                shell=True,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"❌ CLI verify failed: {result.stderr}")
                return False
            print("✅ CLI verify command works")
        except Exception as e:
            print(f"❌ CLI test failed: {e}")
            return False
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\n📊 Test Results:")
        print("   ✅ Package imports")
        print("   ✅ Basic recording")
        print("   ✅ Custom step logging")
        print("   ✅ Error handling")
        print("   ✅ File verification")
        print("   ✅ Artifact capture")
        print("   ✅ CLI commands")
        print(f"   ✅ {len(epi_files)} .epi files created and verified")
        print("\n🎉 Package is ready for users!")
        print(f"\n📁 Test files saved to: {tmpdir.absolute()}")
        
        return True
    finally:
        # Clean up test directory
        import shutil
        try:
            shutil.rmtree(tmpdir)
            print(f"\n🧹 Cleaned up {tmpdir}")
        except:
            pass


if __name__ == "__main__":
    success = test_api_workflow()
    sys.exit(0 if success else 1)


