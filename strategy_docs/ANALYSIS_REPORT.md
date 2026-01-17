# EPI Recorder Codebase Analysis Report

## 1. Executive Summary
EPI Recorder is a Python-based tool designed to create cryptographically verifiable proofs of AI workflow executions. It functions as a "PDF for AI," capturing code, inputs, outputs, environmental data, and API interactions into a single, tamper-proof `.epi` file (a ZIP container). The codebase is structured as a modular Python package with a clear separation of concerns between core logic, recording instrumentation, command-line interface, and viewing utilities.

**Key Strengths:**
- **Security-First Design:** Implements Ed25519 digital signatures and automatic secret redaction by default.
- **Zero-Config UX:** "Smart" CLI that handles environment setup, path injection, and auto-discovery of scripts.
- **Portable Evidence:** Self-contained `.epi` files include everything needed for verification and viewing (embedded HTML viewer).
- **Non-Intrusive:** Uses monkey-patching and sitecustomize injection to record without requiring code changes in the target script.

## 2. Architecture Overview

The codebase is organized into four primary components:

### A. `epi_core` (The Foundation)
Handles the data structure, security, and serialization.
- **`trust.py`**: Implements the "Trust Layer". Uses `cryptography` library for Ed25519 signing. The manifest hash is canonicalized before signing to ensure consistency.
- **`container.py`**: Manages the `.epi` ZIP format. It ensures `mimetype` is uncompressed at the start (validating the file format) and injects the `viewer.html`.
- **`redactor.py`**: A regex-based engine that sanitizes sensitive data (API keys, passwords) from logs *before* they are written to disk.
- **`schemas.py`**: Pydantic models defining the structure of the Manifest and Steps.

### B. `epi_recorder` (The Recorder)
Responsible for capturing runtime data.
- **`patcher.py`**: The "magic" module. It monkey-patches `openai` (v1 and legacy) and `requests` libraries to intercept calls, capturing their inputs, outputs, latency, and costs.
- **`api.py`**: Provides the user-facing `record` decorator and context manager. It manages the `EpiRecorderSession` lifecycle.
- **`bootstrap.py`**: Used by the CLI to initialize recording inside a child process via `sitecustomize.py`.

### C. `epi_cli` (The Interface)
A Typer-based CLI that orchestrates the user experience.
- **`run.py`**: The main entry point `epi run`. It sets up a temporary workspace, creates a `sitecustomize.py` to inject the bootstrap logic, and spawns the user's script in a subprocess.
- **`verify.py`**: Standalone verification logic.
- **`main.py`**: App entry point.

### D. `epi_viewer` (The Visualizer)
- **`epi_viewer.py`**: A desktop wrapper using `pywebview` to display the evidence file in a native window.
- **`epi-viewer/` (Electron App)**: A separate, more robust desktop viewer built with Electron, offering better cross-platform support and security isolation.
- **`epi_viewer_static`**: Contains the HTML/JS/CSS assets for the viewer that get embedded into every `.epi` file.

## 3. Data Flow Analysis (How `epi run` works)

1.  **Initialization**: User runs `epi run script.py`.
2.  **Setup**: CLI creates a temp directory with a `sitecustomize.py` file.
3.  **Injection**: CLI sets `PYTHONPATH` to include this temp dir and sets `EPI_RECORD=1`.
4.  **Execution**: CLI spawns `script.py` in a subprocess.
5.  **Bootstrap**: Python starts, imports `sitecustomize`. This triggers `epi_recorder.bootstrap.initialize_recording()`.
6.  **Patching**: `bootstrap` calls `patcher.patch_all()`, hooking into OpenAI and Requests.
7.  **Recording**: As the script runs, patched functions capture data to `steps.jsonl` in the temp dir.
8.  **Teardown**: On script exit, `EpiRecorderSession` captures the environment, finalizes the manifest, packs everything into a `.epi` ZIP.
9.  **Signing**: The `.epi` file is typically signed using a locally generated Ed25519 private key.
10. **Verification**: The CLI immediately verifies the new file's integrity and signature.

## 4. Security & Trust Analysis

-   **Cryptography**: Uses Ed25519 (via `cryptography` lib), a modern, high-security signature scheme.
    -   *Good*: Verification checks both file hash integrity (SHA-256) and the digital signature.
    -   *Good*: Signatures verify a canonical form of the manifest to avoid JSON formatting issues.
-   **Redaction**: The `Redactor` class is aggressive by default, scanning for OpenAI keys, AWS creds, and more using regex.
    -   *Note*: Redaction happens at the "step" level before writing to disk, minimizing leak risk.
-   **Viewer Security**: The viewer is *static HTML*. It does not require a backend server to render, making it safe to view in air-gapped environments. The "Smart Viewer" is embedded directly into the `.epi` file.

## 5. Functional & User Experience Analysis

### User Workflows
The system supports two primary user personas:

1.  **The CLI User (Zero-Config)**
    -   **Workflow**: `epi run my_script.py`
    -   **Experience**: No code changes needed. The tool "magically" wraps execution.
    -   **Error Handling**: If `epi` command fails (common path issue), users are guided to `python -m epi_cli`.
    -   **Windows Support**: Robust PowerShell scripts (`install.ps1`) handle PATH injection automatically.

2.  **The Developer (Python API)**
    -   **Workflow**:
        ```python
        with record("run.epi", goal="Validation"):
            run_ai_job()
        ```
    -   **Experience**: Granular control via decorators or context managers. Allows manual logging of custom steps (`log_step`) and artifacts (`log_artifact`) alongside auto-captured data.

### UX Friction Points & Solutions
-   **Path Issues**: `api: command not found` is a common Python CLI pain point. The project addresses this with aggressive specific warnings in the README and "Self-Healing" via `epi doctor` and `install.ps1`.
-   **Viewer Complexity**: There are **three** viewer implementations:
    -   **Embedded**: Minimal static HTML inside every ZIP (fallback).
    -   **Python**: `epi_viewer.py` using `pywebview` (for quick local viewing).
    -   **Electron**: `epi-viewer/` (for a premium standalone desktop app experience).
-   **Signing**: By default, `epi run` generates a keypair if one doesn't exist ("default" identity), preventing the "unsigned file" warning that would otherwise erode trust.

## 6. Code Quality & Status
-   **Documentation**: Excellent. Detailed README, docstrings in core files, and clear architecture.
-   **Testing**: Extensive suite in `tests/` covering unit tests, integration tests (`test_full_system.py`), and edge cases (`test_redactor.py`).
-   **Maturity**: The presence of many "fix" scripts in the root suggests recent rapid iteration and bug fixing, particularly around the viewer and signing logic. However, the core package (`epi_core`, `epi_recorder`) appears stable and well-structured.

## 7. Conclusion
The EPI Recorder codebase is a sophisticated, well-engineered solution for AI accountability. It successfully solves the problem of "proving" what an AI did by combining transparent recording (via patching) with strong cryptographic guarantees (via Ed25519). The architecture is modular and extendable, with a clear path for adding new integrations or viewer features.
