# EPI-Recorder V4.2.0 — Complete Technical Documentation

> **One file. One signature. 100% offline verification.**
> EPI captures AI agent decisions into portable, cryptographically sealed `.epi` containers.

---

**Version**: 4.2.0 | **License**: MIT | **Python**: 3.11+ | **PyPI**: `epi-recorder` | **Tests**: 1300+

---

## 1. Project Overview

EPI (Evidence Portable Image) is an open-source framework for capturing, signing, verifying, and sharing AI agent execution traces. It acts as the PDF equivalent for AI evidence — a single, self-verifying file format storing the complete decision trail of an AI workflow.

**Repository**: https://github.com/mohdibrahimaiml/epi-recorder

### Core Value Proposition
- **Capture**: 3 lines of Python wrap any OpenAI/Anthropic/LangChain call
- **Seal**: Ed25519-signed container with SHA-256 integrity
- **Share**: Email, local network, or hosted gateway
- **Verify**: Offline — no server call required
- **Audit**: SCITT transparency, AIUC-1 scoring, compliance mapping

---

## 2. Architecture

### Component Layers

| Layer | Package | Responsibility |
|-------|---------|----------------|
| CLI | `epi_cli` | 30+ Typer commands, terminal output, auto-setup |
| Python SDK | `epi_recorder` | Runtime interception, wrappers, recording sessions |
| Core Engine | `epi_core` | Container mgmt, schemas, crypto, policy, SCITT |
| Web Portal | `verify_portal/` | Static web app for browser verification |
| Browser Ext | `src/extension/` | Chrome extension for web AI capture |

### Data Flow

```
User Code → epi_cli (CLI) → epi_recorder (SDK) → epi_core (Engine) → .epi (Container)
```

---

## 3. Package: epi_cli — CLI Application

Built with **Typer** (Click-based). Entry: `cli_main()` → `app()`.

### Frictionless First-Run System
- `epi demo` works with no API key
- First `epi run/record/init` auto-generates Ed25519 keys
- `epi view/run/init/doctor` auto-registers Windows .epi association
- Self-healing via `epi doctor`

### Complete Command Reference

| Command | Module | Description |
|---------|--------|-------------|
| `epi demo` | dev.py | 60-second demo: capture, verify, open |
| `epi dev` | dev.py | Alias for demo |
| `epi init` | main.py | Setup wizard: keys + demo script + run |
| `epi run <script>` | run.py | Record instrumented Python script |
| `epi record --out <file>` | record.py | Advanced recording |
| `epi view <file>` | view.py | Open browser viewer |
| `epi verify <file>` | verify.py | 10-pass verification |
| `epi export-html <file>` | view.py | Standalone HTML export |
| `epi export-summary <file>` | export_summary.py | Human-readable summary |
| `epi export agt <file>` | main.py | AGT format export |
| `epi share <file>` | share.py | Upload share link |
| `epi review <file>` | review.py | Add human review |
| `epi analyze <file>` | main.py | Fault analysis summary |
| `epi debug <file>` | debug.py | Mistake detection |
| `epi chat <file>` | chat.py | AI-powered evidence chat |
| `epi ls` | ls.py | List local recordings |
| `epi connect open` | connect.py | Team review workspace |
| `epi gateway serve` | gateway.py | Team capture proxy |
| `epi keys generate/list/export/trust/revoke` | keys.py | Key management |
| `epi policy init/validate/explain` | policy.py | Policy management |
| `epi import agt <file>` | importer.py | Import AGT evidence |
| `epi scitt register/verify` | scitt.py | SCITT transparency |
| `epi agt ...` | agt_cmd.py | AGT adapter commands |
| `epi audit <file>` | audit.py | Self-audit compliance |
| `epi identity register/export/import` | identity.py | Identity map |
| `epi global install/uninstall` | install.py | Global auto-recording |
| `epi associate/unassociate` | main.py | Windows file association |
| `epi migrate` | main.py | Convert container formats |
| `epi refresh-viewer` | main.py | Regenerate embedded viewer |
| `epi integrate` | integrate.py | Generate integration examples |
| `epi version` | main.py | Show version |
| `epi help` | main.py | Extended help |
| `epi status` | main.py | Project health |
| `epi doctor` | main.py | Self-healing health check |
| `epi telemetry status/enable/disable` | telemetry.py | Telemetry |
| `epi join-pilot` | main.py | Pilot signup |
| `epi auth login/logout/status` | auth_cmd.py | Cloud identity |

### Key Command Internals

**`epi verify`** — 10-pass check:
1. Container format (envelope-v2 or legacy-zip)
2. MIME type validation
3. SHA-256 integrity (every file in manifest)
4. Ed25519 signature validation
5. Identity check (known/root/unknown/revoked)
6. prev_hash chain integrity (step linked list)
7. Policy rule evaluation
8. SCITT receipt verification (if present)
9. AIUC-1 6-domain scoring (if --aiuc1)
10. Human review ledger (if --review)

Output: `TRUSTED` | `WARN` | `FAILED` | `ERROR`

**`epi view`**: Resolves .epi by path → `./epi-recordings/` → `~/.epi/recordings/`. Opens browser viewer by default.

**`epi doctor`**: 8 checks (keys, disk, perms, recordings dir, gateway storage, deps, PATH, gateway connectivity). Auto-fixes key generation, PATH, registry.

**`epi init`**: Wizard → key generation → framework-specific demo script → optional GH Actions workflow → run demo → report metrics.

---

## 4. Package: epi_core — Core Engine

### 4.1 `container.py` — EPIContainer

Central class managing `.epi` file lifecycle. Two container formats:

**Legacy ZIP** (`legacy-zip`): Standard ZIP archive. First entry must be `mimetype` (stored, uncompressed). MIME: `application/vnd.epi+zip`.

**Envelope v2** (`envelope-v2`): Polyglot HTML+ZIP. 128-byte binary header, embedded viewer HTML, then ZIP payload after `<!-- EPI_ZIP_PAYLOAD_START -->` marker. Opens natively in any browser. MIME: `application/vnd.epi`.

**Envelope Header Structure (128 bytes)**:
- Magic `<!--` (4), Version (1), Payload Format (1), Reserved Flags (2)
- Payload Length (8), Artifact UUID (16), Created At Micros (8)
- Payload SHA-256 (32), Reserved (56)

**Key Methods**: `pack()`, `unpack()`, `read_manifest()`, `read_steps()`, `read_step()`, `count_steps()`, `read_member_json/text/bytes()`, `list_members()`, `verify_integrity()`, `detect_container_format()`, `container_mimetype()`, `extract_inner_payload()`, `extract_embedded_viewer()`, `migrate()`, `refresh_viewer()`, `add_review()`.

### 4.2 `schemas.py` — Core Models (Pydantic v2)

**ManifestModel** (Root of Trust):
- `workflow_id` (UUID), `workflow_name`, `created_at` (datetime)
- `spec_version`, `format_version`, `container_format`
- `public_key`, `signature` (Ed25519, base64)
- `file_manifest` (dict[str, str] — SHA-256 per file)
- `source`, `governance`, `trust`, `scitt` metadata
- `total_steps`, `analysis_status`, `analysis_error`
- `viewer_version`, `prev_hash`, `cli_command`, `user`, `hostname`

**StepModel** (Execution Step):
- `kind` (str), `timestamp` (ISO-8601), `content` (dict)
- `index` (int), `prev_hash` (SHA-256 of prev step), `hash` (SHA-256 of this step)
- `source`, `tags`

### 4.3 `policy.py` — Policy Engine

Governance rules from `epi_policy.json`.

**EPIPolicy**: `policy_id`, `policy_version`, `rules[]`, `description`, `metadata`

**PolicyRule**: `rule_id`, `rule_name`, `severity` (critical/high/medium/low), `mode` (detect/block/warn), `conditions[]`, `action`, `description`

Functions: `load_policy()`, `EPIPolicy.validate()`, `EPIPolicy.model_validate_json()`.

### 4.4 `fault_analyzer.py` — Fault Intelligence

9-pass analysis evaluating steps.jsonl against policy rules.

```python
FaultAnalyzer(policy=policy).analyze(steps_jsonl)
→ FaultAnalysisResult: fault_detected, primary_fault, secondary_flags,
  coverage, verdict_short, mode (policy/heuristic_only)
```

### 4.5 `scitt.py` / `local_scitt.py` — SCITT Transparency

Implements IETF SCITT draft:
- COSE_Sign1 statements over Ed25519
- Merkle inclusion proofs
- Local SQLite service (no network)
- Remote service compatible

### 4.6 `redactor.py` — Secret Redaction

HMAC-SHA256 token replacement for API keys, secrets, PII. Scans all step content, replaces with `[REDACTED:<hash_prefix>]`. Deterministic per secret value.

### 4.7 `trust.py` — Trust Registry

- `VerificationPolicy`: `PERMISSIVE` | `STANDARD` | `STRICT`
- `TrustRegistry`: lookup, verify, revoke
- Trust levels: `ROOT` (root key), `KNOWN` (in registry), `UNKNOWN`, `REVOKED`

### 4.8 Other Core Modules

- **`telemetry.py`**: PostHog anonymous telemetry, `track_event()`, `get_install_id()`
- **`review.py`**: Human review ledger (mutable, not in file_manifest)
- **`serialize.py`**: `get_canonical_hash()` — deterministic SHA-256
- **`capture.py`**: CaptureBatchModel, CaptureEventModel
- **`case_store.py`**: Case storage models
- **`viewer_assets.py`**: Load/inline viewer HTML/JS/CSS from package
- **`workspace.py`**: Recording workspace tempdir creation with fallbacks
- **`aiuc1_mapping.py`**: 6-domain AIUC-1 scoring (A-F)
- **`auth_local.py`**: Local sign-in token management
- **`did_web.py`**: DID:WEB resolution for enterprise trust
- **`connectors.py`**: Gateway/bridge connector primitives
- **`platform/associate.py`**: Windows registry management (.epi → EPIRecorder.File)
- **`_version.py`**: Single version source: `get_version()` → `"4.2.0"`

---

## 5. Package: epi_recorder — Python SDK

### 5.1 Public API

```python
from epi_recorder import record, get_current_session, wrap_openai, wrap_anthropic
```

### 5.2 `api.py` — Recording API

```python
with record("agent.epi", goal="Process loan") as session:
    response = client.chat.completions.create(...)
    session.log_step("agent.decision", {"decision": "approved"})
    session.log_tool_call("Calculator", input="23*17", output="391")
    session.capture()
```

**EpiRecorderSession**: `log_step()`, `log_tool_call()`, `log_llm_call()`, `capture()`, `add_metadata()`, `set_goal()`, `set_workflow_name()`.

### 5.3 `wrappers/` — Client Wrappers

| File | Class | Function |
|------|-------|----------|
| base.py | TracedClientBase | Generic interceptor |
| openai.py | TracedOpenAI | `wrap_openai(OpenAI())` |
| anthropic.py | TracedAnthropic | `wrap_anthropic(Anthropic())` |

Captures: full request, response, streaming chunks, tool calls, timing.

### 5.4 `step_types.py` — Type Constants

`llm.call`, `tool.call`, `tool.output`, `agent.decision`, `session.start`, `session.end`, `agent.run.error`, `user.input`, `human.approval`, `file.write`, `calculation`, `summary`, `stdout.print`, `agent.step`.

### 5.5 Integrations

| Integration | File | Class/Function | Usage |
|-------------|------|----------------|-------|
| LangChain | `integrations/langchain.py` | `EPICallbackHandler` | `callbacks=[EPICallbackHandler()]` |
| LangGraph | `integrations/langgraph.py` | `EPICheckpointSaver` | Graph checkpointer |
| LiteLLM | `integrations/litellm.py` | `EPICallback` | `litellm.callbacks = [EPICallback()]` |
| OpenAI Agents | `integrations/openai_agents.py` | `EPIAgentHooks` | Agent lifecycle hooks |
| OpenTelemetry | `integrations/opentelemetry.py` | `setup_epi_tracing()` | Bridge OTel spans → EPI |
| Guardrails | `integrations/guardrails.py` | Auto-detect | Captures validation results |
| AGT Import | `integrations/agt_adapter/` | `Importer`, `Detector` | `epi import agt` |
| AGT Export | `integrations/agt/` | `export_workspace_to_agt()` | Embedded AGT in .epi |

**AGT Adapter** (`integrations/agt_adapter/`):
- `detect.py`: Auto-detects AGT format (JSON, JSONL, CloudEvents, bundle, directory)
- `importer.py`: Full import pipeline AGT → .epi
- `exporter.py`: Native AGT export
- `schemas.py`: AGT schema definitions
- `transforms.py`: AGT → EPI field mapping
- `compat.py`: Backward compatibility shims
- `errors.py`: AGT-specific errors
- `mapping_report.py`: Field-level mapping docs

### 5.6 Other SDK Modules

- **`auto.py`**: `auto.install()` monkey-patches OpenAI/Anthropic globally
- **`auto_scitt.py`**: Auto-SCITT registration on artifact seal
- **`environment.py`**: Runtime snapshot (hostname, Python, deps, env vars)
- **`patcher.py`**: `patch_module()`, `patch_instance_method()`, `RestoreContext`
- **`trust/engine.py`**: Trust evaluation engine
- **`trust/interceptor.py`**: Real-time request interception
- **`trust/approval.py`**: Human-in-the-loop approval
- **`analytics/engine.py`**: AgentAnalytics (pandas-powered)

---

## 6. Container Format: The .epi File

### 6.1 Internal Structure

```
.epi/
├── mimetype                    # "application/vnd.epi+zip" (MUST be first, stored)
├── manifest.json               # Root of trust: Ed25519-signed, SHA-256 file manifest
├── steps.jsonl                 # Immutable timeline: JSONL with prev_hash linked list
├── environment.json            # Runtime snapshot (hostname, Python, deps, env)
├── analysis.json               # 9-pass fault analysis results
├── policy.json                 # Governance policy (epi_policy.json)
├── policy_evaluation.json      # Rule-by-rule evaluation results
├── review.json                 # Human review ledger (mutable — not in file_manifest)
├── review_index.json           # Review index (mutable)
├── viewer.html                 # Self-contained offline browser viewer
├── VERIFY.txt                  # Plain-text verification guide
├── stdout.log, stderr.log      # Captured output (if streaming captured)
├── artifacts/scitt/            # SCITT receipts (COSE_Sign1 + Merkle proof)
├── artifacts/sbom/             # CycloneDX SBOM (if preserved)
└── artifacts/agt_export.json   # AGT-format export (if embed_agt=True)
```

### 6.2 Step Timeline (Cryptographic Linked List)

```
Step 0: {index:0, kind:"session.start", hash:"abc123", prev_hash:null}
Step 1: {index:1, kind:"llm.call", content:{...}, hash:"def456", prev_hash:"abc123"}
Step 2: {index:2, kind:"tool.call", content:{...}, hash:"ghi789", prev_hash:"def456"}
```

Each step's SHA-256 is the `prev_hash` of the next. Insertion, deletion, or reordering breaks the chain.

### 6.3 Viewer Embedding

viewer.html is self-contained: no server, no internet, no dependencies. Uses Web Crypto API for client-side signature verification. Supports dark/light mode, step filtering, search.

---

## 7. Cryptography & Security Model

### 7.1 Algorithms

| Function | Algorithm | Standard |
|----------|-----------|----------|
| Integrity | SHA-256 | FIPS 180-4 |
| Signing | Ed25519 | RFC 8032 |
| SCITT | COSE_Sign1 | IETF draft |
| Redaction | HMAC-SHA256 | FIPS 198-1 |

### 7.2 Threat Model

| Threat | Mitigation |
|--------|------------|
| Post-seal tampering | SHA-256 manifest + Ed25519 signature over canonical JSON |
| Evidence replay | Unique workflow_id per artifact + created_at timestamp |
| Secret leakage | HMAC-SHA256 redaction — secrets never in plaintext on disk |
| Signature spoofing | Strict `ed25519:<key>:<sig>` format enforcement |
| Step manipulation | prev_hash cryptographic chain — breaks on insert/remove/reorder |
| Key compromise | `epi keys revoke <name>` — revocation files in `~/.epi/revoked_keys/` |
| Visual deception | viewer.html hash in file_manifest — UI swap detected by verify |
| File injection | `verify_integrity()` checks for extra files not in manifest |
| SCITT fraud | Merkle inclusion proof — tampering breaks the tree |

### 7.3 Key Management

| Item | Location |
|------|----------|
| Default keypair | `~/.epi/keys/default/private_key.pem`, `public_key.pem` |
| Trust registry | `~/.epi/trusted_keys/<name>.pub` |
| Revocation | `~/.epi/revoked_keys/<name>.revoked` |
| Format | Ed25519 raw 32-byte, base64-encoded |

Trust levels: `ROOT` (named "root"), `KNOWN` (in registry), `UNKNOWN`, `REVOKED`.

---

## 8. Storage & Persistence

```
~/.epi/
├── keys/default/              # Ed25519 keypair
├── trusted_keys/              # Trusted public keys
├── revoked_keys/              # Revoked key markers
├── recordings/                # Global recording cache
├── shares/                    # Local share output
├── state/                     # CLI state markers
├── identity_map.json          # Agent name → DID mapping
├── telemetry.json             # Telemetry consent
├── telemetry_install_id      # Anonymous install ID
├── pilot_signup.json          # Local pilot signup mirror
├── scitt_ledger.sqlite3       # Local SCITT transparency ledger
└── auth/token.json             # EPI Cloud auth token

./epi-recordings/               # Project-level recordings
./evidence_vault/                # Gateway storage
├── cases.sqlite3               # Gateway case index
└── artifacts/                  # Gateway artifacts
```

---

## 9. Build & Deployment

### 9.1 Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| typer | >=0.12.0 | CLI framework |
| rich | >=13.0.0 | Terminal formatting |
| pydantic | >=2.8.0 | Data models |
| cryptography | >=42.0.0 | Ed25519 signing |
| cbor2 | >=5.6.0 | Canonical CBOR hashing |
| requests | >=2.32.0 | HTTP (share, telemetry) |
| posthog | >=3.4.0 | Anonymous telemetry |
| pywin32 | >=306 (win32) | Windows registry |

Optional: `fastapi+uvicorn` (gateway), `litellm`, `langchain`, `openai`, `anthropic`, `pandas`.

### 9.2 Installation

```bash
pip install epi-recorder
pip install "epi-recorder[integrations]"
pip install "epi-recorder[gateway]"
```

### 9.3 Entry Points

- CLI: `epi` → `epi_cli.main:cli_main`
- Module: `python -m epi_cli`
- SDK: `from epi_recorder import record, wrap_openai, wrap_anthropic`

### 9.4 Windows Platform

- **Standalone installer**: Recommended for double-click .epi support
- **pip + `epi associate`**: Per-user file association (HKCU)
- **`epi associate --system`**: System-wide (HKLM, requires admin/UAC)
- Registry: `HKCU\Software\Classes\.epi` → `EPIRecorder.File`
- Auto-repair runs on every `epi view/run/init/doctor` invocation
- UTF-8 console patched in `cli_main()`

---

## 10. Integrations

| Integration | Type | Mechanism | Status |
|-------------|------|-----------|--------|
| OpenAI | SDK wrapper | `wrap_openai()` | ✅ |
| Anthropic | SDK wrapper | `wrap_anthropic()` | ✅ |
| LangChain | Callback | `EPICallbackHandler` | ✅ |
| LangGraph | Checkpoint saver | `EPICheckpointSaver` | ✅ |
| LiteLLM | Callback | `EPICallback` (100+ providers) | ✅ |
| pytest | Plugin | `pytest --epi` | ✅ |
| OpenTelemetry | Bridge | `setup_epi_tracing()` | ✅ |
| OpenAI Agents SDK | Hooks | `EPIAgentHooks` | ✅ |
| Guardrails AI | Step capture | Auto-detected | ✅ |
| Microsoft AGT | Format adapter | `epi import agt` | ✅ |
| FastAPI | Server proxy | `epi gateway serve` | ✅ |

**pytest**: `--epi` generates .epi per test. `--epi-store-failed` keeps only failures.

**Gateway (FastAPI)**: Acts as proxy for AI API calls. Supports OAuth2/GitHub auth, configurable retention, SIEM webhooks.

---

## 11. Standards Compliance

### SCITT (IETF draft-ietf-scitt-scrapi)
- COSE_Sign1 statements over Ed25519
- Merkle inclusion proofs
- Local SQLite or remote service
- Raises trust level: `TRANSPARENCY: VERIFIED` → LOW→MEDIUM

### AIUC-1 — 6 Domains

| Domain | Letter | Check | Evidence Required |
|--------|--------|-------|-------------------|
| Data & Privacy | A | Redaction quality, env snapshot | environment.json |
| Security | B | Signature, integrity | Signed manifest |
| Safety | C | Step integrity chain | prev_hash linked timeline |
| Reliability | D | Error handling | Error step detection |
| Accountability | E | Human review binding | Signed review.json |
| Society | F | Analysis findings | analysis.json |

### Regulatory Mapping

| Regulation | EPI Coverage |
|------------|--------------|
| EU AI Act Art. 12 (Logs) | steps.jsonl + environment.json |
| EU AI Act Art. 14 (Human oversight) | review.json (signed approval) |
| EU AI Act Art. 19 (10yr retention) | Self-contained .epi (format-stable) |
| FDA 21 CFR Part 11 | Signed steps + Ed25519 signatures |
| HIPAA § 164.312 (Non-repudiation) | Ed25519 signature over manifest |
| NIST AI RMF | policy.json + analysis.json |
| AIUC-1 | 6-domain scoring |
| SCITT (IETF) | COSE_Sign1 + Merkle proof |

---

## 12. Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EPI_RECORDINGS_DIR` | `./epi-recordings` | Local recording output |
| `EPI_GATEWAY_STORAGE_DIR` | `./evidence_vault` | Gateway storage |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `EPI_TELEMETRY_OPT_OUT` | — | Set to `1` to disable telemetry |
| `TMP`/`TEMP` | System temp | Recording workspace temp |

### epi_policy.json

Created by `epi policy init`. Contains: `policy_id`, `policy_version`, `rules[]`.

Each rule: `rule_id`, `rule_name`, `severity`, `mode` (detect/block/warn), `conditions[]`.

### ~/.epi/identity_map.json

Maps agent names to DIDs: `{"my-agent": "did:key:z6Mk..."}`

---

## 13. Testing

- **1300+ passing tests** on GitHub Actions
- **pytest** framework with coverage reporting
- Covers: CLI commands, container format, crypto, policy, fault analysis, SCITT, AIUC-1, Windows association, all integrations, AGT adapter, secret redaction

```bash
pytest                             # All tests
pytest tests/test_verify.py        # Specific area
pytest --cov=epi_core --cov=epi_recorder --cov=epi_cli
```

---

## 14. Web Portal (Verify Portal)

Static web app at `verify_portal/`:

| Page | File | Purpose |
|------|------|---------|
| Landing | `index.html` | Main portal, file upload |
| Verify | `static/verify.html` | Online verification at verify.epilabs.org |
| Workspace | `static/workspace.html` | Team review workspace |
| SCITT | `static/scitt.html` | SCITT standard docs |
| AIUC-1 | `static/aiuc1.html` | AIUC-1 compliance docs |
| AGT | `static/agt.html` | AGT integration docs |

Features: drag-and-drop upload, client-side Web Crypto verification, step explorer, QR codes, share links.

---

## 15. Browser Extension

`src/extension/`: Chrome extension for capturing web-based AI interactions.

| File | Purpose |
|------|---------|
| manifest.json | Extension manifest (MV2/MV3) |
| background.js | Background service worker |
| popup.html | Extension popup UI |
| src/contents/content.js | Page injection |
| src/background/recorderBackground.js | Recording logic |
| src/utils/index.js | Utilities |
| src/viewer/ | Embedded viewer UIs |

Captures from ChatGPT web, Claude web, etc. Forwards to EPI pipeline.

---

## 16. Key Functions Reference

### epi_core/container.py
`pack()`, `unpack()`, `read_manifest()`, `read_steps()`, `read_step()`, `count_steps()`, `read_member_json()`, `read_member_text()`, `read_member_bytes()`, `list_members()`, `verify_integrity()`, `detect_container_format()`, `container_mimetype()`, `extract_inner_payload()`, `extract_embedded_viewer()`, `migrate()`, `refresh_viewer()`, `add_review()`

### epi_core/policy.py
`load_policy()`, `EPIPolicy.validate()`, `EPIPolicy.model_validate_json()`

### epi_core/fault_analyzer.py
`FaultAnalyzer(policy).analyze(steps_jsonl)` → `to_dict()`, `to_json()`, `to_policy_evaluation_json()`

### epi_core/trust.py
`VerificationPolicy(PERMISSIVE|STANDARD|STRICT)`, `TrustRegistry.lookup()`, `TrustRegistry.verify()`

### epi_recorder/api.py
`record(path, ...)`, `get_current_session()`, `session.log_step()`, `session.log_tool_call()`, `session.capture()`

### epi_recorder/wrappers/openai.py
`wrap_openai(client)` → `TracedOpenAI`

### epi_recorder/wrappers/anthropic.py
`wrap_anthropic(client)` → `TracedAnthropic`

### epi_cli/verify.py
`verify_command(ctx, path, json, verbose, report, review, strict, policy, aiuc1, web, qr)`

### epi_cli/keys.py
`KeyManager.generate_keypair()`, `.list_keys()`, `.export_public_key()`, `.trust_key()`, `.revoke_key()`, `generate_default_keypair_if_missing()`

---

*Document generated from EPI-Recorder V4.2.0 codebase. Built by EPI Labs — [epilabs.org](https://epilabs.org)*
