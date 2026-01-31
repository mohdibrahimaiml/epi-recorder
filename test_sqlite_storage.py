"""Test Suite 2: SQLite Storage Integrity"""
import tempfile
import json
from pathlib import Path
from epi_core.storage import EpiStorage
from epi_core.schemas import StepModel
from datetime import datetime

def test_atomic_storage():
    print("Testing SQLite storage...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test 1: Basic write
        storage = EpiStorage("test_session", Path(tmpdir))
        
        step1 = StepModel(
            index=0,
            timestamp=datetime.now(),
            kind='llm.request',
            content={'prompt': 'hello', 'response': 'hi'}
        )
        step2 = StepModel(
            index=1,
            timestamp=datetime.now(),
            kind='tool',
            content={'name': 'calc', 'result': '4'}
        )
        
        storage.add_step(step1)
        storage.add_step(step2)
        
        # Test 2: Read back
        steps = storage.get_steps()
        assert len(steps) == 2, f"Expected 2 steps, got {len(steps)}"
        assert steps[0].kind == 'llm.request'
        assert steps[1].kind == 'tool'
        print("  Write and read: OK")
        
        # Test 3: Finalize creates final file
        final_path = storage.finalize()
        assert final_path.exists(), f"Final file not created: {final_path}"
        print("  Finalize: OK")
        
        # Test 4: Verify JSONL output
        with open(final_path, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 2, f"Expected 2 lines in JSONL, got {len(lines)}"
        print("  JSONL export: OK")
    
    print("SQLite storage test PASSED")

if __name__ == '__main__':
    test_atomic_storage()


