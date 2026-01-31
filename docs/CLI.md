# EPI CLI Reference (v2.2.0)

The **Evidence Packaged Infrastructure (EPI)** CLI is the primary tool for recording, verifying, and viewing AI evidence.

**Version:** 2.2.0  
**Install:** `pip install epi-recorder`

---

## 🚀 Quick Reference

| Command | Description |
|:---|:---|
| `epi init` | **Interactive Setup Wizard.** Creates keys, runs a demo, and explains the concepts. |
| `epi run <script.py>` | **Zero-Config Record.** Records, verifies, and views in one go. |
| `epi debug <file.epi>` | **AI Bug Detection.** Finds infinite loops, hallucinations, and inefficiencies automatically. |
| `epi view <file.epi>` | **Open Viewer.** Opens the browser timeline for a recording. |
| `epi verify <file.epi>` | **Check Integrity.** Validates signatures and hashes. |
| `epi chat <file.epi>` | **AI Chat.** Query your evidence using Google Gemini (Natural Language). |
| `epi ls` | **List Recordings.** Shows files in your `./epi-recordings/` folder. |
| `epi doctor` | **Self-Healing.** Fixes common environment issues (paths, keys, deps). |

---

## 🛠️ Core Commands

### `epi init`
**The "Foolproof" Starter.**  
Running this command launches an interactive wizard that:
1.  Check for SSH keys (generates one if missing).
2.  Creates a `setup_demo.py` file.
3.  Records it (`epi run`) automatically.
4.  Opens the result in your browser.

**Usage:**
```bash
$ epi init
```

### `epi run <script.py>`
**The default way to record.**  
Wraps your python script, records all inputs/outputs/API calls, saves it to a timestamped file in `./epi-recordings/`, verifies it, and opens the viewer.

**Usage:**
```bash
$ epi run my_agent.py
# -> Created: ./epi-recordings/my_agent_20251215_1000.epi
# -> Verified: ✅
# -> Viewing...
```

### `epi record --out <file.epi> -- <command>`
**Advanced recording.**  
Use this when you want to control the output filename or run non-Python commands (shell scripts, etc).

**Usage:**
```bash
# Record with specific filename
$ epi record --out experiment_1.epi -- python agent.py

# Record a shell command
$ epi record --out build.epi -- ./build_script.sh
```

### `epi view <file_or_name>`
**Offline Viewer.**  
Opens a local web server to display the `.epi` timeline. The viewer is strictly **offline-first** (no CDN dependencies) as of v2.1.X.

**Usage:**
```bash
# View by path
$ epi view ./epi-recordings/my_run.epi

# View by name (searches ./epi-recordings)
$ epi view my_run
```

### `epi verify <file.epi>`
**Cryptographic Verification.**  
Re-calculates hashes and checks the Ed25519 signature.

**Options:**
- `--verbose`: Show individual check results (manifest, env, steps).
- `--json`: Output machine-readable JSON (good for CI/CD).

**Usage:**
```bash
$ epi verify demo.epi
✅ Integrity: OK
✅ Signature: Valid (default)
✅ Checks: 23/23 passed
```

### `epi doctor`
**System Health Check.**  
Scans your environment for known issues (missing keys, bad paths, console encoding issues) and fixes them automatically.

**Usage:**
```bash
$ epi doctor
✅ Keys found
✅ Path verified
✅ ASCII encoding fixed
```

```

### `epi debug <file.epi>`
**AI-Powered Mistake Detection (v2.2.0).**  
Analyzes your recording to identify common agent bugs automatically.

**Detected Issues:**
- **Infinite Loops**: Repeated tool calls with same parameters
- **Hallucinations**: LLM responses that lead to immediate errors
- **Inefficiencies**: Excessive token usage for simple tasks
- **Repetitive Patterns**: Redundant work (same query multiple times)

**Usage:**
```bash
$ epi debug agent_session.epi

🔍 Analyzing 47 steps...

⚠️  INFINITE LOOP detected (steps 15-22)
    → Calling tool: search_web("fix error X") 
    → Same query repeated 7 times
    → Suggestion: Add error handling or retry limit

⚠️  HALLUCINATION detected (step 34)
    → LLM suggested file path that doesn't exist
    → Led to FileNotFoundError on next step

✅  No inefficiencies detected
✅  No repetitive patterns detected

Summary: 2 issues found
```

**Options:**
- `--json`: Output to JSON for automated CI checks

```

### `epi chat <file.epi>`
**Talk to your evidence.**  
Powered by Google Gemini. This interactive command loads the evidence context and lets you ask questions like "What errors occurred?" or "Why did the AI make this decision?".

**Usage:**
```bash
$ epi chat my_run.epi
# -> Loading evidence...
# -> Combined context: 1243 steps
# -> AI: Hello! Ask me anything about this run.
# You: Did any API calls fail?
```

**Requirements:**
- `GOOGLE_API_KEY` environment variable must be set.
- A `.epi` file (inputs are loaded into the LLM context).

---

## 🔐 Key Management (`epi keys`)

EPI uses Ed25519 keys to sign evidence.

| Subcommand | Description |
|:---|:---|
| `epi keys list` | Show all keys in `~/.epi/keys/`. |
| `epi keys generate` | Create a new keypair (default is created automatically on first run). |
| `epi keys export --name <k>` | Export public key to verify signatures elsewhere. |

---

## 🐍 Python API

For deeper integration, import `epi_recorder` in your code.

```python
from epi_recorder import record

# Method 1: Decorator
@record(goal="Test Model Accuracy")
def main():
    ...

# Method 2: Context Manager
with record("my_evidence.epi"):
    agent.run()
```

