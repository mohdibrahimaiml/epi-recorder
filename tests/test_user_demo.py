"""
Test script to demo epi-recorder as a normal user would use it.
"""
import time
from pathlib import Path

def simulate_ai_workflow():
    """Simulate a typical AI workflow that would be recorded."""
    print("Starting AI workflow simulation...")
    
    # Simulate some processing
    data = {"input": "test data", "model": "gpt-4"}
    
    # Simulate AI response
    time.sleep(0.5)
    result = {"output": "AI generated response", "tokens": 150}
    
    print(f"Processed: {data}")
    print(f"Result: {result}")
    
    # Create an output file
    output_file = Path("demo_output.txt")
    output_file.write_text("This is demo output from the AI workflow.")
    print(f"Created output file: {output_file}")
    
    return result

if __name__ == "__main__":
    result = simulate_ai_workflow()
    print(f"\nWorkflow completed successfully!")
    print(f"Final result: {result}")


