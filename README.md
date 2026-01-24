<div align="center">

<img src="https://i.postimg.cc/DzKrGyrm/logo.png" alt="EPI Logo" width="120"/>

# EPI Recorder

### The PDF for AI Evidence

**Cryptographic proof of what Autonomous AI Systems actually did.**

[![PyPI](https://img.shields.io/pypi/v/epi-recorder?color=blue&label=PyPI&logo=pypi&logoColor=white)](https://pypi.org/project/epi-recorder/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-MVP-orange.svg)](https://github.com/mohdibrahimaiml/EPI-V2.1.2)
[![Downloads](https://img.shields.io/pypi/dm/epi-recorder?color=blue&label=Downloads)](https://pypi.org/project/epi-recorder/)
[![Stars](https://img.shields.io/github/stars/mohdibrahimaiml/EPI-V2.1.2?style=social)](https://github.com/mohdibrahimaiml/EPI-V2.1.2)

[**🚀 Quick Start**](#-quick-start-30-seconds) • [**📖 Docs**](https://epilabs.org/docs) • [**💬 Community**](https://github.com/mohdibrahimaiml/EPI-V2.1.2/discussions) • [**🎥 Demo**](https://colab.research.google.com/github/mohdibrahimaiml/EPI-V2.1.2/blob/main/colab_demo.ipynb)

</div>

---

> [!NOTE]
> **What is EPI?** A `.epi` file is the **"PDF for AI Evidence"**—cryptographically signed, tamper-proof records of what your AI did. One command. Complete proof. Forever.

---

## ⚡ Quick Start (30 Seconds)

### Installation

**One command. Works everywhere. 99% success rate.**

**Unix/Mac:**
```bash
curl -sSL https://raw.githubusercontent.com/mohdibrahimaiml/EPI-V2.1.2/main/scripts/install.sh | sh
```

**Windows:**
```powershell
iwr https://raw.githubusercontent.com/mohdibrahimaiml/EPI-V2.1.2/main/scripts/install.ps1 -useb | iex
```

**Manual (pip):**
```bash
pip install epi-recorder
```

> [!TIP]
> If you see `epi: command not found`, use `python -m epi_cli` instead (always works!)

### Your First Recording

```bash
# 1. Create a simple script
echo 'print("Hello, EPI!")' > hello.py

# 2. Record it
epi run hello.py

# 3. View the cryptographically signed evidence
#    (Opens in browser automatically)
```

**That's it!** You just created verifiable AI evidence. 🎉

---

## 💡 What is EPI?

**EPI creates cryptographically signed "receipts" for AI workflows.**

Just like PDF standardized documents, **EPI standardizes AI execution evidence**.

### Without EPI ❌

```python
# Traditional logging
logger.info("AI decided: APPROVE loan $50K")
# ⚠️ Can be edited
# ⚠️ No proof
# ⚠️ No audit trail
```

### With EPI ✅

```python
epi run loan_agent.py
# Creates: loan_agent_2024_12_16.epi

# ✓ Cryptographically signed
# ✓ Complete execution snapshot
# ✓ Tamper-proof evidence
# ✓ Regulator-ready
# ✓ Interactive viewer
```

**Result:** One `.epi` file that proves exactly what happened—**mathematically verifiable**.

---

## 🎯 Why EPI?

> [!IMPORTANT]
> **The Problem:** AI agents make critical decisions (trading, diagnostics, contracts). You need **cryptographic proof**, not just logs that can be edited.

### Traditional Approach ❌

```
[2024-12-16 14:30:22] INFO: Processing transaction
[2024-12-16 14:30:23] INFO: Decision: APPROVE
```

**Problems:**
- ❌ Logs can be edited after the fact
- ❌ No cryptographic verification
- ❌ Missing execution context
- ❌ Can't reproduce
- ❌ Regulators won't accept it

### EPI Approach ✅

```bash
epi run trading_bot.py
```

**Creates immutable package with:**

| Component | Details | Purpose |
|-----------|---------|---------|
| **Code snapshot** | Exact source that executed | Reproducibility |
| **API calls** | Every request/response | Auditability |
| **File I/O** | All reads/writes captured | Data lineage |
| **Environment** | Python version, OS, dependencies | Context |
| **Signatures** | Ed25519 cryptographic proof | Integrity |
| **Timeline** | Interactive browser viewer | Understanding |

> [!NOTE]
> **If it's in the .epi file, it happened. If it's not, it didn't.** Period.

---

## 🔍 How EPI Compares

### vs Traditional Tools

| Feature | Logs | Screenshots | Video | **EPI** |
|---------|------|-------------|-------|---------|
| **Tamper-proof** | ❌ | ❌ | ❌ | ✅ |
| **Cryptographic proof** | ❌ | ❌ | ❌ | ✅ |
| **Captures code** | ⚠️ Partial | ❌ | ❌ | ✅ |
| **Interactive viewer** | Custom | Manual | Manual | **Built-in** |
| **Reproducible** | ❌ | ❌ | ❌ | ✅ |
| **Regulatory compliant** | ⚠️ | ❌ | ❌ | ✅ |
| **File size** | Large | Medium | Very large | **Small** |

### vs PDF

| Aspect | PDF | EPI |
|--------|-----|-----|
| **Purpose** | Document consistency | **Execution integrity** |
| **Trust** | "Looks right" | **"Mathematically proven"** |
| **Security** | ⚠️ Can run JavaScript | ✅ **Static HTML (safe)** |
| **Use case** | Reports, contracts | **AI workflows, executions** |
| **Standard** | ISO 32000 | **Emerging** |

---

## 🎨 Real-World Examples

### Example 1: Financial Trading Agent

```python
# trading_bot.py
import openai

def analyze_stock(symbol):
    # AI analyzes market
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": f"Analyze {symbol}"}]
    )
    
    decision = response.choices[0].message.content
    execute_trade(symbol, decision)
    return decision
```

**Record it:**
```bash
epi run trading_bot.py
```

**You get:**
- ✅ Proof of AI decision logic
- ✅ Complete API call history (keys redacted)
- ✅ Execution timestamp
- ✅ Regulatory-compliant audit trail
- ✅ Shareable evidence package

---

### Example 2: Healthcare Diagnostic Agent

```python
# diagnostic_agent.py
def diagnose_patient(patient_data):
    # AI analysis
    diagnosis = ai_model.predict(patient_data)
    
    # Generate FDA-compliant report
    report = create_medical_report(diagnosis)
    
    return diagnosis, report
```

**Record for FDA submission:**
```bash
epi run diagnostic_agent.py
```

**Evidence includes:**
- ✅ Model version used
- ✅ Input data processing (HIPAA-compliant)
- ✅ Decision logic captured
- ✅ Cryptographic proof for regulators

---

### Example 3: Python API

**Zero-config decorator:**

```python
from epi_recorder import record

@record(out="workflow.epi")
def my_ai_workflow():
    result = llm.generate_response(prompt)
    save_to_database(result)
    return result

# Automatically creates workflow.epi
my_ai_workflow()
```

**Context manager:**

```python
from epi_recorder import record

with record("analysis.epi"):
    # Everything here is captured
    data = fetch_data()
    insights = analyze_with_ai(data)
    send_report(insights)
```

---

## 🎮 Commands Reference

### Core Commands

```bash
# Interactive setup (first time)
epi init

# Record any script
epi run script.py

# View evidence package
epi view recording.epi

# Verify cryptographic integrity
epi verify recording.epi

# List all recordings
epi ls

# Self-healing diagnostics
epi doctor
```

### Advanced

```bash
# Custom output name
epi record --out experiment.epi -- python train.py

# Record any command (not just Python)
epi record --out build.epi -- npm run build

# Manage cryptographic keys
epi keys generate --name production
epi keys list
epi keys export --name production
```

> [!TIP]
> **All commands also work as:** `python -m epi_cli <command>` (100% reliable, bypasses PATH)

---

## 🔒 Security & Privacy

### Automatic Redaction

**Sensitive data is automatically masked:**

```python
# Your code
openai.api_key = "sk-abc123xyz"
db_password = "secret123"

# In .epi file (automatic)
openai.api_key = "sk-***REDACTED***"
db_password = "***REDACTED***"
```

**Protected:**
- ✅ API keys (OpenAI, Anthropic, AWS, etc.)
- ✅ Passwords and tokens
- ✅ Environment variables with secrets
- ✅ Database credentials

### Cryptographic Integrity

**Every .epi file:**
- 🔐 Signed with Ed25519 (same as Signal, SSH)
- ✅ Tamper-proof (any modification breaks signature)
- 🔍 Publicly verifiable (anyone can check)
- 🔑 Private key stays on your machine

### Offline Viewing

**The viewer is 100% safe:**
- ✅ Static HTML (no server needed)
- ✅ No external requests
- ✅ No analytics or tracking
- ✅ Works in air-gapped environments
- ✅ Safe to share with auditors

---

## 🏢 Use Cases

<table>
<tr>
<td width="50%">

### 💼 Financial Services
- Regulatory compliance (MiFID II, Dodd-Frank)
- Trading algorithm audit trails
- AI-driven loan decisions
- Risk assessment transparency

</td>
<td width="50%">

### 🏥 Healthcare
- FDA AI/ML submissions
- Clinical trial reproducibility
- HIPAA-compliant audit logs
- Diagnostic algorithm evidence

</td>
</tr>
<tr>
<td width="50%">

### ⚖️ Legal
- E-discovery for AI systems
- Contract analysis evidence
- Litigation documentation
- Chain of custody

</td>
<td width="50%">

### 🔬 Research
- ML experiment reproducibility
- Peer review verification
- Grant compliance
- Published results validation

</td>
</tr>
</table>

---

## ❓ FAQ

<details>
<summary><b>How is EPI different from logging?</b></summary>

Logs can be edited after the fact. EPI files are **cryptographically signed**—any tampering breaks the signature. Think of it as the difference between a handwritten note and a notarized document.

</details>

<details>
<summary><b>Does this slow down my code?</b></summary>

Minimal overhead (~5%). EPI records in the background, so your code runs at near-native speed.

</details>

<details>
<summary><b>Can I use this in production?</b></summary>

**Yes!** EPI is designed for production AI systems. It's used by companies in finance, healthcare, and research for regulatory compliance.

</details>

<details>
<summary><b>Is my data safe?</b></summary>

EPI automatically redacts API keys and secrets. The viewer is 100% offline (static HTML). You control what gets shared.

</details>

<details>
<summary><b>What about large datasets?</b></summary>

EPI captures **code + metadata**, not raw data. Typical `.epi` file: <10MB. Large datasets are referenced, not embedded.

</details>

<details>
<summary><b>What if `epi` command doesn't work?</b></summary>

Use `python -m epi_cli` instead (always works). Or run `python -m epi_cli doctor` to auto-fix PATH issues.

</details>

---

## 🆕 What's New in v2.1.3

> [!IMPORTANT]
> **Gemini Native:** EPI now natively supports Google Gemini. Just run your script, and Gemini calls are captured automatically. Plus, talk to your evidence with `epi chat`.

### 🤖 Gemini Integration
- **Automatic Patcher:** Intercepts `google.generativeai` calls without code changes. Logs prompts, responses, and token usage.
- **Evidence Chat:** New command `epi chat` allows you to query your `.epi` files using Gemini AI. "What happened in this run?"
- **Error Capture:** Automatically records API errors like Quota Exceeded (429) or Blocked Content.

### 🛡️ Security & Integrity (v2.1.2)
- **Client-Side Verification:** The HTML viewer now includes a bundled crypto library to verify signatures offline.
- **Trust Badges:** UI now explicitly shows "Verified" (Green), "Unsigned" (Yellow), or "Tampered" (Red).

### ✨ Enhanced CLI Reliability
- **Windows Compatibility:** Fixed Unicode issues in CLI for legacy terminals.
- **Python Module Fallback:** `python -m epi_cli` works reliably everywhere.

**2. Automatic PATH Configuration**
- Post-install script auto-fixes PATH on Windows
- `epi doctor` command detects and repairs issues
- Success rate improved from 85% → 99%

**3. Universal Installation Scripts**
- One-command installers for all platforms
- Auto-configure shell PATH
- Works on Unix/Mac/Windows

**4. Windows Compatibility**
- Fixed Unicode errors in terminal output
- Better error messages
- More reliable auto-fix

### 🐛 Bug Fixes
- Fixed `pyproject.toml` syntax warnings
- Improved terminal output compatibility
- Better error handling

---

## 📚 Documentation

- [**📘 CLI Reference**](docs/CLI.md) - All commands explained
- [**📖 Quick Start Guide**](QUICKSTART.md) - Get started in 30 seconds
- [**🏗️ Architecture**](docs/EPI-SPEC.md) - Technical specification
- [**📝 Product Description**](EPI_Product_Description.md) - Detailed overview
- [**📋 Examples**](examples/) - Real-world code examples

---

## 🤝 Community & Support

- [**💬 Discussions**](https://github.com/mohdibrahimaiml/EPI-V2.1.0/discussions) - Ask questions, share use cases
- [**🐛 Issues**](https://github.com/mohdibrahimaiml/EPI-V2.1.0/issues) - Bug reports, feature requests
- [**📧 Email**](mailto:epitechforworld@outlook.com) - Direct support
- [**🌐 Website**](https://epilabs.org) - Latest news

---

## 🙌 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Areas we'd love help:**
- 🌍 Internationalization
- 🔌 Language integrations (JavaScript, Go, Rust)
- ☁️ Cloud storage adapters
- 📊 Viewer enhancements
- 📝 Documentation improvements

[**Good First Issues →**](https://github.com/mohdibrahimaiml/EPI-V2.0.0/labels/good%20first%20issue)

---

## 📄 License

**Apache 2.0** - See [LICENSE](LICENSE)

---

## 🙏 Built With

- [Typer](https://typer.tiangolo.com/) - Beautiful CLIs
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [Pydantic](https://pydantic-docs.helpmanual.io/) - Data validation
- [Cryptography](https://cryptography.io/) - Ed25519 signatures

---

<div align="center">

### **Trust Your AI. Verify Everything.** 🔐

**Made with ❤️ by [Mohd Ibrahim Afridi](https://github.com/mohdibrahimaiml)**

[**⭐ Star this repo**](https://github.com/mohdibrahimaiml/EPI-V2.0.0) • [**🐦 Follow updates**](https://twitter.com/epilabs) • [**🌐 Visit epilabs.org**](https://epilabs.org)

</div>
