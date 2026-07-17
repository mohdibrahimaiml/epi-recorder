# EPI Enterprise Pivot: Master Project Documentation

## 1. Executive Summary: The "Trust Layer"
**EPI (Evidence Packaged Infrastructure)** has evolved from a developer utility ("The PDF for AI") into an **Enterprise Trust Platform**.

**The Core Pivot:**
*   **Old Strategy:** Sell a "Recorder" to developers. (Low friction, Low value)
*   **New Strategy:** Sell "Audit Insurance" to Enterprises. (Mid friction, High value)
*   **Value Proposition:** "Don't trust the AI. Trust the Record." EPI packages AI execution evidence into portable, cryptographically verifiable artifacts that can support compliance and audit workflows.

---

## 2. Market Analysis & Target Personas

### "Hair on Fire" Use Cases
1.  **Healthcare (MedTech):** FDA "Black Box" rejection. Need reproducible audit trails for 510(k) submissions.
2.  **Fintech (Lending):** Fair Lending (ECOA) audits. Need to prove *why* a loan was rejected to avoid CFPB fines.
3.  **Cyber Insurance:** Insurers need to verify if a client followed security protocols before paying ransomware claims.

### The Competition
*   **Observability (Datadog/LangSmith):** Strong for *debugging*, but not primarily designed for portable evidence packaging.
*   **EPI:** Immutable, signed, portable files (`.epi`) that support evidence review workflows.

---

## 3. System Architecture & Components

### A. The Recorder (`epi-recorder`)
*   **Role:** The "Black Box" installed in the application.
*   **Mechanism:** Explicit API (`log_llm_call`) & Wrappers.
*   **Output:** Generates a `.epi` file (ZIP container) containing:
    *   `manifest.json`: Metadata & SHA-256 hashes.
    *   `steps.jsonl`: Execution log.
    *   `viewer.html`: Embedded offline viewer.
*   **Security:** Signs the manifest using Ed25519 (high-speed elliptic curve cryptography).

### B. The Cloud Verifier (`verify.html`)
*   **Role:** The "Universal Reader" for auditors.
*   **Location:** `EPI WEBSITE` (User Desktop) & GitHub Pages.
*   **Tech Stack:** Pure Client-Side HTML/JS/WASM.
*   **Key Features (Implemented this Session):**
    *   **Drag-and-Drop:** Instant verification of signature & hash integrity.
    *   **Deep Audit:** A "File Manifest" table showing every file in the bundle and its hash.
    *   **Integrated Visualizer (Safe-View):** A security-hardened `iframe` sandbox that extracts and displays the embedded `viewer.html` without executing potentially malicious script in the parent context.
    *   **Privacy Model:** **Zero Data Exfiltration.** Verification happens entirely in browser memory.

### C. The Enterprise Gateway (`epi_gateway`)
*   **Role:** The "High-Volume" verifier for CI/CD.
*   **Architecture:** FastAPI Backend.
*   **Function:** Accepts `.epi` files via REST, verifies them asynchronously, and logs the result to a centralized audit log.
*   **Optimization:** Smart Batching to handle high-throughput streams.

### D. The CI/CD Hook (`epi-action`)
*   **Role:** "Invisible" enforcement.
*   **Implementation:** GitHub Action.
*   **Usage:** Runs in the build pipeline to automatically record/verify tests, ensuring no "unsigned" code ever hits production.

---

## 4. Technical Implementation Details

### The "Deep Audit" & "Visualizer" Upgrade
We enhanced the `verify.html` significantly to bridge the gap between "Trust" (Math) and "Understanding" (Visuals).

**1. File Manifest Viewer:**
*   **Problem:** Users saw a "Green Checkmark" but didn't know *what* files were inside.
*   **Solution:** Parsed the `manifest.json` and rendered a detailed table of `Filename | SHA-256 Hash`.
*   **Benefit:** Auditors can cross-reference file hashes with their source control.

**2. Integrated Visualizer (Safe-View):**
*   **Problem:** The `.epi` file contains a rich HTML viewer (charts, terminal logs), but the Verifier was just a static text page.
*   **Solution:**
    *   Extracted `viewer.html` from the ZIP blob in memory.
    *   Created a Blob URL.
    *   Loaded it into a full-screen modal `<iframe>` with `sandbox="allow-scripts"`.
*   **Benefit:** Users can now "Play" the evidence inside the Verifier, getting the best of both worlds: Independent Verification + Rich Visualization.

**3. Deployment Pipeline:**
*   Code committed to `c:\Users\dell\OneDrive\Desktop\EPI WEBSITE`.
*   Pushed to `origin/main` (GitHub) for live availability.

---

## 5. Deployment & Usage Guide

### How to Verify Evidence
1.  **Open** the Website: Go to `EPI WEBSITE/verify.html` (or the live URL).
2.  **Drag & Drop**: Drop any `.epi` file (e.g., `visualizer_evidence.epi`).
3.  **Check Status**:
    *   **Green:** Valid Signature + Valid Hash.
    *   **Yellow:** Valid Signature + Unknown Identity (Self-signed).
    *   **Red:** Invalid Signature or Tampered File.
4.  **Deep Dive**:
    *   Click **"View Files"** to audit the file list.
    *   Click **"View Evidence"** (Purple Button) to launch the rich visual player.

### How to Generate Evidence (For Testing)
Use the provided scripts in `epi-recorder`:
*   `python generate_clean_epi.py`: Creates a minimal, clean file (no viewer).
*   `python generate_visual_epi.py`: Creates a rich file with an embedded viewer for testing the Visualizer.

---

## 6. Project Artifact Checksums (Source of Truth)
*   **Strategy:** `PRODUCT_STRATEGY.md`, `TARGET_MARKET_ANALYSIS.md`.
*   **Audit:** `ANALYSIS_REPORT.md`.
*   **Plan:** `IMPLEMENTATION_PLAN.md`, `task.md`.
*   **Summary:** `SESSION_SUMMARY.md`.

**(End of Document)**
