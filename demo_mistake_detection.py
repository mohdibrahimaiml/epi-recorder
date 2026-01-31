#!/usr/bin/env python3
"""
Demo: EPI Mistake Detection

Demonstrates how EPI automatically finds common agent bugs.
This simulates a buggy agent that gets stuck in a loop.
"""

import time
import json
from pathlib import Path
from epi_recorder.patcher import RecordingContext, set_recording_context
from epi_core.schemas import StepModel
from datetime import datetime


def create_buggy_recording():
    """Create a simulated recording with a loop bug"""
    output_dir = Path("./demo_buggy_agent")
    output_dir.mkdir(exist_ok=True)
    
    # Create recording context
    context = RecordingContext(output_dir, enable_redaction=False)
    set_recording_context(context)
    
    print("🎬 Simulating buggy agent execution...\n")
    
    # Simulate normal steps
    print("Step 1: Agent starts task")
    context.add_step("llm.request", {
        "provider": "openai",
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "Calculate 10/0"}]
    })
    
    context.add_step("llm.response", {
        "provider": "openai",
        "model": "gpt-4",
        "choices": [{
            "message": {"role": "assistant", "content": "I'll use the calculator tool"},
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}
    })
    
    # Simulate infinite loop - same error repeated
    for i in range(5):
        print(f"Step {i+2}: Calling calculator (ERROR #{i+1})")
        
        context.add_step("llm.request", {
            "provider": "openai",
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Try calculator again for 10/0"}]
        })
        
        context.add_step("llm.response", {
            "provider": "openai",
            "model": "gpt-4",
            "choices": [{
                "message": {"role": "assistant", "content": f"Let me retry the calculator (attempt {i+1})"},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
        })
        
        context.add_step("llm.error", {
            "provider": "tool",
            "error": "Division by zero error",
            "tool": "calculator"
        })
        
        time.sleep(0.1)
    
    # Finalize the recording
    if hasattr(context, 'storage'):
        final_path = context.storage.finalize()
        print(f"\n✅ Recording saved to: {output_dir}")
        return output_dir
    else:
        print(f"\n✅ Recording saved to: {output_dir}")
        return output_dir


def run_debug_analysis(recording_path):
    """Run epi debug on the recording"""
    print(f"\n🔍 Running mistake detection...\n")
    print("=" * 60)
    
    from epi_analyzer.detector import MistakeDetector
    
    detector = MistakeDetector(str(recording_path))
    mistakes = detector.analyze()
    
    summary = detector.get_summary()
    print(summary)
    print("=" * 60)
    
    return mistakes


if __name__ == "__main__":
    print("=" * 60)
    print("  EPI MISTAKE DETECTION DEMO")
    print("=" * 60)
    print()
    
    # Create the buggy recording
    recording_path = create_buggy_recording()
    
    # Analyze it
    mistakes = run_debug_analysis(recording_path)
    
    # Show results
    print(f"\n📊 Summary:")
    print(f"   Total steps recorded: ~15")
    print(f"   Mistakes found: {len(mistakes)}")
    
    if mistakes:
        print(f"\n🎯 EPI detected the following issues:")
        for m in mistakes:
            print(f"   - {m['type']}: {m['explanation']}")
    
    print(f"\n💡 Try it yourself:")
    print(f"   epi debug {recording_path}")
    print()


