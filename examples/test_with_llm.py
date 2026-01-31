"""
Test script with OpenAI call to verify steps recording.
"""
import os
import openai

# Set up client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY", "test-key"))

print("Making OpenAI API call...")

try:
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Say 'Hello EPI!' in one word"}],
        max_tokens=10
    )
    print(f"Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"OpenAI call failed (expected without valid key): {e}")
    
print("Done!")


