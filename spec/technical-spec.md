# Execution Proof Infrastructure (EPI) Specification v1.0

The EPI format provides a standardized envelope for recording, cryptographically signing, and distributing AI/Agent workflows. By separating the conceptual metadata from the physical artifacts, EPI achieves language-agnostic portability while maintaining cryptographically sound auditability.

## 1. Archive Structure

An `.epi` file is a standard ZIP archive (no compression required by default, but DEFLATE is supported). It must contain the following structure:

```text
recording.epi/
├── mimetype               # MUST be first file, uncompressed, value: "application/vnd.epi+zip"
├── manifest.json          # Global index, integrity hashes, and metadata
├── steps.jsonl            # Ordered timeline of events (LLM calls, tool usage)
├── env.json               # Platform and environment context (optional)
├── viewer.html            # Universal fallback UI for viewing the recording
└── artifacts/             # Directory containing supplementary files (e.g. outputs, logs)
```

## 2. Global Manifest (`manifest.json`)

The manifest acts as the central source of truth for the archive. It is defined by the JSON Schema `epi-spec-v1.json`.

Key Requirements:
*   `spec_version`: Identifies the specification version. Currently `"2.6.0"` in existing Python clients, formalizing to `"1.0.0"` in standard cross-language definitions.
*   `file_manifest`: A dictionary mapping relative paths within the archive to their SHA-256 hashes.
*   **Metadata Fields**: `goal`, `notes`, `metrics`, `tags`, `approved_by` provide semantic context for tracing systems and querying.

## 3. Timeline Events (`steps.jsonl`)

The `steps.jsonl` file uses Newline Delimited JSON (NDJSON). Each line represents an immutable event in the workflow.

Required fields per line:
*   `index` (integer): Sequential step number, 0-indexed.
*   `timestamp` (string, ISO 8601): UTC timestamp of the event.
*   `kind` (string): Categorical type (e.g., `"llm.request"`, `"shell.command"`).
*   `content` (object): Event-specific payload.

### Tracing Standard (W3C context)
To support distributed tracing integration in future iterations, any step MAY include the following tracing properties either at the top-level or within `content`:
*   `trace_id`: The global execution trace identifier.
*   `span_id`: The specific identifier for this step's operation.
*   `parent_span_id`: The span that triggered this execution.

## 4. Cryptographic Trust

When an `.epi` package is signed, the `manifest.json` acts as the root of trust.

1.  **File Hashing**: Every tracked file in the archive (except `manifest.json` and `viewer.html` which embeds it) is hashed via SHA-256. These hashes are stored in `manifest.file_manifest`.
2.  **Canonicalization**: The `manifest.json` is stripped of its `signature` property and converted into a canonical CBOR payload to ensure consistent byte representation.
3.  **Signing**: An Ed25519 signature is generated over the CBOR payload.
4.  **Embedding**: The resulting public key (hex) and signature (hex prefixed with `ed25519:`) are re-injected into the `manifest.json`.

If ANY tracked artifact or step is modified, the SHA-256 hash in `manifest.json` will fail to match. If `manifest.json` is tampered with, the Ed25519 signature will fail validation against the `public_key`.
