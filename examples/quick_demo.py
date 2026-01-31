#!/usr/bin/env python3
"""
Quick demo of EPI Recorder - from recording to viewing in 30 seconds
"""

from epi_recorder import record
from pathlib import Path
import time

def quick_demo():
    """Run a quick demo of EPI Recorder"""
    print("🚀 Quick EPI Recorder Demo")
    print("=" * 30)
    
    # Record a simple workflow
    with record("quick_demo.epi", workflow_name="Quick Demo") as epi:
        print("1. Recording started...")
        
        # Simulate some AI work
        epi.log_step("data.loading", {
            "dataset": "sample.csv",
            "rows": 1000
        })
        print("2. Data loaded")
        
        # Simulate processing
        time.sleep(0.5)
        epi.log_step("model.training", {
            "model": "neural_network",
            "accuracy": 0.92
        })
        print("3. Model trained (92% accuracy)")
        
        # Create an artifact
        results_file = Path("results.txt")
        with open(results_file, "w") as f:
            f.write("Demo Results\nAccuracy: 92%\n")
        epi.log_artifact(results_file)
        print("4. Results saved")
        
        # Simulate LLM call
        epi.log_llm_request("gpt-3.5-turbo", {
            "messages": [{"role": "user", "content": "Summarize results"}]
        })
        epi.log_llm_response({
            "model": "gpt-3.5-turbo",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Model achieved 92% accuracy on test data."
                },
                "finish_reason": "stop"
            }]
        })
        print("5. LLM call recorded")
    
    print("\n✅ Demo complete! Created: quick_demo.epi")
    print("\n📋 To verify:")
    print("   python -m epi_cli.main verify quick_demo.epi")
    print("\n🌐 To view:")
    print("   python -m epi_cli.main view quick_demo.epi")
    print("\nThis demonstrates:")
    print("  • Automatic recording of steps")
    print("  • LLM API call capture")
    print("  • File artifact logging")
    print("  • Cryptographic signing")
    print("  • Verification and viewing")

if __name__ == "__main__":
    quick_demo()


