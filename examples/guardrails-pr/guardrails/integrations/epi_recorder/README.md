# EPI Recorder Integration for Guardrails AI

Produces tamper-evident, cryptographically signed **.epi** artifacts from every Guardrails validation execution.

## Quick Start

```bash
pip install epi-recorder wrapt
```

```python
from guardrails.integrations.epi_recorder import EPIInstrumentor

instrumentor = EPIInstrumentor()
instrumentor.instrument()

guard = Guard.from_rail("my.rail")
result = guard(llm_api, prompt)
# \u2192 guardrails_run.epi written (Ed25519-signed)

instrumentor.uninstrument()
```

## Verification

```bash
epi verify guardrails_run.epi --aiuc1
```

## Options

```python
EPIInstrumentor(
    output_path="my_run.epi",
    auto_sign=True,
    redact=True,
    goal="Validate LLM output",
    tags=["guardrails", "prod"],
)
```
