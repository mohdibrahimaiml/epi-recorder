# EPI Evidence Sealer: MCP contract

For anyone building a plugin, app or skill on top of `https://epi-mcp.onrender.com/mcp`. Every statement here is taken from the server code (`epi_mcp/`, `epi_core/`). Where something is not built, it says so.

## 1. The honest answer to the hardest problem

**No host gives an MCP server the conversation.** A tool receives only the arguments the model writes into the call. ChatGPT and Claude do not pass a structured transcript, message ids, timestamps or tool results to a connector, and they do not tell the connector who the user is. This is a host limit, not something a manifest or skill file can remove.

What EPI does about it, in order of strength:

| Path | Who supplies the content | Strength |
| --- | --- | --- |
| **Upload an export** at `https://epi-mcp.onrender.com/seal` | The user, from the host's own export (Claude or ChatGPT zip/JSON). No model is involved. | Strongest. The record is the host's export, parsed by the server. The source file's name and SHA-256 are written into the first event. |
| **Model-supplied events** via `epi_seal_record` | The model, copying the chat into the call. | Honest but weaker. Every event carries a `fidelity` label (`verbatim`, `summary`, `hash_only`) and the file says `capture_scope: caller-provided`. |
| **Last answer only** (prompt `seal_last_answer`) | The model, sending one exchange. | Practical for long chats, where copying everything is slow or gets paused by the host. |
| A host or browser integration that reads the page | Not built. | Possible future work. |

A sealed file never claims more than this. It states that the record is what the caller supplied, lists `not_captured`, and warns when events have no caller timestamp or are summaries. A plugin must not describe a model-supplied seal as "the authoritative transcript".

## 2. Tools

Names, parameters and results are exact. Over the network a caller can name only files this server sealed, by `artifact_id`; file paths are refused.

### `epi_seal_record` (writes)

Annotations: `readOnlyHint=false`, `destructiveHint=false`, `idempotentHint=false`, `openWorldHint=false`.

| Parameter | Type | Notes |
| --- | --- | --- |
| `events` | array of objects, required | See section 3. At most 5000 events and 8 MiB. |
| `goal` | string, optional | Free text title of the record. |
| `include_bytes` | boolean, default true | Ignored for network callers when links exist; the file is not returned as text. |
| `output_path` | string or null | Local operator only. Ignored over the network. |

Result (fields that matter): `sha256`, `artifact_id`, `steps_sealed`, `scope` (`caller-provided`), `scope_note`, `fidelity` (`events`, `by_fidelity`, `caller_timestamps`, `server_assigned_timestamps`, `distinct_timestamps`, `warnings`), `seal_check` (`integrity_ok`, `signature_valid`, `trust_level`), `sealer_identity`, `view_url`, `download_url`, `share_text`, `download_expires_in_seconds`, `retention`, `warnings`, `summary_counts`, `signer_stability`, `how_to_verify`, `not_captured`, `sealed_at`.

Errors (plain text, nothing is sealed): `events must be a non-empty list`; `event N must be an object`; `Too many events (N > 5000)`; `Record too large`; `Storage quota reached for this caller`; `The server's temporary storage is full`.

### `epi_verify` (read-only)

Parameters: `artifact_id` (preferred) or `epi_path` (accepts the same id). Result: `integrity_ok`, `signature_valid`, `signer`, `verify_message`, `identity_status`, `trust_level`, `trust_message`, `mismatches` (map of file to problem).
Errors: `Pass the artifact_id returned by epi_seal_record`; `That sealed file is no longer on the server (files are kept for 24 hours)`.

### `epi_export_summary` (read-only) — inspect and read back

Parameters: `artifact_id` or `epi_path`, `max_steps` (default 50). Result: `steps_total`, `steps_shown`, `timeline[]` of `{index, kind, timestamp, content}`.

### `epi_compare_runs` (read-only)

Parameters: `artifact_id_a`, `artifact_id_b` (or `epi_path_a`, `epi_path_b`). Result: `run_a`, `run_b` (`steps`, `kinds`, `decisions`), `delta_steps`, `kinds_only_in_a`, `kinds_only_in_b`, `decisions_match`, `first_divergence_index`, `scope_note`.

### What does not exist

There is no separate "export" tool. The file is delivered by `download_url` (HTTP GET, expires after 24 hours) and opened by `view_url`. There is no replay or extract tool and no tool that returns the file as an MCP resource.

## 3. What goes into a record

An event is `{kind, content, timestamp?, fidelity?}`. The server keeps `content` as sent (a bare string becomes `{"text": ...}`), adds a hash-covered `_epi_provenance` block (`timestamp_source`, `received_at`, `fidelity`, and `caller_kind` if the kind was renamed) and a `_epi_capture` block, and chains the steps.

| Thing to capture | How it is recorded |
| --- | --- |
| User and assistant messages | `user.message`, `assistant.message`, `content.text` |
| Tool calls and results | `tool.call` (`tool`, `input`), `tool.response` (`result`) |
| Files in or out | `artifact.attached`, `artifact.produced` (`filename`, `sha256`). Bytes are not embedded. Send the hash. |
| System or developer instructions | Not part of the model-visible chat, so not captured. If left out on purpose, add a `redaction.omitted` event saying what and why. |
| Secrets | Replace with `[REDACTED]`. The server counts the marker in `summary_counts.redactions`. It does not detect secrets for you. |
| Images and large payloads | Send `fidelity: hash_only` with a `sha256`. |
| Model or provider, ids, retries, errors | No dedicated fields. Put them in `content` of an event (for example `custom` kinds); they are sealed as sent. |
| Intermediate reasoning | Not requested and not stored. |
| Timestamps | Only when the chat shows one. Otherwise the server records its own receive time and flags it. |
| Parallel tool calls | Recorded in the order sent; the chain is linear. |

Unambiguous near-miss kind names (`user_request`, `assistant_response`, `tool_call`, `tool_result`) are mapped to the canonical kinds. Other kinds are kept as sent.

An *agent run* uses the same events (`tool.call`, `tool.response`, `agent.decision`, `artifact.produced`). There is no separate run schema today.

## 4. Cryptographic semantics

- **Container:** `.epi` is `envelope-v2`: a polyglot of an HTML viewer and a ZIP, so the file opens in a browser and as an archive. It holds `manifest.json`, `steps.jsonl`, `environment.json`, `artifacts/manifest.json` and `viewer.html`.
- **Hash:** SHA-256.
- **Canonical serialization:** JSON Canonicalization Scheme (RFC 8785) for spec versions 4.4.1 and later. Older files use earlier canonicalizations and still verify.
- **Step chain:** `steps.jsonl` is hash-chained. The first step has `prev_hash = "CHAIN_START"`; every later step's `prev_hash` is the canonical hash of the previous step.
- **File integrity:** the manifest's `file_manifest` maps each file to its SHA-256.
- **Signature:** Ed25519 over the canonical hash of the manifest with its signature field excluded. Format: `ed25519:<keyname>:<hex signature>`, where `keyname` is the first 16 hex characters of SHA-256 of the public key's hex.
- **Public key:** the 32-byte key is embedded in the manifest as hex. Verification needs no server.
- **Signer keys:** the hosted server derives a separate signing key per approved caller from a server secret, so the signer is stable across restarts. Trust is local: a verifier pins a signer with `epi keys trust`. Until then the result is `trust_level: LOW` with a message that the signer is not pinned.
- **Identity:** an optional `sealer_identity` block in the signed `environment.json` (`method`: `pseudonymous`, `oidc` or `github`). It says what the sealing server saw; it never proves who typed the conversation.
- **Trusted time:** a hash of the step list is sent to an RFC 3161 service (FreeTSA) when it answers within the server's timeout. The token is stored in the file. Verification reports that it is present; it does not yet validate the token's signature. If the service does not answer, the seal succeeds with a warning and only the server's receive time.
- **Failure semantics:** `integrity_ok` false means a file does not match its recorded hash (`mismatches` names it); `signature_valid` false means the manifest or key does not match the signature. Either makes the file fail `epi verify`.

## 5. Delivery and verification

- Delivery is by link: `view_url` (browser view, nothing to install) and `download_url`. Both carry an unguessable `?t=` token and stop working after 24 hours; the server then deletes its copy. `share_text` holds the links and hash exactly as they work. A plugin should show them verbatim and must not rebuild a link from the SHA-256.
- A sealed file verifies offline with `epi verify record.epi` or at `https://epilabs.org/verify`. No EPI server is needed.
- Verification on the server is a separate call. The seal result already contains a self-check (`seal_check`), but a plugin that wants an independent confirmation should call `epi_verify` with the `artifact_id`.
- Verify reports integrity and signature, not "37 messages, 14 tool calls". Counts come from `summary_counts` in the seal result and from `epi_export_summary`.

## 6. Authentication

- MCP endpoint: `https://epi-mcp.onrender.com/mcp` (Streamable HTTP).
- An unauthenticated request gets `401` with `WWW-Authenticate` pointing to `/.well-known/oauth-protected-resource`.
- Protected resource: `/.well-known/oauth-protected-resource` (also the `/mcp` suffixed form). Authorization server: `/.well-known/oauth-authorization-server` (also suffixed).
- Dynamic client registration: `POST /oauth/register`. Clients are public (`token_endpoint_auth_method: none`).
- Authorization: `GET /oauth/authorize`, PKCE `S256` required, response type `code`, scopes `seal verify export`. The person clicks Approve; signing in with GitHub is optional. The RFC 8707 `resource` parameter is accepted and ignored.
- Token: `POST /oauth/token`, grants `authorization_code` and `refresh_token`. Access tokens last 30 days; refresh tokens 90 days and rotate on use.
- A plugin file must not contain credentials. The host runs this flow itself.

## 7. Behaviour a plugin should follow

- Say "sealed" only when `epi_seal_record` returned a result with `seal_check.integrity_ok` and `seal_check.signature_valid` true. On any error, say nothing was sealed.
- Never hand-build a `.epi` or a link. Only the server signs.
- Show warnings. Do not hide that a record is model-supplied or summarised.
- Leave out or mark `[REDACTED]`: API keys, tokens, passwords, cookies, private keys, authorization headers, environment secrets.
- Do not re-seal on a loop. The server is **not idempotent**: sealing the same content twice gives two different files, because each carries its own workflow id and times. Duplicate detection (a source run id and evidence root hash) is not built.
- Ids: each file has a `workflow_id` (UUID in the manifest), an `artifact_id` (16 hex characters, valid for 24 hours) and a signer key id.

## 8. Intents to tool calls

| User says | Do |
| --- | --- |
| "Seal this conversation / run" | `epi_seal_record`, then show `share_text` and the warnings |
| "Seal your last answer" | `epi_seal_record` with the last exchange only |
| "Verify this" | `epi_verify` |
| "What happened in this run?" / "Show failed tool calls" / "Give me the manifest" | `epi_export_summary`, then summarise from the returned timeline |
| "Compare these two" | `epi_compare_runs` |
| "I have a chat export" | Point to `https://epi-mcp.onrender.com/seal` |

## 9. Testing status

Automated: seal, verify, read-back and compare over a real HTTP server with OAuth; tamper detection; large records; unicode; odd event names; slow timestamp service; quotas; a replay of ChatGPT's documented connection steps. Not done: a real ChatGPT account connecting end to end, and an interactive viewer inside the host (the `view_url` page opens in a browser instead).
