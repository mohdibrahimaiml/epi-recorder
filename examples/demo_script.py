"""
Demo script for 60-second EPI Recorder demo
"""

print("🚀 EPI Recorder Demo")
print("=" * 30)

# Simulate AI workflow
data = list(range(1000))
processed = [x * 2 for x in data if x % 2 == 0]
result = sum(processed)

print(f"📊 Processed {len(processed)} items")
print(f"📈 Result: {result}")

# Simulate LLM call (this would be auto-captured in real usage)
print("🤖 Simulating LLM call...")
print("   Prompt: Analyze the data processing results")
print("   Response: The processing shows a 2x improvement in efficiency")

print("✅ Demo completed!")