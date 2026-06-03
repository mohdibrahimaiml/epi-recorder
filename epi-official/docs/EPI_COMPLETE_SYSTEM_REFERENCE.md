# EPI System Reference Manual

**Version:** 4.0.1
**Last Updated:** 2026-04-12
**Status:** Production Ready

---

## 1. System Overview

**EPI (Evidence Packaged Infrastructure)** packages AI execution into portable, verifiable `.epi` artifacts. It helps teams preserve execution context, review decision evidence, and verify artifact integrity without treating vendor logs as the system of record.

The system consists of two distinct repositories:
1.  **`epi-recorder` (The Generator):** A Python package that instruments code to capture execution data.
2.  **`EPI WEBSITE` (The Verifier):** A static HTML/JS web application that parses and verifies `.epi` files client-side.

---

## 2. Repository 1: EPI Recorder (`epi-recorder`)

**Path:** `c:\Users\dell\epi-recorder`
**Language:** Python 3.11+
**License:** MIT

### Core Architecture
This package is responsible for the **Creation** of evidence.

*   **`epi_core/`**: The security kernel.
    *   `trust.py`: Handles Ed25519 key generation and signing. ensuring non-repudiation.
    *   `container.py`: Manages the ZIP file structure (Manifest + Steps + Viewer).
    *   `redactor.py`: Regex engine that sanitizes secrets (API keys, passwords) from logs *before* writing to disk.
    *   `schemas.py`: Pydantic definitions for the JSON Manifest.

*   **`epi_recorder/`**: The runtime instrumentation.
    *   `wrappers/`: Modules for explicitly wrapping libraries (e.g., `openai`, `requests`).
    *   `api.py`: Provides the `log_llm_call` API and `@record` decorator.
    *   `bootstrap.py`: Injection logic for the CLI `sitecustomize` trick.

*   **`epi_cli/`**: The User Interface.
    *   `run.py`: The `epi run` command. It creates a temporary environment, injects the recorder, and executes the user's script.
    *   `verify.py`: Python-based verification logic (server-side equivalent of the web verifier).

*   **`epi_viewer_static/`**:
    *   `viewer.html`: The template HTML file that is embedded *inside* every `.epi` zip. This allows the evidence to be "Self-Viewing" even without internet access.

### Key Capabilities
*   **Zero-Config Recording:** `epi run script.py` works without changing source code.
*   **Automatic Redaction:** Prevents leak of secrets in the evidence.
*   **Default Signing:** Auto-generates keys (`~/.epi/keys`) if none exist, ensuring all artifacts are signed.
*   **CLI Logic:** `epi doctor` auto-fixes PATH issues on Windows.

---

## 3. Repository 2: EPI Website (`EPI WEBSITE`)

**Path:** `c:\Users\dell\OneDrive\Desktop\EPI WEBSITE`
**Tech Stack:** HTML5, Tailwind CSS, Vanilla JS
**Deployment:** GitHub Pages / Static Hosting

### Core Architecture
This is the **Verification** layer. It is "Trustless" (Client-Side Only).

*   **`verify.html` (The Cloud Verifier):**
    *   **Logic:** Uses `JSZip` to unpack `.epi` files in browser memory.
    *   **Crypto:** Uses `@noble/ed25519` (WASM/JS) to verify signatures against the manifest hash.
    *   **Privacy:** No files are uploaded. Everything happens locally.
    *   **Features:**
        *   **Red/Green Status:** Instant visual verification.
        *   **Deep Audit:** Modal showing file list and SHA-256 hashes.
        *   **Integrated Visualizer:** Sandboxed `<iframe>` that renders the embedded `viewer.html` securely.

*   **`index.html` (Landing Page):**
    *   Marketing site explaining the "Trust Layer" value prop.
    *   Installation instructions (`iwr ...`).

*   **`viewer.js`**:
    *   Shared logic for the standalone web viewer (different from the embedded one).

*   **`sw.js` (Service Worker):**
    *   Enables **PWA (Progressive Web App)** capabilities.
    *   Allows the website to be installed as a native desktop app ("EPI Verifier").
    *   Provides offline support.

### Key Capabilities
*   **Universal Compatibility:** Works on any device with a browser.
*   **Air-Gapped Ready:** Can be saved to desktop and run without internet.
*   **Safe-View:** The "Visualizer" lets users see rich HTML evidence (charts, logs) without executing untrusted code on their main system.

---

## 4. The Data Format (`.epi`)

An `.epi` file is a **ZIP** archive renamed to `.epi`. It contains:

| File | Purpose |
| :--- | :--- |
| `manifest.json` | Metadata (Author, Timestamp, Signature, File Hashes). |
| `steps.jsonl` | The actual log of execution (JSON Lines). |
| `viewer.html` | A static HTML file to view the recording offline. |
| `environment.json` | Snapshot of OS, Python packages, and Env Vars. |
| `your_script.py` | (Optional) Snapshot of the source code. |

---

## 5. Operational Handbook

### Developer Workflow (Recording)
1.  **Install:** `pip install epi-recorder`
2.  **Run:** `epi run my_script.py`
3.  **Output:** `my_script.epi` is created.

### Auditor Workflow (Verifying)
1.  **Open:** Go to `verify.epilabs.org` (or local `verify.html`).
2.  **Drop:** Drag the `.epi` file onto the page.
3.  **Verify:** Look for the **Green Checkmark**.
4.  **Inspect:** Click "View Files" to check content, "View Evidence" to see the timeline.

### CI/CD Workflow (Automated)
1.  **Github Action:** Use `epi-action` in `.github/workflows`.
2.  **Verification:** The action fails the build if the script runs but produces unsigned or tampered evidence.

---

**(End of Manual)**
