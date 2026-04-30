# EPI Forensic Truth Engine Viewer

`web_viewer/` is the browser-local forensic investigation app for portable `.epi` artifacts.
It powers the hardened "Truth Engine" architecture, providing a tamper-evident audit interface for AI execution records.

The interface is strictly evidence-first, optimized for forensic accountability and regulatory compliance (e.g., EU AI Act Article 12).

## Forensic Audit Model

The viewer organizes evidence into a structured, chronological record:

- **0.0 Summary**: The high-level verdict, trust status, and artifact metadata.
- **1.0 Governance**: The rulebook and policy evaluation results (the "Policy Evaluation").
- **2.0 Evidence_Log**: The bit-perfect chronological trace of execution steps.
- **3.0 Appendix**: The technical environment snapshot and raw manifest.

## Key Hardening Features

- **Official_Forensic_Record**: Every view is treated as an official audit document.
- **Bit-Perfect Integrity**: Uses browser-side JSZip and SHA-256 to verify payload integrity offline.
- **Cryptographic Binding**: Verifies Ed25519 signatures to bind agent identity to evidence.
- **Polyglot Envelope**: The `viewer.html` is embedded as a bootloader inside the `.epi` file itself.

## Investigation Flow

The viewer is designed to establish the "Ground Truth" of an AI interaction:
1. **Verification**: Can I trust this file? (Integrity & Signature)
2. **Governance**: What were the rules? (Policy Evaluation)
3. **Evidence**: What actually happened? (Chronological_Evidence_Log)
4. **Environment**: Where did it happen? (Execution_Environment)
