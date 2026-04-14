# EPI Recorder Repository - Comprehensive Analysis

**Repository:** epi-recorder  
**Version:** 4.0.1  
**Purpose:** Portable repro artifacts for AI agent runs - capture, open, share, and verify AI evidence  
**Spec Reference:** https://github.com/mohdibrahimaiml/epi-spec  
**Analysis Date:** April 14, 2026

---

## 1. Repository Overview

### 1.1 Project Purpose

EPI (Evidence Packaged Infrastructure) is a **standard for packaging AI execution into portable, verifiable `.epi` artifacts**. The epi-recorder is the reference implementation. It provides:

- **Evidence Capture**: Transform any AI workflow execution into a self-contained `.epi` file
- **Portability**: No cloud, no login, no internet required - works offline
- **Verifiability**: Tamper-evident signatures using Ed25519 cryptography
- **Forensics**: Complete execution timeline with environment snapshots for reproducibility
- **Team Review**: Browser-based viewer for inspecting cases without special tools
- **Framework Integration**: Native support for OpenAI, Anthropic, LangChain, LangGraph, LiteLLM, OpenTelemetry, AGT

### 1.2 Architecture Philosophy

**Four Stages of Evidence:**

1. **Setup** - Prepare recording context before workflow execution
2. **Recording** - Capture meaningful execution steps during runtime
3. **Safety Net** - Persist structured steps atomically (survives crashes)
4. **Seal** - Package into durable artifact with cryptographic signatures

### 1.3 Technology Stack

- **Language**: Python 3.11+
- **Core Dependencies**:
  - `pydantic>=2.0.0` - Data validation and serialization
  - `cryptography>=41.0.0` - Ed25519 signing/verification
  - `cbor2>=5.6.0` - Canonical serialization for tamper-evident hashing
  - `typer>=0.12.0` - CLI framework
  - `rich>=13.0.0` - Terminal UI
- **Optional Framework Integrations**:
  - OpenAI, Anthropic, Google Generative AI, LiteLLM
  - LangChain, LangGraph
  - OpenTelemetry
  - pytest
- **Web/Gateway**: FastAPI, Uvicorn, PostgreSQL/S3 optional backends
- **Testing**: pytest, pytest-asyncio, pytest-cov, pytest-playwright

---

## 2. Package-by-Package Breakdown

### 2.1 `epi_cli/` — CLI Commands and Entrypoints

**Purpose**: User-facing command-line interface for recording, verification, sharing, and team review  
**File Count**: 25 Python files

#### Key Files & Functions:

| File | Purpose | Key Classes/Functions |
|------|---------|---------------------|
| `main.py` | CLI entrypoint and app definition | `app` (Typer app), `version_callback()`, `_analysis_has_fault()` |
| `record.py` | Record a command and package output | `record()` - CLI callback for `epi record --out` |
| `run.py` | Run pre-instrumented Python script | `run()` - Execute Python scripts with EPI context |
| `view.py` | Open case file in browser viewer | `view()` - Launch offline HTML viewer |
| `verify.py` | Cryptographic integrity check | `verify()` - Check signatures, hashes, structure |
| `share.py` | Upload hosted share link | `share()` - Push to gateway for browser review |
| `review.py` | Add human review notes to case | `add_review()` - Append review.json |
| `importer.py` | Import AGT evidence | `import_agt()` - Convert AGT bundles to .epi |
| `policy.py` | Manage fault-detection rules | `policy init`, `policy validate`, `policy load` |
| `chat.py` | Chat with evidence using AI | `chat()` - Interactive evidence Q&A |
| `debug.py` | Debug agent recordings | `debug()` - Introspection and error analysis |
| `connect.py` | Local team review workspace | `connect open` - Multi-user browser interface |
| `gateway.py` | Advanced capture service | `gateway serve` - FastAPI evidence server |
| `ls.py` | List local recordings | `ls()` - Directory listing with metadata |
| `integrate.py` | Generate framework examples | `integrate langchain --dry-run` |
| `install.py` | First-time setup | `install()` - Environment prep |
| `keys.py` | Key management | `KeyManager` - Ed25519 key generation/storage |
| `telemetry.py` | Privacy-first metrics | `telemetry enable/disable/test` |
| `export_summary.py` | Export case summaries | `export_summary()` - Bulk case export |
| `onboarding.py` | First-run wizard | `onboarding()` - Interactive guide |
| `_shared.py` | Shared utilities | `ensure_python_command()`, `build_env_for_child()` |
| `dev.py` | Demo/development runner | `dev()` - Quick start demo |
| `doctor.py` | Self-healing health check | `doctor()` - Diagnostic tool |

#### Command Flow Examples:

```bash
epi record --out run.epi -- python script.py  # Args: run.py
epi run --policy epi_policy.json script.py    # Pre-instrumented execution
epi view run.epi                               # Browser: offline viewer
epi verify run.epi                             # Check signatures/integrity
epi share run.epi                              # Host with gateway
epi import agt bundle.json --out case.epi      # Import AGT evidence
```

---

### 2.2 `epi_core/` — Core Artifact, Verification, Storage  

**Purpose**: Core data models, serialization, container logic, trust/crypto, and storage  
**File Count**: 22 Python files (+ 2 in `platform/` subdirectory)

#### Key Files & Functions:

| File | Purpose | Key Classes/Functions |
|------|---------|---------------------|
| `schemas.py` | Pydantic models for manifest and steps | `ManifestModel`, `StepModel` - JSON schema definitions |
| `container.py` | Dual-format container management (ZIP vs envelope) | `EPIContainer` - Pack/extract `.epi` files |
| `capture.py` | Shared capture contracts for ingestion layer | `CaptureBatchModel`, `CaptureEventModel`, `CaptureProvenanceModel` |
| `serialize.py` | Canonical CBOR hashing for tamper-evident records | `get_canonical_hash()` - Deterministic SHA-256 |
| `trust.py` | Cryptographic signing/verification (Ed25519) | `sign_manifest()`, `verify_signature()`, `verify_embedded_manifest_signature()` |
| `llm_capture.py` | Provider-normalized LLM capture | `LLMCaptureRequest`, `build_llm_capture_events()`, `normalize_provider_name()` |
| `review.py` | Human review records (append-only) | `compute_review_hash()`, `canonical_review_json()`, verify/update review |
| `policy.py` | Load and validate company-defined fault rules | `EPIPolicy`, `PolicyRule`, `PolicyScope`, `ApprovalPolicy` |
| `fault_analyzer.py` | Four-pass heuristic fault detection | `FaultAnalyzer` - Error continuation, constraint violation, sequence violation, context drop |
| `artifact_inspector.py` | Validate and inspect portable artifacts | `inspect_artifact()`, `ArtifactInspectionResult` |
| `storage.py` | SQLite-based atomic storage (crash-safe) | `EpiStorage` - Replaces JSONL for durability |
| `redactor.py` | Automatic secret redaction patterns | `Redactor` - API key/token/credential redaction |
| `case_store.py` | Shared gateway-backed case store | `CaseExportResultModel`, `CaseReviewModel`, `DecisionCaseModel` |
| `workspace.py` | Recording workspace management | `create_recording_workspace()`, `RecordingWorkspaceError` |
| `connectors.py` | External evidence source connections | `fetch_live_record()` - Gateway polling |
| `keys.py` | Key storage and management | `load_or_create_default_key()` |
| `telemetry.py` | Usage metrics (privacy-aware) | Telemetry event validation and queueing |
| `time_utils.py` | Timezone handling and normalization | `utc_now()`, `utc_now_iso()` |
| `viewer_assets.py` | Embedded HTML/CSS/JS assets | `inline_viewer_assets()`, `load_viewer_assets()` |
| `auth_local.py` | Local auth (team review) | `build_session_token()`, `hash_session_token()` |
| `_version.py` | Version info | `get_version()` |

#### Data Structures:

**ManifestModel** (JSON schema):
```python
{
  "spec_version": "4.0.1",
  "workflow_id": UUID,
  "created_at": datetime,
  "cli_command": str,
  "env_snapshot_hash": SHA256,
  "file_manifest": {
    "steps.jsonl": SHA256,
    "environment.json": SHA256,
    ...
  },
  "public_key": hex_ed25519_pub,
  "signature": "ed25519:<name>:<hex_sig>",
  "container_format": "legacy-zip" | "envelope-v2",
  "analysis_status": "complete" | "skipped" | "error",
  "goal": str,
  "notes": str,
  "metrics": dict,
  "approved_by": str,
  "tags": list
}
```

**StepModel** (NDJSON timeline):
```python
{
  "index": int,
  "timestamp": datetime,
  "kind": str,  # llm.request, llm.response, python.call, file.write, etc
  "content": {
    # Provider-specific payload
  }
}
```

---

### 2.3 `epi_recorder/` — Runtime Recording API and Wrappers

**Purpose**: Programmatic Python API for instrumentation and wrapper clients  
**File Count**: 8 core files + subdirectories

#### Key Files & Functions:

| File | Purpose | Key Classes/Functions |
|------|---------|---------------------|
| `api.py` | Python API context manager | `EpiRecorderSession`, `record()` context manager, `get_current_session()`, `AgentRun` |
| `__init__.py` | Package exports | Export `record`, `wrap_openai`, `wrap_anthropic`, `auto`, `AgentAnalytics` |
| `auto.py` | Framework auto-setup | `auto.setup()` - Register hooks for LiteLLM, LangChain, OpenTelemetry |
| `asyncapi.py` | Async recording support | `async_record()` - Coroutine context manager |
| `bootstrap.py` | Child process initialization | `_BootstrapStreamCapture` - sitecustomize hook |
| `patcher.py` | Runtime LLM API interception | `RecordingContext`, `get_recording_context()`, `set_recording_context()` |
| `environment.py` | Environment snapshot capture | `capture_full_environment()`, `save_environment_snapshot()` |
| `step_types.py` | Step kind constants | `STEP_KIND_*` constants |

**Wrappers/** (4 files):
- `base.py` - `TracedClientBase` - Common wrapper interface
- `openai.py` - `TracedOpenAI`, `TracedCompletions`, `wrap_openai()` - OpenAI SDK wrapper
- `anthropic.py` - `TracedAnthropic`, `wrap_anthropic()` - Anthropic SDK wrapper
- `__init__.py` - Export wrapper classes

**Integrations/** (6 files):
- `langchain.py` - `EPICallbackHandler` - LangChain callback system integration
- `langgraph.py` - `EPICheckpointSaver` - LangGraph checkpoint backend
- `litellm.py` - `enable_epi()` - LiteLLM provider wrapper
- `opentelemetry.py` - `EPISpanExporter` - OpenTelemetry span export
- `openai_agents.py` - OpenAI Agents framework hooks
- `__init__.py` - Integration exports

**AGT/** (6 files - in integrations/):
- `converter.py` - Convert AGT events to EPI format
- `loader.py` - Load AGT bundles/manifests
- `mapping.py` - AGT field to EPI mapping
- `report.py` - Analysis reports for imported artifacts
- `schema.py` - AGT schema definitions
- `__init__.py` - `export_agt_to_epi()`, `load_agt_input()`, `AGTInputError`

**Analytics/** (2 files):
- `analytics.py` - `AgentAnalytics` class for pandas-based analysis
- `__init__.py` - Exports

#### Usage Example:
```python
from epi_recorder import record, wrap_openai
from openai import OpenAI

client = wrap_openai(OpenAI())

with record("my_agent.epi") as session:
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello"}]
    )
    session.log_step("decision", {"action": "approved"})
```

---

### 2.4 `epi_gateway/` — Web Gateway Services

**Purpose**: FastAPI-based server for shared evidence collection, review workflows, and integration proxying  
**File Count**: 6 Python files

#### Key Files & Functions:

| File | Purpose | Key Classes/Functions |
|------|---------|---------------------|
| `main.py` | FastAPI application and endpoints | `app` (FastAPI instance), router definitions |
| `proxy.py` | Relay OpenAI/Anthropic API calls | `relay_openai_chat_completions()`, `relay_anthropic_messages()`, `build_*_proxy_capture_request()` |
| `worker.py` | Background task processing | `EvidenceWorker` - Batch processing, analysis, signing |
| `share.py` | Share service and hosting | `ShareService` - Upload/retrieve shared artifacts |
| `approval_notify.py` | Approval email/webhook notifications | `send_approval_email()`, `send_signed_webhook()` |
| `__init__.py` | Package initialization |  |

**Gateway Features:**
- **Case Collection**: POST `/cases` endpoint for submitting evidence
- **LLM Proxying**: `/v1/chat/completions` (OpenAI-compatible), `/messages` (Anthropic-compatible)
- **Team Review**: Case listing, filtering, approval workflows
- **Share Links**: Generate ephemeral hosted links for browser review
- **Telemetry**: Opt-in usage metrics collection
- **Authentication**: Local auth with role-based access control
- **Batch Processing**: Worker pool for analysis, signing, and storage optimization

---

### 2.5 `pytest_epi/` — pytest Plugin

**Purpose**: Automatic EPI recording for pytest test functions  
**File Count**: 2 Python files

#### Key Files:

| File | Purpose | Key Classes/Functions |
|------|---------|---------------------|
| `plugin.py` | pytest hook registration | `pytest_addoption()`, `pytest_configure()`, `pytest_runtest_makereport()` |
| `__init__.py` | Package initialization | |

#### Configuration:

```ini
[tool.pytest.ini_options]
epi = true                          # Enable recording
epi_dir = "./test-evidence"        # Output directory
epi_on_pass = false                # Keep failures only (default)
epi_sign = true                    # Auto-sign artifacts
```

**CLI Usage:**
```bash
pytest --epi test_agent.py          # Record all tests
pytest --epi --epi-on-pass          # Keep all artifacts
pytest --epi -k "test_chat"         # Pattern match
```

---

### 2.6 `epi_analyzer/` — Analysis and Fault Detection

**Purpose**: Deterministic fault detection and policy-grounded analysis  
**File Count**: 2 Python files

#### Key Files:

| File | Purpose | Key Classes/Functions |
|------|---------|---------------------|
| `detector.py` | Four-pass heuristic analyzer | (Extends `epi_core.fault_analyzer.FaultAnalyzer`) |
| `__init__.py` | Package initialization | |

**Note**: Core analysis logic in `epi_core/fault_analyzer.py` (100+ lines)

#### Analysis Passes:

1. **Error Continuation** - Tool returned error but agent continued as if success
2. **Constraint Violation** - Numerical limit set at step M violated at step N
3. **Sequence Violation** - Action B occurred before required action A (policy-driven)
4. **Context Drop** - Key entity ID vanishes from final third of execution

---

### 2.7 `epi_viewer_static/` — Viewer Assets

**Purpose**: Self-contained browser viewer for offline case inspection  
**File Count**: 4 files

#### Files:

| File | Purpose |
|------|---------|
| `index.html` | Main viewer HTML with case-first layout |
| `app.js` | Case navigation, evidence display, search/filter logic |
| `crypto.js` | Client-side Ed25519 verification, CBOR hashing |
| `viewer_lite.css` | Responsive case-first styling |

**Embedded Sections:**
- Overview (decision, review status, trust state)
- Evidence (steps timeline, logs, metrics)
- Policy (control rules evaluation)
- Review (human decision record)
- Mapping (AGT transformation audit)
- Trust (signature verification UI)
- Attachments (exported files)

---

### 2.8 `web_viewer/` — Web-Based Case Viewer

**Purpose**: Server-based case viewer for team review (minimal JavaScript)  
**File Count**: 6 files

#### Files:

| File | Purpose |
|------|---------|
| `index.html` | Server-rendered case layout |
| `app.js` | Client-side interactions and data fetching |
| `styles.css` | Server viewer styling |
| `jszip.min.js` | ZIP extraction library for browser |
| `README.md` | Setup documentation |
| `__init__.py` | Flask/Starlette routing |

---

### 2.9 `_cells/` — Colab Notebook Cells

**Purpose**: Framework-specific Jupyter notebook examples  
**File Count**: 12 Python files

#### Cell Modules:

| File | Purpose |
|------|---------|
| `cell_record.py` | Record a workflow |
| `cell_setup.py` | Initialize environment |
| `cell_agent.py` | Multi-turn agent example |
| `cell_chat.py` | Chat interface demo |
| `cell_verify.py` | Verify artifacts |
| `cell_view.py` | Open viewer |
| `cell_download.py` | Export cases |
| `cell_explore.py` | Data exploration |
| `cell_inspect.py` | Evidence inspection |
| `cell_integrations.py` | Framework setup |
| `cell_tamper.py` | Tamper detection demo |
| `cell_cta.py` | Call-to-action examples |

---

## 3. Key Implementation Details

### 3.1 How .epi Artifacts Are Created, Serialized, and Verified

#### Creation Flow:

```
User Code / CLI Command
    ↓
Create RecordingWorkspaceError (temp directory)
    ↓
Initialize EpiStorage (SQLite) or capture context
    ↓
Execute workflow / capture hooks intercept LLM calls
    ↓
Store steps atomically (.add_step() → SQLite transaction)
    ↓
Capture environment snapshot (environment.json)
    ↓
On completion: EPIContainer.pack()
    ├─ Build ManifestModel with file hashes
    ├─ Compute SHA-256 hashes of all artifacts
    ├─ (Optional) Sign manifest with Ed25519 private key
    ├─ Create ZIP payload with steps, environment, viewer.html, manifest
    └─ Wrap ZIP in EPI1 envelope with header
    ↓
Write .epi file to disk
```

#### Serialization:

**Container Formats:**

1. **legacy-zip** (v3.x):
   - `.epi` file IS the ZIP archive directly
   - Starts with ZIP magic bytes `PK\x03\x04`

2. **envelope-v2** (v4.0+, default):
   - Binary header (64 bytes):
     ```
     00-03: Magic "EPI1"
     04:    Envelope version (1)
     05:    Payload format (0x01 = ZIP-v1)
     06-07: Reserved (0x0000)
     08-15: Payload length (uint64 LE)
     16-47: Payload SHA-256
     48-63: Reserved zeros
     64+:   ZIP payload bytes
     ```
   - Payload SHA-256 enables fail-fast validation

**Step Serialization (steps.jsonl):**
- NDJSON format (one JSON object per line)
- Each line is one StepModel serialized
- Atomically appended to prevent corruption on crash

**Manifest Serialization:**
- Canonical JSON (sorted keys, no whitespace)
- Hashed with CBOR for deterministic digest
- Signed with Ed25519 private key
- Stored as last file in ZIP (allows append-only review records)

#### Verification Flow:

```
Reader loads .epi file
    ↓
Detect container format (EPI1 magic vs ZIP magic)
    ├─ If EPI1: Validate envelope header, stream-hash payload, extract ZIP
    └─ If PK\x03\x04: Use as legacy ZIP directly
    ↓
Parse manifest.json from ZIP
    ↓
Verify mimetype field = "application/vnd.epi+zip"
    ↓
For each file in manifest.file_manifest:
    ├─ Read from ZIP
    ├─ Compute SHA-256
    └─ Compare to manifest hash → integrity_ok
    ↓
If manifest.signature present:
    ├─ Extract public_key
    ├─ Compute canonical hash of manifest (excluding signature)
    ├─ Verify Ed25519 signature
    └─ signature_valid = True/False
    ↓
Return ArtifactInspectionResult
```

---

### 3.2 The Wrapper/Instrumentation Pattern

#### Design Philosophy:
- **Explicit Opt-In**: No silent monkey-patching by default
- **Transparent**: Proxies pass all arguments to underlying client
- **Non-Blocking**: Wrapper failures don't crash user code
- **Thread-Safe**: Global recording context with locks

#### Pattern Implementation:

**Wrapper Structure** (`epi_recorder/wrappers/openai.py`):
```python
class TracedOpenAI:
    def __init__(self, openai_client, provider="openai"):
        self._client = openai_client  # Delegate to real client
    
    @property
    def chat(self):
        return TracedCompletions(self._client.chat)

class TracedCompletions:
    def create(self, **kwargs):
        session = get_current_session()  # Get active recording
        if session:
            session.log_step("llm.request", {
                "provider": "openai",
                "model": kwargs.get("model"),
                "messages": kwargs.get("messages")
            })
        
        response = self._completions.create(**kwargs)  # Call real API
        
        if session:
            session.log_step("llm.response", {
                "choices": extract_choices(response),
                "usage": extract_usage(response)
            })
        
        return response  # Return to user unchanged
```

**Integration Points:**
- `wrap_openai(client)` - Per-client opt-in
- `auto.setup()` - Global registration for all clients
- Framework callbacks (LangChain, LangGraph, OpenTelemetry integration points)
- LiteLLM proxy (patches `litellm.completion()` globally)

**Signature:**
```python
def wrap_openai(client: OpenAI) -> TracedOpenAI
def wrap_anthropic(client: Anthropic) -> TracedAnthropic
def wrap_client(client, provider="auto") -> TracedClient
```

---

### 3.3 Container Format (Envelope vs Legacy ZIP)

#### Legacy ZIP Format (v3.x):

```
example.epi (is a ZIP)
├── mimetype (first, STORED)
├── steps.jsonl (NDJSON timeline)
├── environment.json (env snapshot)
├── viewer.html (embedded offline viewer)
├── artifacts/ (captured files)
└── manifest.json (metadata + hashes + signature)
```

**Pros:** Direct ZIP compatibility  
**Cons:** Starts with ZIP magic, can be misclassified as "compressed folder"

#### Envelope Format (v4.0+, default):

```
example.epi
├── [64-byte EPI1 header]
│   ├── Magic: "EPI1"
│   ├── Envelope version: 1
│   ├── Format: 0x01 (zip-v1)
│   ├── Payload length (uint64 LE)
│   ├── Payload SHA-256
│   └── Reserved
│
└── Embedded ZIP payload (identical to legacy)
    ├── mimetype
    ├── steps.jsonl
    ├── environment.json
    ├── viewer.html
    ├── artifacts/
    └── manifest.json
```

**Container Abstraction** (`EPIContainer` class):

```python
class EPIContainer:
    @staticmethod
    def pack(workspace, manifest, out_path, signer_function=None):
        # Detect or choose format
        # Generate ZIP
        # (v4.0+) Wrap in envelope with SHA-256 validation
        # Write to disk
    
    @staticmethod
    def extract(epi_path, temp_dir):
        # Auto-detect format
        # Validate envelope or ZIP magic
        # Extract payload ZIP
        # Verify hashes
        # Return extraction status
    
    @staticmethod
    def read_manifest(epi_path):
        # Open container (any format)
        # Read and parse manifest.json
        # Return ManifestModel
```

---

### 3.4 Trust and Cryptography Implementation

#### Key Management:

**Default Key Location:** `~/.epi/keys/default.pem` (Ed25519 private key)

```python
class KeyManager:
    def load_or_create_default_key(self):
        if ~/.epi/keys/default.pem exists:
            return load_private_key_from_pem()
        else:
            new_key = Ed25519PrivateKey.generate()
            save_to_pem()
            return new_key
```

**Ed25519 Signing:**

```python
def sign_manifest(manifest, private_key, key_name="default"):
    # Add public key to manifest
    manifest.public_key = private_key.public_key().hex()
    
    # Compute canonical JSON hash (CBOR normalized)
    manifest_hash = get_canonical_hash(manifest, exclude={"signature"})
    
    # Sign hash with Ed25519
    signature_bytes = private_key.sign(bytes.fromhex(manifest_hash))
    
    # Encode with metadata
    manifest.signature = f"ed25519:{key_name}:{signature_bytes.hex()}"
    
    return manifest
```

**Verification:**

```python
def verify_embedded_manifest_signature(manifest):
    if not manifest.signature or not manifest.public_key:
        return None, None, "unsigned"
    
    try:
        # Extract signature components
        parts = manifest.signature.split(":")
        key_name = parts[1] if len(parts) > 1 else "unknown"
        sig_hex = parts[-1]
        
        # Recompute hash (excludes signature field)
        manifest_hash = get_canonical_hash(manifest, exclude={"signature"})
        
        # Verify Ed25519 signature
        public_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(manifest.public_key)
        )
        public_key.verify(bytes.fromhex(sig_hex), bytes.fromhex(manifest_hash))
        
        return True, key_name, "verified"
    except InvalidSignature:
        return False, key_name, "invalid signature"
    except Exception as e:
        return False, None, f"verification error: {e}"
```

**Canonical Hashing:**

```python
def get_canonical_hash(model, exclude_fields=None):
    # Convert Pydantic model to dict
    model_dict = model.model_dump()
    
    # Normalize datetime → ISO-8601 string
    # Normalize UUID → string
    # Exclude specified fields (e.g., signature)
    
    # Serialize to CBOR canonical form:
    # - Keys sorted alphabetically
    # - Floats prohibited (use ints/strings)
    # - Minimal encoding
    
    cbor_bytes = cbor2.dumps(
        model_dict,
        default=_cbor_default_encoder,
        canonical=True
    )
    
    # SHA-256 the CBOR bytes
    return hashlib.sha256(cbor_bytes).hexdigest()
```

#### Trust Model:

1. **Direct Verification**: User has trusted public key → check signature
2. **Gateway Trust**: Trust signer identity from gateway metadata
3. **Policy-Grounded**: Filter by approval status + reviewer identity
4. **Imported Evidence**: Mark with `trust_class: "verified_imported"` vs `"verified_direct"`

---

### 3.5 CLI Command Flow and User Interactions

#### Major Command Flows:

**`epi record --out run.epi -- python script.py`:**
```
1. Parse args (out path, command)
2. Create recording workspace (temp dir)
3. Build environment snapshot
4. Set child process env vars:
   - EPI_RECORDER_DIR = temp workspace path
   - EPI_ENABLE_PATCHING = 1
5. Spawn subprocess with patched sys.path
6. Bootstrap initializes RecordingContext (patches OpenAI, etc.)
7. User script runs, LLM calls accumulate in steps.jsonl
8. After completion:
   - Build ManifestModel
   - Load default private key
   - Call sign_manifest()
   - EPIContainer.pack(workspace, manifest, out_path, signer)
9. Print summary panel (file size, exit code, verification command)
```

**`epi run script.py` (pre-instrumented):**
```
1. User code already uses: with record("output.epi")
2. Check for local epi_policy.json
3. Print warning if policy invalid
4. Execute script directly (in-process)
5. recording completes normally
```

**`epi verify run.epi`:**
```
1. Detect container format (EPI1 vs ZIP magic)
2. Extract manifest + file list
3. Verify envelope SHA-256 (if envelope-v2)
4. Check integrity: ∑ SHA-256(file) == manifest.file_manifest
5. Verify signature: Ed25519 check against public_key
6. Count steps in steps.jsonl
7. Return ArtifactInspectionResult
8. Print trust panel: integrity_ok, signature_valid, steps count
```

**`epi view run.epi` | `epi share run.epi`:**
```
view:
  1. Inspect artifact (verify integrity first)
  2. Extract viewer.html from ZIP
  3. Inline manifest.json, steps.jsonl, environment.json into <script>
  4. Launch browser with file:// URL
  5. Offline viewer renders case from embedded data

share:
  1. Inspect artifact (must pass integrity check)
  2. POST to gateway: /api/cases/upload
  3. Gateway generates ephemeral URL
  4. Print share URL (browser-accessible case viewer)
```

**`epi import agt bundle.json --out case.epi`:**
```
1. Load AGT input (JSON bundle or directory)
2. Parse AGT schema (audit_logs, flight_recorder, etc.)
3. Map AGT events to EPI capture model
   - AGT tool_call → EPI step kind "tool.call"
   - AGT error → step kind "error"
   - etc.
4. Build CaptureEventModel for each event
5. Create ManifestModel with metadata
6. Optionally pack AGT raw files under artifacts/agt/
7. Sign with default key
8. EPIContainer.pack() → case.epi
9. Print mapping report (what was translated, derived, preserved raw)
```

---

### 3.6 Redaction and Privacy

#### Redaction Strategy:

**Pattern-Based Detection:**
- OpenAI keys: `sk-[48 chars]`, `sk-proj-[48+ chars]`
- Anthropic: `sk-ant-[95+ chars]`
- AWS: `AKIA[16 chars]`, secrets patterns
- GitHub: `ghp_*`, `gho_*`
- JWT tokens: `eyJ*.*.*` (3-part format)
- PII: Email, phone, database URLs
- Private keys: PEM format detection

```python
DEFAULT_REDACTION_PATTERNS = [
    (r'sk-[a-zA-Z0-9]{48}', 'OpenAI API key'),
    (r'sk-ant-[a-zA-Z0-9_-]{95,}', 'Anthropic API key'),
    ...
]
```

**Redaction Flow:**

```python
class Redactor:
    def redact(self, content_dict):
        redacted = copy.deepcopy(content_dict)
        count = 0
        
        for pattern, description in self.patterns:
            for key, value in flatten_dict(redacted).items():
                if isinstance(value, str):
                    if pattern.search(value):
                        redacted[key] = "***REDACTED***"
                        count += 1
        
        return redacted, count
```

**Enabled by Default:**
- `epi record` and `epi run` enable redaction automatically
- `--no-redact` flag to disable (not recommended)
- Environment variables marked for redaction: `OPENAI_API_KEY`, `DATABASE_URL`, etc.

**Redaction Step:**
```json
{
  "kind": "security.redaction",
  "content": {
    "count": 3,
    "target_step": "llm.request"
  }
}
```

---

## 4. Data Flow: Recording → Storage → Verification → Viewing

```
┌─────────────────────────────────────────────────────────────────┐
│ RECORDING PHASE                                                 │
├─────────────────────────────────────────────────────────────────┤

User Code / CLI
    │
    ├─→ with record("output.epi") or epi record --out
    │
    ├─→ RecordingContext initialized
    │   ├─→ Temp workspace created
    │   ├─→ EpiStorage (SQLite) or JSONL
    │   └─→ Environment snapshot captured
    │
    ├─→ Wrappers/Integrations hooked
    │   ├─→ wrap_openai() patches client.chat.completions
    │   ├─→ EPICallbackHandler listens to LangChain events
    │   ├─→ EPISpanExporter receives OpenTelemetry spans
    │   └─→ patcher patches globals (LiteLLM, etc)
    │
    └─→ Execution
        └─→ Each LLM/tool call:
            1. session.log_step("llm.request", {...})
            2. Call underlying API
            3. session.log_step("llm.response", {...})

┌─────────────────────────────────────────────────────────────────┐
│ STORAGE PHASE                                                   │
├─────────────────────────────────────────────────────────────────┤

RecordingContext.add_step() called
    │
    ├─→ Redactor.redact() if enabled
    │   └─→ Emit security.redaction step if secrets found
    │
    └─→ Store atomically
        ├─→ EpiStorage: INSERT INTO steps VALUES (...) + COMMIT
        │   (crash-safe, survives power loss)
        └─→ or JSONL: append line + flush
            (best-effort, corrupts on crash)

After workflow completes
    │
    ├─→ Collect all artifacts from workspace
    │
    ├─→ Build ManifestModel
    │   ├─→ Compute SHA-256(steps.jsonl)
    │   ├─→ Compute SHA-256(environment.json)
    │   ├─→ Compute SHA-256(analysis.json) if policy present
    │   └─→ Store hashes in file_manifest
    │
    ├─→ Sign manifest
    │   ├─→ Load ~/.epi/keys/default.pem (or --no-sign)
    │   ├─→ Compute canonical JSON hash
    │   ├─→ Ed25519 sign the hash
    │   └─→ Append signature to manifest
    │
    └─→ EPIContainer.pack()
        ├─→ Create ZIP with all files
        ├─→ Add embedded viewer.html
        ├─→ (v4.0+) Wrap in EPI1 envelope
        ├─→ Compute envelope SHA-256
        └─→ Write to disk: output.epi

┌─────────────────────────────────────────────────────────────────┐
│ VERIFICATION PHASE                                              │
├─────────────────────────────────────────────────────────────────┤

epi verify output.epi
    │
    ├─→ Detect container format
    │   ├─→ EPI1 magic? → Validate envelope header + SHA-256
    │   └─→ PK\x03\x04 magic? → Legacy ZIP
    │
    ├─→ Extract manifest.json
    │
    ├─→ Verify integrity
    │   ├─→ Extract each file from ZIP
    │   ├─→ Compute SHA-256 of file content
    │   └─→ Compare to manifest.file_manifest[filename]
    │       → integrity_ok = all match
    │
    ├─→ Verify signature (if present)
    │   ├─→ Extract Ed25519 public key from manifest
    │   ├─→ Recompute canonical JSON hash
    │   ├─→ Ed25519 verify signature
    │   └─→ signature_valid = True/False/None
    │
    └─→ Return ArtifactInspectionResult
        ├─→ integrity_ok: bool
        ├─→ signature_valid: bool | None
        ├─→ steps_count: int
        └─→ mismatches: dict (if integrity failed)

┌─────────────────────────────────────────────────────────────────┐
│ VIEWING PHASE                                                   │
├─────────────────────────────────────────────────────────────────┤

epi view output.epi
    │
    ├─→ Inspect artifact (verify integrity)
    │
    ├─→ Extract viewer.html from ZIP
    │
    ├─→ Read steps.jsonl from ZIP
    │
    ├─→ Read manifest.json, environment.json, analysis.json
    │
    ├─→ Inject inline <script> in viewer.html:
    │   window.__EPI_MANIFEST__ = {...}
    │   window.__EPI_STEPS__ = [...]
    │   window.__EPI_ENVIRONMENT__ = {...}
    │
    ├─→ Launch browser (file://)
    │
    └─→ Browser viewer renders case
        ├─→ Overview tab: decision, review status, trust state
        ├─→ Evidence tab: timeline, steps, search/filter
        ├─→ Policy tab: control rules evaluation
        ├─→ Review tab: human decision
        ├─→ Trust tab: signature verification (crypto.js)
        └─→ Attachments tab: exported artifacts

epi share output.epi
    │
    ├─→ POST artifact to gateway: /api/cases/upload
    │
    ├─→ Gateway stores in evidence_vault (encrypted or redacted)
    │
    ├─→ Generate ephemeral share link
    │
    └─→ User shares URL → opens web viewer in browser
```

---

## 5. Integration Points: Framework Integrations

### 5.1 LLM Provider Wrapping

#### OpenAI:
```python
from epi_recorder import wrap_openai
from openai import OpenAI

client = wrap_openai(OpenAI(api_key="..."))

with record("agent.epi"):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "..."}]
    )
    # Automatically logged as llm.request + llm.response steps
```

**Wrapper Classes:**
- `TracedOpenAI` - Main proxy
- `TracedCompletions` - Routes to streaming/non-streaming handlers
- `TracedEmbeddings` (if supported)

#### Anthropic:
```python
from epi_recorder import wrap_anthropic
from anthropic import Anthropic

client = wrap_anthropic(Anthropic(api_key="..."))
# Same usage pattern
```

### 5.2 Framework Callbacks

#### LangChain:
```python
from epi_recorder.integrations.langchain import EPICallbackHandler

handler = EPICallbackHandler()

llm = ChatOpenAI(callbacks=[handler])

with record("langchain_agent.epi"):
    result = llm.invoke("...")
    # All LLM calls, tool calls, retriever queries logged
```

**Captured Events:**
- `on_llm_start`: Prompt + model info
- `on_llm_end`: Response + tokens
- `on_tool_start`: Tool name + input
- `on_tool_end`: Tool output
- `on_chain_start/end`: Chain execution
- `on_retriever_start/end`: Retriever queries

#### LangGraph:
```python
from epi_recorder.integrations.langgraph import EPICheckpointSaver

checkpointer = EPICheckpointSaver("agent.epi")

result = graph.invoke(
    input_data,
    config={"configurable": {"thread_id": "1"}},
    checkpointer=checkpointer
)

with record("agent.epi"):
    # State transitions automatically checkpointed
```

#### OpenTelemetry:
```python
from epi_recorder.integrations.opentelemetry import EPISpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

epi_exporter = EPISpanExporter()
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(epi_exporter))

with record("otel_agent.epi"):
    # All OTEL spans exported to .epi
```

#### LiteLLM (Global Hook):
```python
from epi_recorder.integrations.litellm import enable_epi

enable_epi()  # Patches litellm.completion globally

with record("litellm_agent.epi"):
    import litellm
    response = litellm.completion(model="gpt-4", messages=[...])
    # Captured automatically
```

### 5.3 AGT (Microsoft Agent Governance Toolkit)

#### Import AGT Evidence:
```python
epi import agt bundle.json --out case.epi
epi import agt ./evidence-dir --out case.epi
epi import agt agt_import_manifest.json --out case.epi
```

**Conversion Process:**

1. Load AGT input (JSON bundle, directory, or manifest)
2. Parse AGT schemas:
   - `audit_logs.json` - Agent decision records
   - `flight_recorder.json` - Execution trace
   - Other provider-specific formats
3. Map AGT events to EPI step kinds:
   - AGT tool call → `tool.call`
   - AGT error → `error`
   - AGT decision → `decision`
4. Extract transformation audit:
   - Raw: Events copied exactly
   - Translated: Format converted but semantics preserved
   - Derived: Computed from other events
   - Synthesized: Inferred from available data
5. Attach raw AGT artifacts under `artifacts/agt/`
6. Create case file with mapping report

**AGT Mapping:**
- `agt/converter.py` - Event normalization
- `agt/loader.py` - Input parsing
- `agt/mapping.py` - Schema field mapping
- `agt/report.py` - Dedup and analysis modes
- `agt/schema.py` - AGT data models

---

## 6. Test Coverage

### 6.1 Test Structure

**Total Test Files:** 60+ in `/tests` directory

**Test Categories:**

#### Unit Tests:
- `test_schemas.py` - Schema validation
- `test_serialize.py` - CBOR hashing correctness
- `test_container.py` - Container pack/extract
- `test_trust.py` - Ed25519 signing/verification
- `test_capture_schema.py` - Capture event models
- `test_redactor.py` - Secret redaction patterns
- `test_fault_analyzer.py` - Heuristic detection passes

#### Integration Tests:
- `test_cli_commands.py` - End-to-end CLI workflows
- `test_api_integration.py` - Python API context manager
- `test_container_extended.py` - Large artifacts, edge cases
- `test_serialize_storage.py` - SQLite + JSON storage
- `test_policy_loader.py` - Policy parsing and validation
- `test_langchain_integration.py` - LangChain callbacks
- `test_litellm_integration.py` - LiteLLM proxy
- `test_opentelemetry_integration.py` - OTEL span export
- `test_gateway_*.py` - Gateway endpoints and workflows

#### Compliance Tests:
- `test_compliance/` - Policy evaluation, redaction, trust
- `test_audit_*.py` - Package integrity (wheel, sdist)
- `test_agt_*.py` - AGT import workflows
- `test_review_trust_protocol.py` - Review verification
- `test_env_comprehensive.py` - Environment snapshot

#### Browser/E2E Tests:
- `test_web_viewer_mvp.py` - Viewer rendering
- `test_browser/` - Playwright-based case viewing
- `test_view_verify_extended.py` - View + verify flow

#### Security Tests:
- `test_trust.py` - Signature verification edge cases
- `test_redactor.py` - Complete redaction coverage
- `test_container.py` - Malformed archive handling
- `test_runtime_boundaries.py` - Process isolation

### 6.2 Test Configuration

**pytest.ini / pyproject.toml:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
asyncio_mode = "auto"
timeout = 300
markers = [
    "integration: integrations with external frameworks",
    "slow: slow tests",
    "compliance: compliance and audit tests",
]
```

**conftest.py:**
- Windows API shims (test machinery)
- Temp directory management (crash-safe)
- Pytest plugin fixtures

### 6.3 Test Coverage:
- Core modules (schemas, container, trust): ~90%+
- CLI commands: ~80%+
- Integrations: ~75%+
- Edge cases and error handling: Comprehensive

---

## 7. Configuration & Settings

### 7.1 pyproject.toml Dependencies

**Core Requirements:**
```toml
pydantic>=2.0.0,<=2.12.3      # Data validation
cryptography>=41.0.0,<44     # Ed25519, asymmetric crypto
cbor2>=5.6.0                  # Canonical serialization
typer>=0.12.0,<0.25          # CLI framework
rich>=13.0.0,<14             # Terminal UI
```

**Optional Framework Dependencies:**
```toml
# LLM Providers
openai>=1.0.0
anthropic>=0.25.0
google-generativeai>=0.4.0
litellm>=1.0.0

# Frameworks
langchain-core>=0.2.0
langgraph>=0.2.0
opentelemetry-api>=1.25.0
opentelemetry-sdk>=1.25.0

# Analytics
pandas>=1.5.0
matplotlib>=3.5.0

# Gateway
fastapi>=0.111.0,<1
uvicorn>=0.30.0,<1
boto3>=1.34.0
```

**Development & Test:**
```toml
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-cov>=4.1.0
black>=24.0.0
ruff>=0.3.0
httpx>=0.27.0
```

### 7.2 Entry Points

```toml
[project.scripts]
epi = "epi_cli.main:cli_main"
```

**Subcommands:**
- `epi record` - Record a command
- `epi run` - Run pre-instrumented script
- `epi view` - Open case in browser
- `epi verify` - Check integrity/signatures
- `epi share` - Upload to gateway
- `epi review` - Add human review
- `epi import agt` - Convert AGT evidence
- `epi analyze` - Fault analysis summary
- `epi chat` - Chat with evidence
- `epi policy` - Policy management
- `epi ls` - List recordings
- `epi integrate` - Framework setup generator
- `epi init` - First-time setup
- `epi telemetry` - Opt-in metrics
- `epi connect` - Team review workspace
- `epi gateway` - Service runner
- `epi doctor` - Health check

### 7.3 Environment Variables

```bash
# Recording Context
EPI_RECORDER_DIR= <output directory>      # Where steps.jsonl goes
EPI_ENABLE_PATCHING=1                     # Enable LLM patching
EPI_ENABLE_REDACTION=1                    # Enable secret redaction (default)

# Configuration
EPI_POLICY_PATH=./epi_policy.json         # Custom policy location
EPI_QUIET=1                               # Suppress warnings
EPI_TEMP_DIR=/custom/tmp                  # Temp workspace root

# Gateway
EPI_GATEWAY_STORAGE_DIR=./evidence_vault
EPI_GATEWAY_BATCH_SIZE=50
EPI_GATEWAY_BATCH_TIMEOUT=2.0

# Telemetry
EPI_TELEMETRY_ENDPOINT=https://...
EPI_TELEMETRY_ENABLED=0                   # Opt-in required
```

### 7.4 Configuration Files

**~/.epi/config.toml:**
```toml
[keys]
default = "~/.epi/keys/default.pem"

[telemetry]
enabled = false
endpoint = "https://telemetry.epilabs.org/api/events"

[viewer]
theme = "light"
```

**epi_policy.json (Project Level):**
```json
{
  "policy_id": "org-risk-framework",
  "version": "1.0",
  "scope": {
    "organization": "acme-corp",
    "application": "ai-finance"
  },
  "rules": [
    {
      "id": "maximum-transfer-limit",
      "severity": "critical",
      "type": "threshold_guard",
      "condition": "transfer_amount > 100000"
    }
  ]
}
```

---

## 8. Key File Counts and Statistics

### Python Files by Package:

| Package | CLI | Core | Wrappers | Integrations | Gateway | Tests | Total |
|---------|-----|------|----------|--------------|---------|-------|-------|
| epi_cli | 25 | - | - | - | - | - | **25** |
| epi_core | - | 24 | - | - | - | - | **24** |
| epi_recorder | - | 8 | 4 | 12 | - | - | **24** |
| epi_gateway | - | - | - | - | 6 | - | **6** |
| pytest_epi | - | - | - | - | - | 2 | **2** |
| epi_analyzer | - | - | - | - | - | 2 | **2** |
| _cells | - | - | - | - | - | - | **12** |
| **Total** | **25** | **24** | **4** | **12** | **6** | **2** | **~100+** |

### Documentation Files:
- `README.md` - Main overview
- `CHANGELOG.md` - Version history
- `technical_overview.md` - High-level architecture
- `docs/EPI-SPEC.md` - Complete specification
- `docs/CLI.md` - All commands
- `docs/CONNECT.md` - Team review guide
- `docs/POLICY.md` - Policy guide
- `docs/TELEMETRY-PRIVACY.md` - Privacy commitment

### Test Coverage:
- 60+ test files
- Coverage of core, CLI, integrations, compliance
- Playwright E2E tests for viewer
- Mutation-resistant unit tests

---

## 9. Key Code Patterns

### 9.1 Context Manager Pattern

```python
# User code
with record("output.epi") as session:
    # Code here runs inside active recording context
    client.chat.completions.create(...)  # Captured
    session.log_step("decision", {...})  # Manual step
# Artifact packaged on exit

# Implementation
class EpiRecorderSession:
    def __enter__(self):
        set_recording_context(self)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        EPIContainer.pack(...)
        clear_recording_context()
```

### 9.2 Factory Pattern (Wrapper Creation)

```python
def wrap_openai(client, provider="openai"):
    """Factory that returns proxy without modifying original."""
    return TracedOpenAI(client, provider)

def wrap_client(client, provider="auto"):
    """Auto-detect provider type and return appropriate wrapper."""
    if isinstance(client, OpenAI):
        return wrap_openai(client)
    elif isinstance(client, Anthropic):
        return wrap_anthropic(client)
```

### 9.3 Visitor Pattern (Steps Processing)

```python
def analyze_steps(steps_file_path):
    """Visit each step, accumulate analysis state."""
    visitor = FaultAnalyzer()
    for step in load_steps_jsonl(steps_file_path):
        visitor.visit(step)
    return visitor.result()
```

### 9.4 Thread-Local Storage

```python
_thread_local = threading.local()

def set_recording_context(ctx):
    _thread_local.context = ctx

def get_current_session():
    return getattr(_thread_local, "context", None)
```

### 9.5 Canonical Serialization

```python
# All hashing uses CBOR canonical encoding:
def get_canonical_hash(model):
    # 1. Convert to dict
    # 2. Normalize datetime/UUID strings
    # 3. CBOR encode with canonical=True (sorted keys, minimal)
    # 4. SHA-256 hash
    return hashlib.sha256(cbor_bytes).hexdigest()
```

---

## 10. Architecture Diagrams

### Component Interaction:

```
┌─────────────────────────────────────────────────────────────────┐
│ User Code / CLI                                                 │
└────────────────┬────────────────────────────────────────────────┘
                 │
        ┌────────┴────────┬──────────────┐
        ▼                 ▼              ▼
    ┌─────────┐    ┌──────────┐   ┌─────────┐
    │ epi_cli │    │ Python   │   │ pytest  │
    │ Commands│    │ API      │   │ Plugin  │
    └────┬────┘    │ (record  │   └────┬────┘
         │         │  context)│        │
         └─────┬───┴──────┬───┴────────┘
               │          │
               ▼          ▼
        ┌─────────────────────────┐
        │  epi_recorder           │
        │  ├─ api.py              │
        │  ├─ patcher.py          │
        │  ├─ wrappers/           │
        │  └─ integrations/       │
        │      ├─ langchain.py    │
        │      ├─ langgraph.py    │
        │      ├─ litellm.py      │
        │      ├─ opentelemetry.py│
        │      └─ agt/            │
        └──┬─────────────────┬────┘
           │                 │
           ▼                 ▼
    ┌─────────────────┬─────────────────┐
    │ LLM Wrappers    │ Framework Hooks │
    │ ├─ OpenAI       │ ├─ LangChain    │
    │ ├─ Anthropic    │ ├─ LangGraph    │
    │ └─ LiteLLM      │ ├─ LiteLLM      │
    │                 │ └─ OpenTelemetry│
    └─────────────────┴─────────────────┘
              │                │
              └────────┬───────┘
                       ▼
            ┌──────────────────────┐
            │ RecordingContext     │
            │ ├─ EpiStorage (SQLite│
            │ ├─ Redactor         │
            │ └─ Step accumulation│
            └──────────┬───────────┘
                       ▼
            ┌──────────────────────┐
            │ epi_core             │
            │ ├─ schemas.py        │
            │ ├─ serialize.py      │
            │ ├─ container.py      │
            │ ├─ trust.py (Ed25519)│
            │ ├─ policy.py         │
            │ ├─ fault_analyzer.py │
            │ └─ ...               │
            └──────────┬───────────┘
                       ▼
            ┌──────────────────────┐
            │ .epi Artifact        │
            │ ├─ [EPI1 header]     │
            │ ├─ steps.jsonl       │
            │ ├─ environment.json  │
            │ ├─ manifest.json (sig)
            │ ├─ viewer.html       │
            │ └─ artifacts/        │
            └──────────┬───────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
    ┌────────┐  ┌────────┐  ┌──────────────┐
    │ View   │  │ Verify │  │ Share/Gateway│
    │(offline)  │(trust) │  │(team review) │
    └────────┘  └────────┘  └──────────────┘
```

---

## 11. Cryptographic Trust Model

```
.epi Artifact Created
        │
        ├─→ RecordingContext captures steps
        ├─→ ManifestModel built
        ├─→ SHA-256 hash computed (CBOR canonical)
        │
        ├─→ Load ~/.epi/keys/default.pem (Ed25519 private)
        ├─→ Ed25519.sign(manifest_hash)
        ├─→ Append signature to manifest
        │
        ├─→ EPIContainer.pack()
        │   ├─→ Create ZIP with all files
        │   ├─→ Write manifest.json last
        │   └─→ (v4.0+) Wrap in EPI1 envelope with SHA-256
        │
        └─→ Write .epi file to disk

Later: epi verify
        │
        ├─→ Read .epi file
        ├─→ Detect format (EPI1 vs ZIP)
        ├─→ Validate envelope SHA-256 (if v4.0+)
        │
        ├─→ Extract manifest.json
        ├─→ Verify each file hash matches manifest.file_manifest
        │   → integrity_ok
        │
        ├─→ Extract public_key from manifest
        ├─→ Recompute canonical JSON hash (exclude signature field)
        ├─→ Ed25519.verify(signature_bytes, manifest_hash, public_key)
        │   → signature_valid = True/False/None
        │
        └─→ Report: ArtifactInspectionResult
```

---

## 12. Data Model Relationships

```
ManifestModel (global metadata)
├─ workflow_id (UUID)
├─ created_at (timestamp)
├─ spec_version ("4.0.1")
├─ cli_command ("epi record ...")
├─ env_snapshot_hash (SHA-256 of environment.json)
│
├─ file_manifest (map)
│  └─ "steps.jsonl" → SHA-256
│  └─ "environment.json" → SHA-256
│  └─ "analysis.json" → SHA-256
│  └─ "viewer.html" → SHA-256
│  └─ "artifacts/..." → SHA-256
│
├─ public_key (hex ed25519 public key)
├─ signature ("ed25519:default:<hex>")
├─ container_format ("legacy-zip" | "envelope-v2")
│
└─ decision metadata (case-first UX)
   ├─ goal
   ├─ notes
   ├─ metrics
   ├─ approved_by
   └─ tags

steps.jsonl (NDJSON timeline)
├─ StepModel[0]
│  ├─ index: 0
│  ├─ timestamp: datetime
│  ├─ kind: "llm.request"
│  └─ content: {provider, model, messages}
│
├─ StepModel[1]
│  ├─ index: 1
│  ├─ kind: "llm.response"
│  └─ content: {choices, usage, latency}
│
└─ StepModel[n]
   └─ ...

environment.json (snapshot)
├─ python_version: "3.11.8"
├─ os: "Windows"
├─ packages: {numpy: "1.24", pandas: "2.0"}
├─ cwd: "/home/user/project"
├─ environment_vars: {API_KEY: "***REDACTED***"}
└─ timestamp: datetime

analysis.json (sealed, append-only)
├─ analyzer_version: "1.0.0"
├─ analysis_timestamp: datetime
├─ fault_detected: bool
├─ primary_fault: null | {kind, evidence, severity}
├─ policy_violations: [...]
├─ heuristic_observations: [...]
└─ manifest_hash: "sha256..."

review.json (append-only review ledger)
├─ review_version: "1.1.0"
├─ reviewed_by: "alice@company.com"
├─ reviewed_at: datetime
├─ decision: "approved" | "rejected" | "needs_revision"
├─ comments: "..."
├─ review_hash: SHA-256
├─ review_signature: "ed25519:..."
└─ evidence_binding_hash: SHA-256(sealed manifest)
```

---

## 13. Known Constraints and Design Decisions

### 13.1 Process Isolation

- **Recording runs in child process** for safety
- **sys.path patched** via sitecustomize to inject bootstrap
- **RecordingContext thread-local** for multi-threaded workflows
- **No monkey-patching by default** - explicit `wrap_openai()` required

### 13.2 Storage Durability

- **vs JSONL**: SQLite with transactions (crashes corrupt JSONL)
- **vs relational DB**: Single SQLite file in workspace (no setup)
- **vs in-memory**: Steps persisted to disk before packing

### 13.3 Cryptography

- **Ed25519 only** (no RSA/ECDSA) - simpler, faster for signing
- **CBOR canonical encoding** - deterministic across platforms
- **No key rotation** - v1.x design uses one key per identity
- **Public key embedded** - enables offline verification

### 13.4 Container Format Evolution

- **Legacy ZIP still supported** - backward compatible
- **New EPI1 envelope** - avoids "compressed folder" misclassification
- **Payload SHA-256 in header** - enables fail-fast validation
- **No compression** - STORE only for integrity

### 13.5 Evidence Immutability

- **steps.jsonl + manifest sealed** - not rewritten
- **review.json append-only** - new reviews added, old kept
- **Manifest contains file hashes** - tampering detectable
- **Policy + analysis also sealed** - can be re-run but originals kept

---

## 14. Performance Characteristics

### 14.1 Recording Overhead

- **Near-zero for non-LLM work** - only LLM calls logged
- **<5ms per LLM step** - minimal interception cost
- **SQLite commit per step** - atomic but some I/O cost

### 14.2 Serialization

- **CBOR canonical encoding** - slower than JSON but deterministic
- **get_canonical_hash()** - ~1ms for typical manifest
- **Ed25519 signing** - ~2ms per signature

### 14.3 Container Operations

- **pack()** - O(N) where N = file count, mostly ZIP creation
- **extract()** - O(N) file extraction + SHA-256 hashing
- **verify()** - O(N) hash verification, bottleneck is disk I/O

### 14.4 Typical Artifact Sizes

- **steps.jsonl** - ~100KB per 100 LLM calls
- **environment.json** - ~5-50KB
- **viewer.html** - ~500KB (embedded)
- **Total .epi** - 1-10MB typical, depends on artifact attachments

---

## 15. Security Considerations

### 15.1 Threat Model

| Threat | Mitigation |
|--------|-----------|
| Tampering with steps | SHA-256 manifest hashing + Ed25519 signature |
| Forged artifacts | Public key verification; pinning trusted keys |
| Exposed secrets | Automatic redaction + pattern matching |
| Execution hijacking | No code execution from .epi files (viewer is static HTML) |
| Replay attacks | Each artifact has unique workflow_id + timestamp |
| Key compromise | No automatic re-verification after key exposure |

### 15.2 Design Safeguards

- **No arbitrary code execution** - .epi is pure data + HTML
- **Viewer runs offline** - no network callbacks
- **Redaction enabled by default** - secrets removed before packaging
- **Signatures not required** - fall back to integrity checks
- **Review.json doesn't replace manifest** - original evidence sealed forever

### 15.3 Key Management

- **~/.epi/keys/ directory** - Home-owned, not shared
- **PEM format** - Standard format, portable
- **No key derivation** - Static ed25519 key (future improvement)
- **Key pinning** - Trust webhook signatures via known public keys

---

## 16. Future Roadmap (From Changelog)

### v4.0.1+ Planned:
- **Dashboard beta** - Graphical artifact management
- **Pilot program** - Enterprise telemetry + support
- **AGT ecosystem** - Closer Microsoft integration
- **Framework compliance** - LangChain, LangGraph native support

### Long-term Vision:
- **Key rotation** - Multi-key signing (future version)
- **Distributed ledger** - Append-only evidence across teams
- **Compliance exports** - EU AI Act evidence bundles
- **Framework standards** - EPI as industry standard format

---

## Summary

The **epi-recorder** is a mature, production-ready implementation of the EPI standard for portable AI evidence. It provides:

✅ **Complete Evidence Capture** - From code-level wrappers to framework integrations  
✅ **Cryptographic Trust** - Ed25519 signatures + deterministic hashing  
✅ **Offline Verification** - No internet required to inspect or verify artifacts  
✅ **Team Review** - Gateway + browser-based case viewer  
✅ **Framework Integration** - OpenAI, Anthropic, LangChain, LangGraph, LiteLLM, OpenTelemetry  
✅ **AGT Migration** - Import Microsoft governance evidence  
✅ **Privacy-First** - Automatic secret redaction + opt-in telemetry  
✅ **Comprehensive Testing** - 60+ test files, compliance + security focus

**Architecture**: Modular, extensible, with clear separation of concerns across CLI, core logic, wrappers, and integrations. Thread-safe recording context with atomic storage. CBOR canonical serialization ensures deterministic verification across platforms.

