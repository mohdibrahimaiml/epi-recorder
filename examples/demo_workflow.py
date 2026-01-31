#!/usr/bin/env python3
"""
Demo AI Workflow - Shows what EPI Recorder captures
"""
import json
from datetime import datetime

print("🤖 Starting AI Workflow Demo...")
print("-" * 50)

# Simulate an AI task
task = {
    "timestamp": datetime.now().isoformat(),
    "model": "gpt-4",
    "prompt": "Explain quantum computing in simple terms",
    "response": "Quantum computing uses quantum mechanics principles...",
    "tokens_used": 150,
    "cost": 0.003
}

print(f"📝 Task: {task['prompt']}")
print(f"🤖 Model: {task['model']}")
print(f"⏱️  Time: {task['timestamp']}")
print(f"💬 Response: {task['response'][:50]}...")
print(f"📊 Tokens: {task['tokens_used']}")

# Write output
output_file = "demo_output.json"
with open(output_file, "w") as f:
    json.dump(task, f, indent=2)

print(f"\n✅ Output saved to {output_file}")
print("-" * 50)
print("✨ Demo complete!")


