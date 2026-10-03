# EPI Evidence Sealing (MCP)

Use these tools when the user asks to seal, verify, or inspect an agent run.
Do not narrate EPI methodology instead of calling the tools. Seal only
**caller-provided observable evidence** — never claim to capture the
entire run, hidden reasoning, or inaccessible system state.

## Tools

- `epi_seal_record(events, goal?, output_path?)` — seal execution events
  into a signed `.epi` file. Returns the **file bytes (base64)**,
  filename, SHA-256, and an immediate seal self-check. Hand the file to
  the user as a download; the server path is meaningless outside the host.
- `epi_verify(epi_path)` — verify integrity, signature, identity, trust.
- `epi_export_summary(epi_path, max_steps?)` — read back the timeline.

## Capture-scope rules (never overclaim)

1. Pass **only material this run actually exposed**: user task, tool calls
   you invoked, tool results you received, artifacts you produced.
2. Never claim to seal hidden chain-of-thought or inaccessible model state.
3. The seal proves the provided record was not altered after sealing. It
   does not prove the record is complete — say so when asked.
4. Seal / identity / coverage are three different questions:
   - seal = integrity + signature (this plugin),
   - identity = who holds the signing key (`epi keys trust` on the
     recipient side, out of scope here),
   - coverage = whether everything was recorded (depends on what events
     were passed in, not on cryptography).

## Redaction

Remove API keys, tokens, passwords, and personal data from event content
before sealing. If in doubt, replace the value with `[REDACTED]` and note it.
