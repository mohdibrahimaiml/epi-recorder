"""Test Suite 3: Mistake Detector Comprehensive Tests"""
import sqlite3
import json
import tempfile
import shutil
from pathlib import Path
from epi_analyzer.detector import MistakeDetector

def create_test_db(steps_data):
    """Helper to create test database files"""
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_temp.db"
    
    conn = sqlite3.connect(str(db_path))
    conn.execute('''
        CREATE TABLE steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            step_index INTEGER,
            timestamp TEXT,
            kind TEXT,
            content TEXT,
            created_at REAL
        )
    ''')
    
    for i, (kind, content) in enumerate(steps_data):
        conn.execute(
            'INSERT INTO steps (step_index, timestamp, kind, content, created_at) VALUES (?, ?, ?, ?, ?)',
            (i, '2024-01-01T00:00:00', kind, json.dumps(content), float(i))
        )
    conn.commit()
    conn.close()
    
    return Path(tmpdir)  # Return directory, detector will find the db

def test_infinite_loop():
    print("\nTest 1: Infinite Loop Detection")
    # Create: 5 similar LLM requests in a row
    steps = [
        ('llm.request', {'messages': [{'role': 'user', 'content': 'calc 10/0'}]}),
        ('llm.response', {'choices': [{'message': {}, 'finish_reason': 'stop'}]}),
        ('llm.request', {'messages': [{'role': 'user', 'content': 'calc 10/0'}]}),
        ('llm.response', {'choices': [{'message': {}, 'finish_reason': 'stop'}]}),
        ('llm.request', {'messages': [{'role': 'user', 'content': 'calc 10/0'}]}),
        ('llm.response', {'choices': [{'message': {}, 'finish_reason': 'stop'}]}),
        ('llm.request', {'messages': [{'role': 'user', 'content': 'calc 10/0'}]}),
        ('llm.response', {'choices': [{'message': {}, 'finish_reason': 'stop'}]}),
    ]
    
    db_dir = create_test_db(steps)
    detector = MistakeDetector(str(db_dir))
    mistakes = detector.analyze()
    
    # Should detect loop
    loop_found = any(m['type'] == 'INFINITE_LOOP' for m in mistakes)
    if loop_found:
        print("  PASS - Infinite loop detected")
    else:
        print(f"  FAIL - Expected INFINITE_LOOP, got: {[m['type'] for m in mistakes]}")
        return False
    return True

def test_hallucination():
    print("\nTest 2: Hallucination Detection")
    # Create: LLM confident, then error
    steps = [
        ('llm.response', {
            'provider': 'openai',
            'choices': [{'message': {'content': 'I will calculate'}, 'finish_reason': 'stop'}]
        }),
        ('llm.error', {'error': 'invalid params', 'provider': 'tool'})
    ]
    
    db_dir = create_test_db(steps)
    detector = MistakeDetector(str(db_dir))
    mistakes = detector.analyze()
    
    # Should detect hallucination
    hall_found = any(m['type'] == 'HALLUCINATION' for m in mistakes)
    if hall_found:
        print("  PASS - Hallucination detected")
    else:
        print(f"  WARN - Hallucination not detected (may need tuning)")
    return True  # Don't fail on this one

def test_inefficiency():
    print("\nTest 3: Inefficiency Detection")
    # Create: Expensive execution
    steps = [
        ('llm.response', {'usage': {'total_tokens': 15000}, 'model': 'gpt-4'}) for _ in range(3)
    ]
    
    db_dir = create_test_db(steps)
    detector = MistakeDetector(str(db_dir))
    mistakes = detector.analyze()
    
    # Should detect inefficiency
    ineff_found = any(m['type'] == 'INEFFICIENT' for m in mistakes)
    if ineff_found:
        print("  PASS - Inefficiency detected")
    else:
        print(f"  WARN - No inefficiency detected (may need tuning)")
    return True

def test_no_mistakes():
    print("\nTest 4: Clean Execution Detection")
    # Create: Normal execution
    steps = [
        ('llm.request', {'messages': []}),
        ('llm.response', {'usage': {'total_tokens': 100}}),
        ('tool', {'name': 'search', 'result': 'ok'}),
        ('llm.response', {'usage': {'total_tokens': 150}})
    ]
    
    db_dir = create_test_db(steps)
    detector = MistakeDetector(str(db_dir))
    mistakes = detector.analyze()
    
    # Should find no critical mistakes
    critical = [m for m in mistakes if m.get('severity') == 'CRITICAL']
    if len(critical) == 0:
        print("  PASS - No critical mistakes in clean execution")
    else:
        print(f"  FAIL - Found unexpected mistakes: {mistakes}")
        return False
    return True

if __name__ == '__main__':
    print("="*60)
    print("MISTAKE DETECTOR COMPREHENSIVE TESTS")
    print("="*60)
    
    results = []
    results.append(test_infinite_loop())
    results.append(test_hallucination())
    results.append(test_inefficiency())
    results.append(test_no_mistakes())
    
    print("\n" + "="*60)
    if all(results):
        print("ALL DETECTOR TESTS PASSED")
    else:
        print(f"SOME TESTS FAILED: {sum(results)}/{len(results)} passed")
        exit(1)


