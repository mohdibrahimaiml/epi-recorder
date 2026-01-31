import time

# Simulate simple agent (no actual OpenAI calls for testing)
def my_agent():
    print("Agent starting...")
    
    # Step 1: Simulated LLM call
    print("LLM call 1: Sending 'Say hello'")
    response_text = "Hello! How can I help you today?"
    print(f"LLM said: {response_text}")
    
    # Step 2: "Tool" call (simulated)
    result = {"data": "some_result"}
    print(f"Tool returned: {result}")
    
    # Step 3: Final simulated LLM
    print("LLM call 2: Sending 'Summarize'")
    summary = "Task completed successfully."
    print(f"LLM summary: {summary}")
    
    return "done"

if __name__ == "__main__":
    result = my_agent()
    print(f"Agent finished: {result}")


