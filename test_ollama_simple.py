"""
Simple Ollama + EPI Integration Test (No Emoji Edition)

Tests that Ollama deepseek-r1:7b works with EPI recorder.
"""

from openai import OpenAI
from epi_recorder import record, wrap_openai
import sys

def test_ollama_basic():
    """Basic Ollama + EPI test"""
    
    print("=" * 70)
    print("OLLAMA + EPI RECORDER INTEGRATION TEST")
    print("=" * 70)
    print()
    
    print("[1] Setting up Ollama client (OpenAI-compatible)...")
    
    # Create Ollama client
    client = wrap_openai(OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama"  # Doesn't matter for local
    ))
    
    print("[2] Creating EPI recording session...")
    
    try:
        with record("ollama_test.epi", goal="Test Ollama integration") as epi:
            print("[3] Sending request to DeepSeek-R1...")
            
            response = client.chat.completions.create(
                model="deepseek-r1:7b",
                messages=[
                    {"role": "user", "content": "Write a haiku about Python programming"}
                ],
                temperature=0.7
            )
            
            content = response.choices[0].message.content
            print()
            print("DeepSeek-R1 response:")
            print("-" * 70)
            print(content)
            print("-" * 70)
            print()
            
            # Log custom metadata
            epi.log_step("custom.test", {
                "test_type": "ollama_integration",
                "model": "deepseek-r1:7b",
                "success": True,
                "provider": "ollama"
            })
        
        print("[4] SUCCESS! .epi file created")
        print()
        print("File location: epi-recordings/ollama_test.epi")
        print()
        print("Verify with:")
        print("  epi verify epi-recordings/ollama_test.epi")
        print("  epi view epi-recordings/ollama_test.epi")
        print()
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        print()
        print("Troubleshooting:")
        print("  1. Check Ollama is running: ollama serve")
        print("  2. Verify model exists: ollama list")
        print("  3. Test model: ollama run deepseek-r1:7b \"hello\"")
        print()
        import traceback
        traceback.print_exc()
        return False

def generate_test_data():
    """Generate 5 test .epi files using Ollama (FREE!)"""
    
    print()
    print("=" * 70)
    print("GENERATING TEST DATA FOR ANALYTICS")
    print("=" * 70)
    print()
    
    client = wrap_openai(OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama"
    ))
    
    prompts = [
        "Explain recursion in one sentence",
        "What is a closure in Python?",
        "Difference between sync and async?",
        "What are Python generators?",
        "Explain Python decorators briefly"
    ]
    
    successful = 0
    for i, prompt in enumerate(prompts):
        print(f"[{i+1}/5] Creating test_run_{i+1}.epi...")
        try:
            with record(f"test_run_{i+1}.epi", goal=f"Test query {i+1}") as epi:
                response = client.chat.completions.create(
                    model="deepseek-r1:7b",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7
                )
                epi.log_step("test.completed", {"prompt": prompt})
                successful += 1
                print(f"    SUCCESS")
        except Exception as e:
            print(f"    FAILED: {e}")
    
    print()
    print(f"Generated {successful}/5 test files")
    print()
    
    if successful > 0:
        print("Now test analytics:")
        print("  python demo_analytics.py")
        print()
    
    return successful == 5

if __name__ == "__main__":
    success = test_ollama_basic()
    
    if success and "--generate-data" in sys.argv:
        generate_test_data()
    
    sys.exit(0 if success else 1)
