#!/usr/bin/env python3
"""
EPI Recorder example with real OpenAI integration
"""

import os
import openai
from epi_recorder import record

def main():
    """Demonstrate EPI Recorder with real OpenAI API calls"""
    
    print("[ ] EPI Recorder with OpenAI Integration")
    print("=" * 40)
    
    # Check if OpenAI API key is available
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("⚠️  OPENAI_API_KEY not found in environment variables")
        print("   To run this example with real API calls:")
        print("   1. Set your OpenAI API key:")
        print("      export OPENAI_API_KEY='your-api-key-here'")
        print("   2. Run this script again")
        print()
        print("   For now, we'll simulate the API calls...")
        
        # Simulate the recording without real API calls
        simulate_openai_workflow()
        return
    
    # Initialize OpenAI client
    client = openai.OpenAI(api_key=api_key)
    
    # Record the workflow with EPI
    with record("openai_example.epi", workflow_name="OpenAI Chat Example") as epi:
        print("📝 Recording started...")
        
        # Log the start of our chat interaction
        epi.log_step("chat.session.start", {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7
        })
        
        # Make OpenAI API call (automatically recorded by EPI)
        print("💬 Sending message to OpenAI...")
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Explain quantum computing in simple terms."}
            ],
            temperature=0.7
        )
        
        # Log the response
        epi.log_step("chat.response.received", {
            "model": response.model,
            "response_length": len(response.choices[0].message.content),
            "finish_reason": response.choices[0].finish_reason
        })
        
        # Print the response
        print("\n[ ] OpenAI Response:")
        print("-" * 20)
        print(response.choices[0].message.content)
        
        # Log completion
        epi.log_step("chat.session.end", {
            "status": "completed",
            "total_tokens": response.usage.total_tokens if response.usage else 0
        })
    
    print("\n[ ] EPI recording completed: openai_example.epi")
    print("[ ] To verify: epi verify openai_example.epi")
    print("[ ] To view:   epi view openai_example.epi")

def simulate_openai_workflow():
    """Simulate the workflow without real API calls"""
    
    with record("openai_example.epi", workflow_name="OpenAI Chat Example") as epi:
        print("📝 Recording started...")
        
        # Log the start of our chat interaction
        epi.log_step("chat.session.start", {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7
        })
        
        # Simulate OpenAI API call
        print("💬 Simulating message to OpenAI...")
        epi.log_llm_request("gpt-3.5-turbo", {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Explain quantum computing in simple terms."}
            ],
            "temperature": 0.7
        })
        
        # Simulate response
        simulated_response = {
            "model": "gpt-3.5-turbo",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Quantum computing is a type of computing that uses quantum bits (qubits) instead of regular bits. While regular bits can be either 0 or 1, qubits can be both 0 and 1 at the same time, thanks to a property called superposition. This allows quantum computers to solve certain problems much faster than classical computers."
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 45,
                "completion_tokens": 82,
                "total_tokens": 127
            },
            "latency_seconds": 1.842
        }
        
        epi.log_llm_response(simulated_response)
        
        # Log the response
        epi.log_step("chat.response.received", {
            "model": simulated_response["model"],
            "response_length": len(simulated_response["choices"][0]["message"]["content"]),
            "finish_reason": simulated_response["choices"][0]["finish_reason"]
        })
        
        # Print the simulated response
        print("\n[ ] Simulated OpenAI Response:")
        print("-" * 30)
        print(simulated_response["choices"][0]["message"]["content"])
        
        # Log completion
        epi.log_step("chat.session.end", {
            "status": "completed",
            "total_tokens": simulated_response["usage"]["total_tokens"]
        })
    
    print("\n[ ] EPI recording completed: openai_example.epi")
    print("[ ] To verify: epi verify openai_example.epi")
    print("[ ] To view:   epi view openai_example.epi")

if __name__ == "__main__":
    main()


