# EPI - Evidence Packaged Infrastructure

**Evidence Packaged Infrastructure (EPI)** - The "PDF for AI Workflows"

Self-contained, cryptographically verified evidence packages for AI systems.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-production--ready-green.svg)](https://pypi.org/project/epi-recorder/)
[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://pypi.org/project/epi-recorder/)
[![GitHub](https://img.shields.io/badge/GitHub-EPI--V1.1-black.svg?logo=github)](https://github.com/mohdibrahimaiml/EPI-V1.1)

---

## 🚀 Quick Start

### Python API (Recommended for Developers)

```python
from epi_recorder import record

# Wrap your AI code with a context manager
with record("my_workflow.epi", workflow_name="Demo"):
    # Your AI code runs normally - automatically recorded!
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello!"}]
    )
    
    # Optionally log custom events
    session.log_step("calculation", {"result": 42})

# .epi file is automatically created, signed, and ready to verify!
```

### CLI (For Shell Scripts & CI/CD)

```bash
# Install
pip install epi-recorder

# Record a workflow
epi run my_ai_script.py

# Verify integrity and authenticity
epi verify recording.epi

# View in browser
epi view recording.epi
```

That's it! Your AI workflow is now captured, signed, and viewable.

---

## 🆕 What's New in v1.1.0

✅ **Windows Compatibility** - Full support for Windows CMD and PowerShell  
✅ **Unicode Fixes** - Clean ASCII output, no encoding errors  
✅ **Enhanced CLI** - All 11 commands work perfectly on Windows  
✅ **Improved Metadata** - Better support for goal, notes, metrics, tags  
✅ **Bug Fixes** - Resolved redaction edge cases and error handling  

**Note:** File format remains backward compatible (spec version 1.0-keystone)

---

## 🎯 What is EPI?

**EPI (Evidence Packaged Infrastructure)** captures **everything** that happens during an AI workflow:


- 🤖 **LLM API calls** - Prompts, responses, tokens, latency
- 🔒 **Secrets redacted** - Automatically (15+ patterns)
- 📦 **Files and artifacts** - Content-addressed storage
- 🖥️ **Environment snapshot** - OS, Python version, packages
- ✅ **Cryptographically signed** - Ed25519 signatures
- 📊 **Beautiful timeline viewer** - Interactive HTML interface

All packaged into a **single .epi file** that anyone can verify and replay.

---

## 🌟 Why EPI?

### The Problem

❌ **70% of AI research cannot be reproduced**  
❌ **AI models fail mysteriously in production**  
❌ **Cannot prove how AI decisions were made**  
❌ **"It worked on my machine" debugging nightmare**

### The Solution

✅ **Record** - Capture complete AI workflows with one command  
✅ **Verify** - Cryptographic proof of authenticity  
✅ **Share** - Single file contains everything  
✅ **Replay** - Deterministic reproduction (offline mode)  
✅ **Audit** - Full transparency for compliance

---

## 📖 Core Features

### 🎬 Recording

```bash
epi run train.py
```

Automatically captures:
- OpenAI API calls (GPT-4, GPT-3.5, etc.)
- Shell commands and outputs
- Python execution context
- Generated files and artifacts
- Environment variables (redacted)

### 🔐 Security by Default

- **Auto-redacts secrets:** API keys, tokens, credentials
- **Ed25519 signatures:** Cryptographic proof of authenticity
- **Frictionless:** Auto-generates keypair on first run
- **No secret leakage:** 15+ regex patterns protect sensitive data

### ✅ Verification

```bash
epi verify experiment.epi
```

Three-level verification:
1. **Structural** - Valid ZIP format and schema
2. **Integrity** - SHA-256 file hashes match
3. **Authenticity** - Ed25519 signature valid

### 👁️ Beautiful Viewer

```bash
epi view experiment.epi
```

Opens in your browser with:
- Interactive timeline of all steps
- LLM chat bubbles (prompts & responses)
- Trust badges (signed/unsigned)
- Artifact previews
- Zero code execution (pure JSON rendering)

---

## 🎓 Use Cases

### AI Researchers

```bash
# Submit verifiable research
epi run reproduce.py
```

✅ 100% reproducible methodology  
✅ Eliminates "it worked on my machine"  
✅ Speeds up peer review

### Enterprise AI Teams

```bash
# Capture production AI runs
epi run deploy_model.py
```

✅ Audit trails for compliance (EU AI Act, SOC 2)  
✅ Debug production failures instantly  
✅ Version control for AI systems

### Software Engineers

```bash
# Perfect bug reproduction
epi run flaky_test.py
```

✅ Share exact failing conditions  
✅ Debug AI features faster  
✅ Stable CI/CD for AI features

---

## 🛠️ Installation

### From PyPI (Recommended)

```bash
pip install epi-recorder
```

### From Source

```bash
git clone https://github.com/mohdibrahimaiml/EPI-V1.1.git
cd EPI-V1.1
pip install -e .
```

### Requirements

- **Python:** 3.11 or higher
- **OS:** Windows, macOS, Linux
- **Dependencies:** Automatically installed

---

## 📚 Commands

### `epi run` - Record and Auto-Verify

Record a Python script (easiest way):

```bash
epi run script.py
```

Options:
- `--no-verify` - Skip verification step
- `--no-open` - Don't open browser
- `--goal "text"` - Set workflow goal
- `--metrics '{"key": value}'` - Add metrics (JSON)

### `epi verify` - Check Integrity

Verify .epi file integrity and authenticity:

```bash
epi verify recording.epi
```

Output:
```
+-------------- [OK] EPI Verification Report --------------+
| File: recording.epi                                      |
| Trust Level: HIGH                                        |
| Message: Cryptographically verified and integrity intact |
+----------------------------------------------------------+
```

### `epi view` - Open in Browser

View recording in interactive HTML viewer:

```bash
epi view recording.epi
```

### `epi ls` - List Recordings

Show all recordings in `./epi-recordings/`:

```bash
epi ls
```

### `epi keys` - Manage Keys

```bash
epi keys generate --name mykey
epi keys list
epi keys export --name mykey
```

---

## 🐍 Python API

### Why Use the Python API?

The Python API is the **recommended way** to integrate EPI into your AI applications:

✅ **Zero CLI overhead** - No shell commands needed  
✅ **Seamless integration** - Just wrap your code with `with record()`  
✅ **Auto-captures OpenAI** - Automatically records all LLM calls  
✅ **Custom logging** - Manually log steps and artifacts  
✅ **Auto-signed** - Cryptographic signatures by default

### Basic Usage

```python
from epi_recorder import record

with record("experiment.epi", workflow_name="My Experiment"):
    # Your code here - automatically recorded
    result = train_model()
    print(f"Result: {result}")
```

### With Custom Logging

```python
from epi_recorder import record
from pathlib import Path

with record("workflow.epi", 
            workflow_name="Data Processing",
            tags=["v1.0", "prod"]) as session:
    # Process data
    data = load_data("input.csv")
    
    # Log custom steps
    session.log_step("data.loaded", {
        "rows": len(data),
        "columns": list(data.columns)
    })
    
    # Process...
    results = process(data)
    
    # Save output
    results.to_csv("output.csv")
    
    # Capture the output file
    session.log_artifact(Path("output.csv"))
    
    # Log summary
    session.log_step("processing.complete", {
        "status": "success",
        "output_rows": len(results)
    })
```

### With OpenAI (Auto-Recorded)

```python
from epi_recorder import record
import openai

with record("chat_session.epi", workflow_name="Customer Support"):
    # OpenAI calls are automatically captured!
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is quantum computing?"}
        ]
    )
    
    print(response.choices[0].message.content)
    
    # API keys are automatically redacted in the recording!
```

### Advanced Options

```python
from epi_recorder import record

with record(
    "advanced.epi",
    goal="Train ML model",
    notes="Testing with new hyperparameters",
    metrics={"accuracy": 0.96, "latency_ms": 150},
    approved_by="lead_scientist@company.com",
    metadata_tags=["production", "v2.1"],
    auto_sign=True,        # Sign with default key
    redact=True           # Redact secrets
) as session:
    # Your workflow
    pass
```

---

## 🔒 Security

### Automatic Redaction

EPI automatically removes:
- OpenAI API keys (`sk-...`)
- Anthropic API keys (`sk-ant-...`)
- AWS credentials (`AKIA...`)
- GitHub tokens (`ghp_...`)
- Bearer tokens, JWT tokens
- Database connection strings
- Private keys (PEM format)

### Cryptographic Signing

- **Algorithm:** Ed25519 (RFC 8032)
- **Key Size:** 256 bits
- **Hash:** SHA-256 with canonical CBOR
- **Storage:** `~/.epi/keys/` (secure permissions)

---

## 🧪 Example

```python
# chat_example.py
from openai import OpenAI

client = OpenAI()

response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "user", "content": "Explain quantum computing"}
    ]
)

print(response.choices[0].message.content)
```

```bash
# Record it
epi run chat_example.py

# Verify it
epi verify chat_example_*.epi
# ✅ Trust Level: HIGH

# View it
epi view chat_example_*.epi
# Opens timeline in browser
```

---

## 🧑‍💻 Development

### Running Tests

```bash
pytest tests/ -v --cov=epi_core --cov=epi_cli
```

### Project Structure

```
epi-recorder/
├── epi_core/           # Core logic
├── epi_cli/            # CLI commands
├── epi_recorder/       # Runtime capture
├── tests/              # Test suite
└── docs/               # Specification
```

---

## 📊 Project Status

✅ **Phase 0:** Foundation (complete)  
✅ **Phase 1:** Trust Layer (complete)  
✅ **Phase 2:** Recorder MVP (complete)  
✅ **Phase 3:** Viewer MVP (complete)  
✅ **Phase 4:** Polish & Production (complete)

**Current Release:** v1.1.0 - Production Ready

---

## 📞 Contact & Support

**Project:** Evidence Packaged Infrastructure (EPI)  
**Founder:** Mohd Ibrahim Afridi  
**Project Email:** epitechforworld@outlook.com  
**Personal Email:** mohdibrahimaiml@outlook.com

**Links:**
- **GitHub Repository:** https://github.com/mohdibrahimaiml/EPI-V1.1
- **Issues:** https://github.com/mohdibrahimaiml/EPI-V1.1/issues
- **PyPI:** https://pypi.org/project/epi-recorder/
- **Documentation:** [Coming Soon]

---

## 📄 License

Apache License 2.0

Copyright (c) 2024 Mohd Ibrahim Afridi

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

---

## 🙏 Acknowledgments

Built with:
- [Pydantic](https://pydantic.dev/) - Data validation
- [Typer](https://typer.tiangolo.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [cryptography](https://cryptography.io/) - Ed25519 signatures

---

## 🌟 Made with ❤️ for the AI community

**Turning opaque AI runs into transparent, portable digital proofs.**

EPI makes AI workflows reproducible, verifiable, and auditable.

---

**Get started today:**

```bash
pip install epi-recorder
```

**Record your first AI workflow:**

```python
from epi_recorder import record

@record
def hello_epi():
    print("Hello, EPI!")
    return "success"

hello_epi()
```

**Welcome to the future of AI transparency!** 🚀
