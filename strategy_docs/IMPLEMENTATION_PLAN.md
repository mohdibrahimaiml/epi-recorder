# EPI Enterprise Implementation Plan (Revised)

## Goal
Execute the "Web-First" production strategy to maximize trust and adoption while minimizing distribution friction and engineering risk.

## Phase 1: The "Visual" Trust (Web Verifier)
*Objective: "Viral Truth". Enable anyone to verify an .epi file in 3 seconds via a URL, with zero installation.*

### 1.1 The "Dropzone" Web App (`verify.epilabs.org`)
- [ ] **Architecture**: Static Single Page App (SPA). Zero backend.
- [ ] **Stack**: HTML5, Vanilla JS (or lightweight framework), Web Crypto API.
- [ ] **Core Features**:
    - [ ] **Drag & Drop**: Instant file parsing.
    - [ ] **Client-Side Unzip**: Use `JSZip` to extract manifest in memory.
    - [ ] **Browser Verification**: Implement Ed25519 verification using `SubtleCrypto` or `tweetnacl.js`. **Crucial**: Private data never leaves the browser.
    - [ ] **"The Badge"**: Animated Green Checkmark if signature matches.
    - [ ] **"Redacted View"**: Show non-sensitive metadata (Cost, Model, Timestamp) by default.

## Phase 2: The "Invisible" Hook (CI/CD)
*Objective: "Automatic Content". Build the library of .epi files without changing production code.*

### 2.1 The GitHub Action
- [ ] **Action**: `epi-record-action`
- [ ] **Logic**:
    - [ ] Sets up python environment.
    - [ ] Injects `sitecustomize.py`.
    - [ ] Runs user's test suite.
    - [ ] Uploads `.epi` artifacts to GitHub Actions Summary.
- [ ] **Value**: Developers get "Evidence" for every Pull Request automatically.

## Phase 3: The "Gateway" Moat (Enterprise Only)
*Objective: "Production Governance". High-reliability control for Banks.*

### 3.1 The Async Sidecar
- [ ] **Architecture**: Non-blocking logger.
- [ ] **Deployment**: Docker container running alongside the App.
- [ ] **Mode**: "On-Prem / VPC" (Runs in *their* cloud).
- [ ] **Function**: Captures keys/requests locally, signs them, and batches upload to storage. simpler and safer than a synchronous proxy.

## Execution Strategy
1.  **Kill the Desktop App**: Stop work on Electron. It's too much friction.
2.  **Focus on JS Cryptography**: The hardest part of Phase 1 is ensuring the JS verification matches the Python signing exactly (Canonical JSON, Ed25519).
3.  **Ship `verify.html`**: A single portable HTML file that can also be hosted.
