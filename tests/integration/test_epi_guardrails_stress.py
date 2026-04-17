import asyncio
import threading
import time
from pathlib import Path

import pytest
pytestmark = pytest.mark.network

import os
os.environ["GUARDRAILS_TELEMETRY_ENABLED"] = "false"

try:
    import guardrails as gd
except ImportError:
    pytest.skip("Guardrails AI not installed", allow_module_level=True)

from epi_guardrails.instrumentor import instrument, uninstrument

# Enable logging to see the execution
import logging
logging.basicConfig(level=logging.INFO)

def dummy_llm_sync(*args, **kwargs):
    return "mocked LLM output"

async def dummy_llm_async(*args, **kwargs):
    await asyncio.sleep(0.01)
    return "mocked async LLM output"

def pass_validator(val: str, **kwargs):
    if "fail" in val:
        raise ValueError("Simulated failure")
    return val

@pytest.fixture(autouse=True)
def setup_instrumentation():
    instrument()
    yield
    uninstrument()

@pytest.mark.network
def test_stress_multithreaded_concurrency(tmp_path):
    """
    Test that threadpools and multiple concurrent sync Guards 
    do NOT bleed context into one another.
    """
    results = []
    def run_guard(idx):
        try:
            # Explicit session manages output
            from epi_guardrails import GuardrailsRecorderSession
            epi_path = tmp_path / f"thread_{idx}.epi"
            with GuardrailsRecorderSession(output_path=epi_path, auto_sign=False, redact=False):
                guard = gd.Guard()
                guard(dummy_llm_sync, prompt=f"thread input {idx}", messages=[{"role": "user", "content": f"thread input {idx}"}])
            results.append((idx, epi_path))
        except Exception as e:
            # Re-raise to crash thread visibly instead of hiding behind exist assertion
            raise e
            
    threads = []
    for i in range(10):
        t = threading.Thread(target=run_guard, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    # Verify 10 distinct artifacts
    import zipfile
    
    # helper for reading payload
    def extract_steps(path):
        import json
        with zipfile.ZipFile(path) as zf:
            steps_content = zf.read("steps.jsonl").decode("utf-8")
        return [json.loads(line) for line in steps_content.strip().split("\n")]
    
    assert len(results) == 10
    for idx, res in results:
        assert isinstance(res, Path), f"Thread {idx} failed with {res}"
        assert res.exists()
        steps = extract_steps(res)
        assert len(steps) > 0, "No steps recorded"
        # Ensure that no other thread's prompts got logged here
        prompts = [s for s in steps if s["kind"] == "agent.step" and s["content"].get("phase") == "start"]
        assert len(prompts) == 1
        assert prompts[0]["content"]["prompt"] == f"thread input {idx}"

@pytest.mark.network
def test_nested_guard_execution(tmp_path):
    """
    Test that an inner guard execution creates a distinct artifact
    without clobbering the parent's contextvars stack.
    """
    outer_path = tmp_path / "outer.epi"
    inner_path = tmp_path / "inner.epi"

    from epi_guardrails import GuardrailsRecorderSession

    def custom_llm(*args, **kwargs):
        inner_guard = gd.Guard()
        in_prompt = f"inner prompt from outer prompt"
        with GuardrailsRecorderSession(output_path=inner_path, auto_sign=False, redact=False):
            inner_res = inner_guard(dummy_llm_sync, prompt=in_prompt, messages=[{"role": "user", "content": in_prompt}])
        return f"outer wrapped {inner_res.validated_output}"

    outer_guard = gd.Guard()
    with GuardrailsRecorderSession(output_path=outer_path, auto_sign=False, redact=False):
        res = outer_guard(custom_llm, prompt="outer prompt", messages=[{"role": "user", "content": "outer prompt"}])

    # Assert Both were isolated and recorded
    assert outer_path.exists()
    assert inner_path.exists()
    
    import zipfile
    def extract_steps(pth):
        import json
        with zipfile.ZipFile(pth) as zf:
            steps_content = zf.read("steps.jsonl").decode("utf-8")
        return [json.loads(line) for line in steps_content.strip().split("\n")]
        
    outer_steps = extract_steps(outer_path)
    # The inner guard SHOULD NOT leak into the outer guard steps array!
    # Because inner guard should push a new state in contextvars, emit to it, pop it on exit.
    inner_calls = [s for s in outer_steps if "inner prompt" in str(s)]
    assert len(inner_calls) == 0, "State leaked! Inner execution steps found in outer EPI"

    inner_steps = extract_steps(inner_path)
    assert len(inner_steps) > 0

@pytest.mark.network
@pytest.mark.asyncio
async def test_stress_async_concurrency(tmp_path):
    """
    Ensure asyncio contextvars boundaries correctly track 
    concurrent executions.
    """
    async def run_async_guard(idx):
        from epi_guardrails import GuardrailsRecorderSession
        path = tmp_path / f"async_{idx}.epi"
        with GuardrailsRecorderSession(output_path=path, auto_sign=False, redact=False):
            guard = gd.Guard()
            # Run sync guard in threadpool to simulate concurrent isolation
            await asyncio.to_thread(
                guard, dummy_llm_sync, prompt=f"async input {idx}", messages=[{"role": "user", "content": f"async input {idx}"}]
            )
        return path

    tasks = [run_async_guard(i) for i in range(5)]
    paths = await asyncio.gather(*tasks)
    
    import zipfile
    
    # helper for reading payload
    def extract_steps(pth):
        import json
        with zipfile.ZipFile(pth) as zf:
            steps_content = zf.read("steps.jsonl").decode("utf-8")
        return [json.loads(line) for line in steps_content.strip().split("\n")]
        
    for idx, path in enumerate(paths):
        assert path.exists()
        steps = extract_steps(path)
        assert len(steps) > 0
        start_step = [s for s in steps if s["kind"] == "agent.step" and s["content"].get("phase") == "start"][0]
        assert start_step["content"]["prompt"] == f"async input {idx}"

@pytest.mark.network
def test_guard_payload_structure(tmp_path):
    """
    Verify the payload formatting rules required by Phase 1.
    """
    path = tmp_path / "schema.epi"
    guard = gd.Guard(name="TestSchemaGuard")
    
    from epi_guardrails import GuardrailsRecorderSession
    with GuardrailsRecorderSession(output_path=path, auto_sign=False, redact=False, goal="verify schema", guard_name="TestSchemaGuard"):
        guard(dummy_llm_sync, prompt="test payload", messages=[{"role": "user", "content": "test payload"}])
    
    import json
    import zipfile
    with zipfile.ZipFile(path) as zf:
        steps_content = zf.read("steps.jsonl").decode("utf-8")
    steps = [json.loads(line) for line in steps_content.strip().split("\n")]
    
    # Expect Guard Execution Start to be steps[0]
    guard_meta = steps[0]["content"]["guard"]
    
    expected_data = "TestSchemaGuard"
    assert guard_meta["name"] == expected_data
