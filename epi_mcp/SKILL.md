# EPI Evidence Sealing (MCP)

**Rule zero: never construct `.epi` bytes yourself.** If a tool call
fails, report the run as unsealed and stop. A hand-built artifact is
forgery; the verifier will mark it SIGNATURE INVALID, and you must
never present one as sealed.

Use these tools when the user asks to seal, verify, or inspect an agent run.
Do not narrate EPI methodology instead of calling the tools. Seal only
**caller-provided observable evidence** — never claim to capture the
entire run, hidden reasoning, or inaccessible system state.

No setup is required from the user: authentication arrives with the
call, and every seal is automatically bound to the caller's identity
via a per-caller key (created on first use). Never ask the user for
URLs, tokens, or key names.

## Tools

- `epi_seal_record(events, goal?, include_bytes?)` — seal events into a
  signed `.epi` file. Returns `artifact_id`, an expiring **download URL**
  (it carries its own secret, so it opens in a browser; 24 h), filename,
  SHA-256, a seal self-check, a **fidelity** report and **warnings**, and
  (unless `include_bytes=false`) the file as base64. The server path is
  meaningless outside the host. If the link has expired or the server
  restarted, the base64 bytes are the fallback.
- `epi_verify(epi_path)` — verify integrity, signature, identity, trust.
  Accepts the `artifact_id` from a seal.
- `epi_export_summary(epi_path, max_steps?)` — read back the timeline
  (also accepts `artifact_id`).
- `epi_compare_runs(epi_path_a, epi_path_b)` — diff two sealed
  timelines (deltas, decisions, first divergence). Compares records,
  never runs.

## Chat history mapping (use these step kinds)

Conversation runs:

| Chat element | Step kind | Content |
|---|---|---|
| User message | `user.message` | text (or its hash if private) |
| Assistant message | `assistant.message` | text |
| Uploaded file | `artifact.attached` | filename + SHA-256 |
| Generated file | `artifact.produced` | filename + SHA-256 |

Agent runs: `agent.run.start` → `tool.call` → `tool.response` →
`artifact.produced` → `agent.decision` → `agent.run.end`.
Timestamps come from the host record, never invented.

## What a good chat seal looks like

1. **Seal the thread the user asked about.** If the conversation mixes
   topics, ask which one before sealing.
2. **Verbatim, not paraphrase.** Pass each message's exact text with
   `fidelity: "verbatim"`. Use `"summary"` for anything you condensed and
   `"hash_only"` (with sha256) for private content. A paraphrase labelled
   verbatim is a false record.
3. **Real times.** Pass the host's timestamp per event as ISO-8601. If you
   do not have one, omit it: the server stamps its own receive time and
   labels it `server_received`. Never invent times. If every event ends
   up with the same time, the tool warns you; relay that warning.
4. **Declare omissions.** Redact with `[REDACTED]`. If you leave out a
   category of content (for example a third party's financial details),
   add a `redaction.omitted` event stating what kind and why. Silent
   omission makes the record look more complete than it is.
5. **Tell the user the truth afterwards:** the link, the SHA-256, every
   warning the tool returned, identity unpinned unless they trusted the
   key, and `epi verify <file>.epi` for an independent check.

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
before sealing. Mark every redaction with `[REDACTED]` — the server
tallies markers into `summary_counts.redactions`, so the count is
checkable against the sealed steps. If in doubt, replace the value
with `[REDACTED]` and note it.
