"""
Test async support for EPI Recorder

Validates that EPIRecorderSession works with both sync and async contexts.
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from epi_recorder import record

async def test_async_basic():
    """Test basic async context manager"""
    print("Test 1: Basic async context manager")
    print("-" * 60)
    
    try:
        async with record("test_async_basic.epi", goal="Test async") as epi:
            print("  Inside async context")
            await epi.alog_step("custom.test", {"data": "async test"})
            print("  Logged async step")
            await asyncio.sleep(0.1)
            print("  Simulated async work")
        
        print("  SUCCESS: Async context exited cleanly")
        
        # Verify file exists
        if Path("epi-recordings/test_async_basic.epi").exists():
            print("  SUCCESS: .epi file created")
            return True
        else:
            print("  ERROR: .epi file not found")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_async_with_exception():
    """Test async context manager handles exceptions"""
    print("\nTest 2: Async exception handling")
    print("-" * 60)
    
    try:
        async with record("test_async_error.epi", goal="Test error handling") as epi:
            print("  Inside async context")
            await epi.alog_step("custom.before_error", {"status": "ok"})
            print("  Logged step before error")
            raise ValueError("Intentional test error")
    except ValueError:
        print("  SUCCESS: Exception handled correctly")
        
        # Verify file exists with error logged
        if Path("epi-recordings/test_async_error.epi").exists():
            print("  SUCCESS: .epi file created despite error")
            return True
        else:
            print("  ERROR: .epi file not found after error")
            return False

async def test_async_concurrent():
    """Test multiple concurrent async recordings"""
    print("\nTest 3: Concurrent async recordings")
    print("-" * 60)
    
    async def create_recording(i):
        async with record(f"test_async_concurrent_{i}.epi", goal=f"Concurrent {i}") as epi:
            await epi.alog_step("concurrent.start", {"id": i})
            await asyncio.sleep(0.1)
            await epi.alog_step("concurrent.end", {"id": i})
        return i
    
    try:
        # Run 5 recordings concurrently
        results = await asyncio.gather(*[create_recording(i) for i in range(5)])
        
        print(f"  Completed {len(results)} concurrent recordings")
        
        # Verify all files exist
        for i in range(5):
            if not Path(f"epi-recordings/test_async_concurrent_{i}.epi").exists():
                print(f"  ERROR: File {i} not found")
                return False
        
        print("  SUCCESS: All concurrent recordings created")
        return True
        
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_sync_compatibility():
    """Test that sync context manager still works"""
    print("\nTest 4: Sync mode compatibility")
    print("-" * 60)
    
    try:
        with record("test_sync_compat.epi", goal="Test sync compatibility") as epi:
            print("  Inside sync context")
            epi.log_step("custom.sync", {"mode": "sync"})
            print("  Logged sync step")
        
        print("  SUCCESS: Sync context works")
        
        if Path("epi-recordings/test_sync_compat.epi").exists():
            print("  SUCCESS: Sync .epi file created")
            return True
        else:
            print("  ERROR: Sync .epi file not found")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

async def run_all_tests():
    """Run all async tests"""
    print("=" * 70)
    print("EPI RECORDER - ASYNC SUPPORT TEST SUITE")
    print("=" * 70)
    print()
    
    results = []
    
    # Test 1: Basic async
    results.append(await test_async_basic())
    
    # Test 2: Async with exception
    results.append(await test_async_with_exception())
    
    # Test 3: Concurrent
    results.append(await test_async_concurrent())
    
    # Test 4: Sync compatibility (run synchronously)
    results.append(test_sync_compatibility())
    
    print()
    print("=" * 70)
    
    if all(results):
        print("ALL TESTS PASSED - ASYNC SUPPORT WORKING PERFECTLY")
        print("=" * 70)
        print()
        print("Both sync and async modes are production-ready!")
        print()
        print("Usage examples:")
        print()
        print("  # Sync mode (existing code still works)")
        print("  with record('sync.epi'):")
        print("      pass")
        print()
        print("  # Async mode (new!)")
        print("  async with record('async.epi'):")
        print("      await agent.run()")
        print()
        return 0
    else:
        print("SOME TESTS FAILED")
        print("=" * 70)
        failed = sum(1 for r in results if not r)
        print(f"Failed: {failed}/{len(results)} tests")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
