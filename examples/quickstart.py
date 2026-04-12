"""
EPI Quickstart — the minimum integration that gives you a signed .epi artifact.

Works with any OpenAI-compatible endpoint, including Ollama (local, free).
"""

from epi_recorder import record, wrap_openai
from openai import OpenAI

# Uses OPENAI_API_KEY env var automatically.
# Local Ollama alternative (no API key, free):
#   client = wrap_openai(OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"))
client = wrap_openai(OpenAI())

with record("my_first_agent.epi"):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Explain EPI Recorder in one sentence."}],
    )
    print(response.choices[0].message.content)

# That's it.
# Created:  my_first_agent.epi
# Contains: LLM call, response, tokens, latency, Ed25519 signature
# Open it:  epi view my_first_agent.epi
