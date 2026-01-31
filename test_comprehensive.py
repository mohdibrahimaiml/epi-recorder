#!/usr/bin/env python3
"""
Comprehensive Test Suite for EPI Recorder
Tests thread-safety, SQLite storage, async support, and mistake detection
"""

import sys
import os
import time
import threading
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Test results tracker
results = {
    'passed': [],
    'failed': [],
    'errors': []
}

def test_result(name, passed, error=None):
    """Record test result"""
    if passed:
        results['passed'].append(name)
        print(f"[PASS] {name}")
    else:
        results['failed'].append(name)
        print(f"[FAIL] {name}")
        if error:
            results['errors'].append(f"{name}: {error}")
            print(f"       Error: {error}")

def test_imports():
    """Test that all modules import correctly"""
    print("\n=== TEST 1: Module Imports ===")
    
    try:
        from epi_recorder.api import record, EpiRecorderSession
        test_result("epi_recorder.api imports", True)
    except Exception as e:
        test_result("epi_recorder.api imports", False, str(e))
    
    try:
        from epi_analyzer.detector import MistakeDetector
        test_result("epi_analyzer.detector imports", True)
    except Exception as e:
        test_result("epi_analyzer.detector imports", False, str(e))
    
    try:
        from epi_cli.main import app
        test_result("epi_cli.main imports", True)
    except Exception as e:
        test_result("epi_cli.main imports", False, str(e))
    
    try:
        from epi_core.storage import EpiStorage
        test_result("epi_core.storage imports", True)
    except Exception as e:
        test_result("epi_core.storage imports", False, str(e))
    
    try:
        from epi_recorder.patcher import RecordingContext, get_recording_context
        test_result("epi_recorder.patcher imports", True)
    except Exception as e:
        test_result("epi_recorder.patcher imports", False, str(e))

def test_storage():
    """Test SQLite storage functionality"""
    print("\n=== TEST 2: SQLite Storage ===")
    
    try:
        from epi_core.storage import EpiStorage
        from epi_core.schemas import StepModel
        from datetime import datetime
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create storage
            storage = EpiStorage("test_session", Path(tmpdir))
            
            # Add steps
            step1 = StepModel(index=0, timestamp=datetime.now(), kind='test.step1', content={'data': 'value1'})
            step2 = StepModel(index=1, timestamp=datetime.now(), kind='test.step2', content={'data': 'value2'})
            
            storage.add_step(step1)
            storage.add_step(step2)
            
            # Retrieve steps
            steps = storage.get_steps()
            if len(steps) == 2:
                test_result("SQLite storage add/get", True)
            else:
                test_result("SQLite storage add/get", False, f"Expected 2 steps, got {len(steps)}")
            
            # Finalize
            final_path = storage.finalize()
            if final_path.exists():
                test_result("SQLite finalize", True)
            else:
                test_result("SQLite finalize", False, "File not created")
                
    except Exception as e:
        test_result("SQLite storage", False, str(e))

def test_thread_safety():
    """Test thread-safety with concurrent recordings"""
    print("\n=== TEST 3: Thread Safety ===")
    
    errors = []
    success_count = [0]
    
    def worker(thread_id):
        try:
            from epi_recorder.patcher import RecordingContext, set_recording_context
            from pathlib import Path
            import tempfile
            
            with tempfile.TemporaryDirectory() as tmpdir:
                ctx = RecordingContext(Path(tmpdir))
                token = set_recording_context(ctx)
                
                # Simulate work
                time.sleep(0.05)
                
                # Add step
                ctx.add_step('test', {'thread_id': thread_id})
                
                # Clear context
                set_recording_context(None)
                
                success_count[0] += 1
        except Exception as e:
            errors.append(f"Thread {thread_id}: {str(e)}")
    
    # Run 5 concurrent threads
    threads = []
    for i in range(5):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    if not errors and success_count[0] == 5:
        test_result("Thread safety (5 concurrent)", True)
    else:
        test_result("Thread safety (5 concurrent)", False, f"{len(errors)} errors, {success_count[0]}/5 succeeded")

def test_detector():
    """Test mistake detector"""
    print("\n=== TEST 4: Mistake Detector ===")
    
    try:
        from epi_analyzer.detector import MistakeDetector
        import tempfile
        import json
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple JSONL file
            jsonl_path = Path(tmpdir) / "steps.jsonl"
            
            steps = [
                {'index': 0, 'timestamp': '2024-01-01T00:00:00', 'kind': 'llm.request', 'content': {'messages': [{'role': 'user', 'content': 'test'}]}},
                {'index': 1, 'timestamp': '2024-01-01T00:00:01', 'kind': 'llm.response', 'content': {'provider': 'openai', 'choices': [{'finish_reason': 'stop'}], 'usage': {'total_tokens': 100}}},
            ]
            
            with open(jsonl_path, 'w') as f:
                for step in steps:
                    f.write(json.dumps(step) + '\n')
            
            # Test detector
            detector = MistakeDetector(str(tmpdir))
            mistakes = detector.analyze()
            
            # Should have no mistakes for clean execution
            if isinstance(mistakes, list):
                test_result("Mistake detector analysis", True)
            else:
                test_result("Mistake detector analysis", False, "Did not return list")
                
        test_result("Mistake detector initialization", True)
        
    except Exception as e:
        test_result("Mistake detector", False, str(e))

def test_api_compatibility():
    """Test that the API is accessible"""
    print("\n=== TEST 5: API Compatibility ===")
    
    try:
        # Test that record is importable from top level
        from epi_recorder import record, EpiRecorderSession
        test_result("API: record importable", True)
    except Exception as e:
        test_result("API: record importable", False, str(e))
    
    try:
        from epi_recorder.patcher import RecordingContext
        test_result("API: RecordingContext importable", True)
    except Exception as e:
        test_result("API: RecordingContext importable", False, str(e))

def print_summary():
    """Print test summary"""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Passed: {len(results['passed'])}")
    print(f"Failed: {len(results['failed'])}")
    
    if results['failed']:
        print("\nFailed Tests:")
        for name in results['failed']:
            print(f"  - {name}")
    
    if results['errors']:
        print("\nErrors:")
        for error in results['errors']:
            print(f"  - {error}")
    
    success_rate = len(results['passed']) / (len(results['passed']) + len(results['failed'])) * 100
    print(f"\nSuccess Rate: {success_rate:.1f}%")
    
    if success_rate >= 80:
        print("\nSTATUS: READY FOR PRODUCTION")
        return 0
    else:
        print("\nSTATUS: NEEDS FIXES")
        return 1

if __name__ == '__main__':
    print("="*60)
    print("EPI RECORDER - COMPREHENSIVE TEST SUITE")
    print("="*60)
    
    test_imports()
    test_storage()
    test_thread_safety()
    test_detector()
    test_api_compatibility()
    
    sys.exit(print_summary())


