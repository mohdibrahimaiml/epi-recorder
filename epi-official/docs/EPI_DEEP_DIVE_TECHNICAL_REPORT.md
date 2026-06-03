# EPI System: Deep Dive Technical Report

**Target Audience:** CTOs, Lead Engineers, Security Auditors
**Scope:** Source code analysis, cryptographic protocols, and core architectural decisions.

---

## 1. The Recorder Engine (`epi-recorder`)

The heart of EPI is its ability to capture code execution **deterministically**. This is achieved through **Explicit Capture**.

### A. The Capture Mechanism: Explicit Wrappers
Instead of relying only on implicit monkey-patching, EPI supports explicit wrappers to keep capture behavior predictable across Python environments.

**Code Analysis (`epi_recorder/wrappers/openai.py`):**
1.  **Wrapping:** The developer wraps their client: `client = wrap_openai(OpenAI())`.
2.  **Capture:** The wrapper intercepts calls (e.g., `chat.completions.create`).
    *   **Pre-Call:** Captures arguments.
    *   **Execution:** Calls the original method.
    *   **Post-Call:** Captures the return value.
3.  **Logging:** Writes a structured JSON object to `steps.jsonl`.

**Why this matters:** Explicit capture removes "magic", ensuring that EPI never breaks your application's behavior and works in all Python environments.

### B. The Security Kernel (`epi_core/trust.py`)
Trust is not achieved by "logs" but by **Cryptographic Signatures**.

**Protocol:**
1.  **Canonicalization:** Before signing, the `manifest.json` is "canonicalized" to ensure deterministic hashing.
    *   Keys are sorted alphabetically.
    *   Whitespace is stripped.
    *   This prevents "valid JSON, invalid Signature" errors across different platforms (Windows vs Linux handling of newlines).
2.  **Signing Algorithm:** **Ed25519** (Edwards-curve Digital Signature Algorithm).
    *   Selected for high performance (signing doesn't slow down the AI agent) and small key size (32 bytes).
    *   Library: `cryptography.hazmat.primitives.asymmetric.ed25519`.
3.  **Key Management:** Keys are stored locally in `~/.epi/keys`. EPI uses this local key store for artifact signing.

### C. The Redactor (`epi_core/redactor.py`)
To prevent PII/Secret leaks, EPI runs a regex engine *before* writing to disk.
*   **Patterns:** Scans for `sk-proj-...` (OpenAI), `AKIA...` (AWS), and standard private key headers.
*   **Behavior:** Replaces found secrets with `***REDACTED***`. This happens in memory, so the secret never touches the `steps.jsonl` file.

---

## 2. The Cloud Verifier (`verify.html`)

The Verifier is a **Zero-Knowledge** application. It serves to prove the validity of a file without ever needing to see its contents on a server.

### A. Client-Side Architecture
*   **No Backend:** The Python backend (`verify.py`) logic was ported to JavaScript.
*   **Libraries:**
    *   `JSZip`: Reads the ZIP structure in browser RAM.
    *   `@noble/ed25519`: Pure JS implementation of Ed25519 for signature verification.

### B. The Verification Logic (`processFile()`)
1.  **Unzip:** Opens the `.epi` file.
2.  **Manifest Parse:** Reads `manifest.json`.
3.  **Hash Verification:**
    *   Iterates through `file_manifest`.
    *   Computes SHA-256 of every file in the ZIP (e.g., `steps.jsonl`, `main.py`).
    *   Compares computed hash vs manifest hash.
4.  **Signature Verification:**
    *   Extracts the signature string `ed25519:keyname:signaturebase64`.
    *   Reconstructs the "Canonical Manifest String".
    *   Verifies the signature against the provided Public Key.

### C. The "Deep Audit" Feature (New)
We added a transparency layer to show users *what* they are verifying.
*   **Implementation:** A dynamic table generator that iterates `manifest.file_manifest` and renders `Filename` + `Hash` chunks.
*   **Purpose:** Allows auditors to manually spot-check files against their known Git hashes.

### D. The "Integrated Visualizer" (The Safe-View)
This was the most complex addition. The goal was to render the *embedded* `viewer.html` (which might contain arbitrary HTML/JS) inside the Verifier without risking XSS (Cross-Site Scripting).

**The Solution: Sandboxed Blob Iframe**
1.  **Extraction:** We pull the `viewer.html` string from the ZIP.
2.  **Blobbing:** We create a browser `Blob` object:
    ```javascript
    const blob = new Blob([htmlContent], { type: 'text/html' });
    ```
3.  **Isolation:** We generate a unique URL:
    ```javascript
    vizFrame.src = URL.createObjectURL(blob);
    ```
4.  **Sandboxing:** The `<iframe>` has strict permissions:
    ```html
    <iframe sandbox="allow-scripts allow-popups allow-forms">
    ```
    *   `allow-scripts`: Needed for the viewer's Timeline rendering logic.
    *   **Crucially missing:** `allow-same-origin`. This prevents the viewer from accessing the parent Verifier's cookies, local storage, or DOM. It effectively runs in a null origin.

---

## 3. The "Invisible" CI/CD Hook (`epi-action`)

To enforce this at an enterprise scale, we built a GitHub Action.

**Mechanism:**
1.  **Trigger:** Runs on `pull_request` or `push`.
2.  **Evidence Generation:** Runs the tests wrapped in `epi run`.
3.  **Verification:** Immediately runs `epi verify` on the generated artifact.
4.  **Blocking:** If verification fails (e.g., unsigned artifact), the CI pipeline fails, preventing the deploy.

---

## 4. Conclusion

The EPI system is architected for **Trustless Verification**. 
*   The **Recorder** assumes the environment is hostile (redacts secrets).
*   The **Verifier** assumes the file is hostile (verifies sigs, sandboxes viewer).
*   The **Crypto** assumes the network is hostile (signs offline).

This "Paranoid Architecture" is what makes it suitable for High-Compliance environments like Banking and Healthcare.

**(End of Report)**
