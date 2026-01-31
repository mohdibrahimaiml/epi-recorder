"""
EPI Quickstart - The Only Example That Matters for YC

This is the simplest possible integration.
Just wrap your agent code. That's it.
"""

from epi_recorder import record
import openai

# Set your OpenAI API key
# openai.api_key = "your-key-here"

# Wrap your agent code - ZERO changes needed
with record(workflow_name="my_first_agent"):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Hello! Explain EPI-Recorder in one sentence."}]
    )
    print(response.choices[0].message.content)

# That's it! 
# ✅ Creates: my_first_agent_TIMESTAMP.epi
# ✅ Captures: LLM call, response, tokens, cost
# ✅ Signs: Ed25519 cryptographic signature
# ✅ Opens: Browser viewer automatically


