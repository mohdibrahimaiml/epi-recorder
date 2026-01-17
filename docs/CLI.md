# EPI CLI Reference (v2.1.2)

The **Evidence Packaged Infrastructure (EPI)** CLI is the primary tool for recording, verifying, and viewing AI evidence.

**Version:** 2.1.2  
**Install:** `pip install epi-recorder`

---

## 🚀 Quick Reference

| Command | Description |
|:---|:---|
| `epi init` | **Interactive Setup Wizard.** Creates keys, runs a demo, and explains the concepts. |
| `epi run <script.py>` | **Zero-Config Record.** Records, verifies, and views in one go. |
| `epi view <file.epi>` | **Open Viewer.** Opens the browser timeline for a recording. |
| `epi verify <file.epi>` | **Check Integrity.** Validates signatures and hashes. |
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
