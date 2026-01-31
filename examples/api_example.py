"""
EPI Recorder Python API Example

Demonstrates how to use the Python library API for recording AI workflows.
"""

from pathlib import Path
from epi_recorder.api import EpiRecorderSession, record

# Example 1: Basic usage with context manager
print("=" * 60)
print("Example 1: Basic Recording")
print("=" * 60)

with EpiRecorderSession("example_basic.epi", workflow_name="Basic Demo") as epi:
    print("📹 Recording started...")
    
    # Your AI workflow code here
    # This would normally include OpenAI calls, etc.
    
    # Manual logging
    epi.log_step("calculation.start", {
        "operation": "factorial",
        "input": 5
    })
    
    result = 120  # factorial(5)
    
    epi.log_step("calculation.complete", {
        "operation": "factorial",
        "input": 5,
        "result": result
    })
    
    print(f"✅ Calculation result: {result}")
    print("📦 Recording stopped, .epi file created!")

print()

# Example 2: With artifact capture
print("=" * 60)
print("Example 2: With Artifact Capture")
print("=" * 60)

with record("example_with_artifacts.epi", workflow_name="Artifacts Demo") as epi:
    print("📹 Recording with artifacts...")
    
    # Create a sample output file
    output_file = Path("sample_output.txt")
    output_file.write_text("This is a generated artifact!\n")
    
    # Log the artifact
    epi.log_artifact(output_file)
    print(f"📎 Artifact captured: {output_file}")
    
    # Clean up
    output_file.unlink()
    
    print("📦 Recording complete with artifacts!")

print()

# Example 3: With custom tags
print("=" * 60)
print("Example 3: With Tags and Metadata")
print("=" * 60)

with EpiRecorderSession(
    "example_tagged.epi",
    workflow_name="Tagged Demo",
    tags=["experiment", "demo", "v1.0"],
    auto_sign=True,
    redact=True
) as epi:
    print("📹 Recording with tags...")
    
    # Log multiple steps
    for i in range(3):
        epi.log_step("iteration.step", {
            "iteration": i,
            "status": "processing",
            "data": f"Step {i} data"
        })
        print(f"  Step {i} logged")
    
    print("📦 Recording complete with tags!")

print()

# Example 4: Error handling
print("=" * 60)
print("Example 4: Error Handling")
print("=" * 60)

try:
    with record("example_with_error.epi", workflow_name="Error Demo") as epi:
        print("📹 Recording (will encounter error)...")
        
        epi.log_step("process.start", {"status": "ok"})
        
        # Simulate an error
        raise ValueError("Example error for demonstration")
        
except ValueError as e:
    print(f"❌ Error caught: {e}")
    print("📦 Recording saved despite error!")

print()

# Example 5: Manual LLM logging (for custom integrations)
print("=" * 60)
print("Example 5: Manual LLM Logging")
print("=" * 60)

with record("example_manual_llm.epi", workflow_name="Manual LLM Demo") as epi:
    print("📹 Recording manual LLM calls...")
    
    # Simulate an LLM request (without actually calling API)
    epi.log_llm_request("gpt-4", {
        "messages": [
            {"role": "user", "content": "What is 2+2?"}
        ],
        "temperature": 0.7
    })
    
    # Simulate response
    epi.log_llm_response({
        "model": "gpt-4",
        "content": "2 + 2 equals 4.",
        "tokens": 15,
        "finish_reason": "stop"
    })
    
    print("✅ Manual LLM interaction logged!")

print()
print("=" * 60)
print("✨ All examples complete!")
print("=" * 60)
print()
print("Created .epi files:")
print("  • example_basic.epi")
print("  • example_with_artifacts.epi")
print("  • example_tagged.epi")
print("  • example_with_error.epi")
print("  • example_manual_llm.epi")
print()
print("Verify them with:")
print("  python -m epi_cli.main verify example_basic.epi")
print()
print("View them with:")
print("  python -m epi_cli.main view example_basic.epi")


