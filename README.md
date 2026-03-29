<p align="center">
  <img src="https://raw.githubusercontent.com/mohdibrahimaiml/epi-recorder/main/docs/assets/logo.png" alt="EPI Logo" width="180"/>
  <br>
  <h1 align="center">EPI</h1>
  <p align="center"><strong>3 lines of code. Your AI agent's decisions — captured, signed, and openable in any browser forever.</strong></p>
  <p align="center">
    <em>No cloud. No login. No internet required.</em>
  </p>
</p>

---

<p align="center">
  <a href="https://pypi.org/project/epi-recorder/"><img src="https://img.shields.io/pypi/v/epi-recorder?style=flat-square&label=PyPI&color=0073b7" alt="PyPI Version"/></a>
  <a href="https://pepy.tech/project/epi-recorder"><img src="https://img.shields.io/pepy/dt/epi-recorder?style=flat-square&label=downloads&color=0073b7" alt="Downloads"/></a>
  <a href="https://pypi.org/project/epi-recorder/"><img src="https://img.shields.io/pypi/pyversions/epi-recorder?style=flat-square&label=python&color=0073b7" alt="Supported Python Versions"/></a>
  <a href="https://github.com/mohdibrahimaiml/epi-recorder/blob/main/LICENSE"><img src="https://img.shields.io/github/license/mohdibrahimaiml/epi-recorder?style=flat-square&label=license&color=0073b7" alt="License"/></a>
  <a href="https://github.com/mohdibrahimaiml/epi-recorder/stargazers"><img src="https://img.shields.io/github/stars/mohdibrahimaiml/epi-recorder?style=flat-square&label=stars&color=0073b7" alt="GitHub Stars"/></a>
</p>

<p align="center">
  <a href="https://colab.research.google.com/github/mohdibrahimaiml/epi-recorder/blob/main/colab_demo.ipynb">
    <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open in Colab"/>
  </a>
  &nbsp;
  <a href="https://epilabs.org/verify">
    <img src="https://img.shields.io/badge/verify-.epi%20files-green?style=flat-square&logo=checkmarx" alt="Verify .epi files online"/>
  </a>
</p>

<p align="center">
  <strong>
    <a href="#install">Install</a> ·
    <a href="#try-it-now--no-api-key">Try It Now</a> ·
    <a href="#add-to-your-code">Add to Your Code</a> ·
    <a href="#pytest-plugin">pytest</a> ·
    <a href="#framework-integrations">Integrations</a> ·
    <a href="docs/EPI-SPEC.md">Specification</a> ·
    <a href="docs/CLI.md">CLI Reference</a> ·
    <a href="docs/POLICY.md">Policy Guide</a> ·
    <a href="CHANGELOG.md">Changelog</a> ·
    <a href="https://epilabs.org">Website</a>
  </strong>
</p>

---

## Install

```bash
pip install epi-recorder
```

---

## Try It Now — No API Key

**Option A: On your machine (60 seconds)**

```bash
pip install epi-recorder
epi demo
```

This runs a complete refund-approval demo using a built-in mock LLM:

1. Agent runs, makes a decision, captures every step
2. Creates a signed `.epi` case file locally
3. Opens the browser review view (no login, no internet)
4. Lets you export and cryptographically verify it

> Already have an OpenAI key? Set `OPENAI_API_KEY` and the demo uses the real API instead.

**Option B: In your browser (no install)**

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mohdibrahimaiml/epi-recorder/blob/main/colab_demo.ipynb)

Click the badge above. No local setup. The notebook runs `pip install epi-recorder` inside Colab and walks through the same refund-review loop in your browser: setup → run → review → verification.

**Option C: Verify an existing .epi file**

Drag and drop any `.epi` file at [epilabs.org/verify](https://epilabs.org/verify) — no install, no login, verification runs entirely in your browser.

---

## Add to Your Code

```python
from epi_recorder import record, wrap_openai
from openai import OpenAI

client = wrap_openai(OpenAI())

with record("my_agent.epi"):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Plan a trip to Tokyo"}]
    )
```

**What EPI creates:** a portable `.epi` case file with the decision timeline, environment snapshot, browser review view, and trust metadata. When rules are present, EPI also embeds `policy.json` and `analysis.json`. Human review can later add review notes without rewriting the original record.

Open it:

```bash
epi view my_agent.epi    # browser review view — offline, no login
epi verify my_agent.epi  # cryptographic integrity check
```

`epi view` is the canonical EPI review experience. Older desktop viewer surfaces remain legacy/internal compatibility paths and are not the recommended front door.

### Record a full agent run with approvals and tool calls

```python
from epi_recorder import record

with record("refund_agent.epi", goal="Resolve customer refund safely") as epi:
    with epi.agent_run(
        "refund-agent",
        user_input="Refund order 123",
        session_id="sess-001",
        task_id="refund-123",
    ) as agent:
        agent.plan("Look up the order, confirm approval status, then decide.")
        agent.tool_call("lookup_order", {"order_id": "123"})
        agent.tool_result("lookup_order", {"status": "paid", "amount": 120})
        agent.approval_request("approve_refund", reason="Amount exceeds auto threshold")
        agent.approval_response("approve_refund", approved=True, reviewer="manager@company.com")
        agent.decision("approve_refund", confidence=0.91)
```

The resulting `.epi` shows lineage, approvals, tool calls, memory activity, and pause/resume checkpoints as one signed case file.

### Local LLM — free, unlimited development

```python
client = wrap_openai(OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
))

with record("test.epi"):
    response = client.chat.completions.create(model="llama3", messages=[...])
```

---

## pytest Plugin

One flag. Signed `.epi` evidence per test. No code changes.

```bash
pytest --epi                    # generates signed .epi per test
pytest --epi --epi-dir=evidence # custom output directory
```

Every test failure leaves a signed case file you can open, verify, and share. Useful for catching regressions in multi-step agent behavior over time.

**Share a test failure**: Attach the `.epi` file to a GitHub issue or PR. Anyone can open it in their browser. No EPI install required on their end — the review view is embedded inside the file.

---

## The Full Loop

```text
define policy → run workflow → inspect fault analysis → confirm/dismiss in review → verify trust
```

```bash
epi policy init          # create epi_policy.json with control rules
python my_workflow.py    # run your instrumented script
epi view my_workflow.epi   # open in browser
epi review my_workflow.epi # add human review notes
epi verify my_workflow.epi # cryptographic check
```

---

## Starter Kits

Production-shaped examples for common consequential workflows. Pick one, run it, then adapt to your code.

| Kit | What it covers |
|:----|:---------------|
| [`examples/starter_kits/refund/`](examples/starter_kits/refund/) | Refund approval agent with human sign-off, policy rules, and full audit trail |

More kits coming: claims, underwriting, support escalation.

---

## What EPI Is

EPI is the evidence layer for consequential AI decisions — the ones that approve refunds, underwrite loans, escalate support cases, or trigger operational actions.

When one of those runs goes wrong, traditional logs help you debug. EPI helps you *defend* the decision after an incident, audit request, model-risk review, or compliance challenge. It creates one portable `.epi` case file that answers:

- What actually happened, step by step?
- Which rule was active at the time?
- Did a human reviewer confirm or dismiss it?
- Is this case file still trustworthy, or was it tampered with?

EPI is not an observability dashboard. It sits beside observability as the durable evidence layer.

### Why EPI vs. Alternatives

| | **EPI** | LangSmith | Arize | W&B |
|:--|:--------|:----------|:------|:----|
| **Works offline** | Yes — air-gapped ready | No — cloud required | No | No |
| **Tamper-proof** | Yes — Ed25519 signatures | No | No | No |
| **Open format** | Yes — `.epi` spec | No — proprietary | No | No |
| **Cost** | **Free** (MIT) | $99+/mo | Custom | $50+/mo |

> EPI complements these tools. Use LangSmith for live traces, EPI for durable evidence.

---

## For Compliance and Governance Teams

EPI is designed for teams facing real regulatory pressure:

- **EU AI Act** — tamper-evident audit trails with cryptographic proof
- **FDA / Healthcare** — signed decision records for AI-assisted diagnostics
- **Financial services (SEC, ECOA)** — litigation-grade evidence for automated decisions
- **Data governance** — automatic PII redaction with `security.redaction` steps
- **Air-gapped deployment** — no internet required, ever

The portability advantage: you can hand a regulator a single `.epi` file. They verify it at [epilabs.org/verify](https://epilabs.org/verify) — drag and drop, no login, no install, no calling you back. Verification runs client-side in their browser.

For the enterprise architecture boundary, see [docs/OPEN-CORE-ARCHITECTURE.md](docs/OPEN-CORE-ARCHITECTURE.md).
For self-hosted deployment and operator runbook, see [docs/SELF-HOSTED-RUNBOOK.md](docs/SELF-HOSTED-RUNBOOK.md).

---

## Advanced / Operator Workflows

### Gateway path for AI infrastructure teams

```bash
epi gateway serve
epi gateway serve --users-file config/gateway-users.example.json
```

Point SDKs, adapters, or proxies at one capture endpoint. Supports OpenAI-compatible `/v1/chat/completions`, Anthropic-compatible `/v1/messages`, LiteLLM, and generic LLM adapters. Keeps the `.epi` export path for proof and audit.

### Windows double-click support

`.epi` files contain an embedded offline viewer, but Windows needs a registered handler to open them by double-click.

```text
Recommended for Windows users:
  install epi-setup-<version>.exe

Developer path:
  pip install epi-recorder
  epi associate --system   # or: epi associate
```

---

## What Changed in v2.8.10

- **Notebook packaging correction**
  - `colab_demo.ipynb` and `EPI NEXUA VENTURES.ipynb` now ship in the GitHub repo and source distribution
  - the wheel remains focused on runtime/package code instead of installing demo notebooks into the environment
- **Release audit hardening**
  - the release gate now audits the source tarball and fails if the required notebooks are missing or old notebook snapshots leak into the release
- **2.8.9 runtime hotfixes preserved**
  - the Colab notebooks still render the actual extracted `viewer.html` inside an iframe
  - reusable approval policies still accept both `approval_id` and `id`
  - `applies_at` still accepts either a single intervention point or a list

EPI still stores the machine-readable rulebook as `epi_policy.json`, but `v2.8.10` makes the packaged release honest about where the demo notebooks live: in the repo and source release, not as installed runtime assets.

Older release notes live in [CHANGELOG.md](CHANGELOG.md).

For policy placement and rule design, see [docs/POLICY.md](docs/POLICY.md).

## Framework Integrations

EPI fits the stack your AI platform team already uses. **Start with one workflow, not a rewrite.**

### LiteLLM - 100+ Providers in One Line

```python
import litellm
from epi_recorder.integrations.litellm import EPICallback

litellm.callbacks = [EPICallback()]  # That's it - all calls are now recorded

response = litellm.completion(model="gpt-4", messages=[...])
response = litellm.completion(model="claude-3-opus", messages=[...])
response = litellm.completion(model="ollama/llama3", messages=[...])
# Every call -> signed .epi evidence
```

### LangChain - Full Event Capture

```python
from langchain_openai import ChatOpenAI
from epi_recorder.integrations.langchain import EPICallbackHandler

llm = ChatOpenAI(model="gpt-4", callbacks=[EPICallbackHandler()])
result = llm.invoke("Analyze this contract for risk...")
# Captures: LLM calls, tool invocations, chain steps, retriever queries, agent decisions
```

### OpenAI Streaming - Real-Time Evidence

```python
from epi_recorder import record, wrap_openai
from openai import OpenAI

client = wrap_openai(OpenAI())

with record("stream_demo.epi"):
    stream = client.chat.completions.create(
        model="gpt-4", stream=True,
        messages=[{"role": "user", "content": "Write a poem"}]
    )
    for chunk in stream:
        print(chunk.choices[0].delta.content or "", end="")
# Chunks yielded in real-time, assembled response logged with full token usage
```

### pytest Plugin - Evidence per Test

```bash
pip install epi-recorder
pytest --epi                    # Generates signed .epi per test
pytest --epi --epi-dir=evidence # Custom output directory
```

### GitHub Action - CI/CD Verification

```yaml
# .github/workflows/verify.yml
- name: Verify EPI evidence
  uses: mohdibrahimaiml/epi-recorder/.github/actions/verify-epi@main
  with:
    path: ./evidence
    fail-on-tampered: true
```

### OpenTelemetry - Bridge to Existing Infra

```python
from epi_recorder.integrations.opentelemetry import setup_epi_tracing

setup_epi_tracing(service_name="my-agent")
# All OTel spans -> signed .epi files automatically
```

### Global Install - Record Everything

```bash
epi install --global    # All Python processes now auto-record
epi uninstall --global  # Clean removal, one command
```

Set `EPI_AUTO_RECORD=0` to disable without uninstalling.

---

## Architecture

```mermaid
flowchart LR
    A["Agent Code"] -->|"record()"| B["Capture Layer"]
    B -->|"Wrapper/API"| C["Recorder"]
    C -->|"Atomic Write"| D["SQLite WAL"]
    D -->|"Finalize"| E["Packer"]
    F["Private Key"] -->|"Ed25519 Sign"| E
    E -->|"ZIP"| G["agent.epi"]
```

**Design principles:**

| Principle | How |
|:----------|:----|
| **Crash-safe** | SQLite WAL - no data loss, even if agents crash mid-execution |
| **Explicit capture** | Evidence is intentional and reviewable in code |
| **Cryptographic proof** | Ed25519 signatures (RFC 8032) that can't be forged or backdated |
| **Offline-first** | Zero cloud dependency - works in air-gapped environments |
| **Framework-native** | Plugs into LiteLLM, LangChain, OpenTelemetry, pytest - no refactoring |

---

## Supported Providers & Frameworks

### Direct Wrappers

| Provider | Integration | Streaming |
|:---------|:------------|:----------|
| **OpenAI** | `wrap_openai()` | Yes - Real-time chunk capture |
| **Anthropic** | `wrap_anthropic()` | Yes |
| **Google Gemini** | Explicit API | - |
| **Ollama** (local) | `wrap_openai()` with local endpoint | Yes |
| **Any HTTP LLM** | `log_llm_call()` explicit API | - |

### Framework Integrations

| Framework | Integration | Coverage |
|:----------|:------------|:---------|
| **OpenAI Agents-style events** | `OpenAIAgentsRecorder` | Stream event bridge into agent-native EPI steps |
| **LiteLLM** | `EPICallback` | 100+ providers, one line |
| **LangChain** | `EPICallbackHandler` | LLM, tools, chains, retrievers, agents |
| **LangGraph** | `EPICheckpointSaver` | Native checkpoint backend |
| **OpenTelemetry** | `EPISpanExporter` | Span -> .epi conversion |
| **pytest** | `--epi` flag | Signed evidence per test |
| **GitHub Actions** | `verify-epi` action | CI/CD pipeline verification |

---

## Key Features

### Async Support

Non-blocking I/O for LangGraph, AutoGen, and async-first frameworks:

```python
async with record("agent.epi"):
    response = await async_client.chat.completions.create(...)
    await epi.alog_step("custom.event", {"reasoning": "..."})
```

### Local LLM Support

Record against Ollama for free, unlimited development:

```python
client = wrap_openai(OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
))

with record("test.epi"):
    response = client.chat.completions.create(
        model="deepseek-r1:7b",
        messages=[{"role": "user", "content": "Debug this code..."}]
    )
```

### Agent Analytics

Track performance across hundreds of runs:

```python
from epi_recorder import AgentAnalytics

analytics = AgentAnalytics("./production_runs")
summary = analytics.performance_summary()

print(f"Success rate: {summary['success_rate']:.1%}")
print(f"Avg cost: ${summary['avg_cost_per_run']:.3f}")
print(f"Most common error: {summary['top_errors'][0]}")

analytics.generate_report("dashboard.html")  # Interactive HTML dashboard
```

### LangGraph Checkpoint Integration

```python
from langgraph.graph import StateGraph
from epi_recorder.integrations import EPICheckpointSaver

graph = StateGraph(AgentState)
checkpointer = EPICheckpointSaver("my_agent.epi")

result = graph.invoke(
    {"messages": [HumanMessage(content="...")]},
    {"configurable": {"thread_id": "user_123"}},
    checkpointer=checkpointer
)
# Captures all state transitions, checkpoint metadata, and agent decision points
```

### OpenAI Agents Event Bridge

```python
from epi_recorder import record
from epi_recorder.integrations import OpenAIAgentsRecorder

with record("support_agent.epi") as epi:
    with OpenAIAgentsRecorder(epi, agent_name="support-agent", user_input="Reset customer password") as recorder:
        for event in streamed_result.stream_events():
            recorder.consume(event)
```

This starter adapter maps common agent stream events into:
- `agent.message`
- `tool.call` / `tool.response`
- `agent.handoff`
- `agent.approval.request` / `agent.approval.response`
- `agent.memory.read` / `agent.memory.write`
- `agent.decision`

---

## The `.epi` File Format

An `.epi` file is a self-contained ZIP archive:

```
my_agent.epi
|- mimetype              # "application/vnd.epi+zip"
|- manifest.json         # Metadata + Ed25519 signature + content hashes
|- steps.jsonl           # Execution timeline (NDJSON)
|- environment.json      # Runtime environment snapshot
`- viewer.html           # Self-contained offline viewer (opens in any browser)
```

| Property | Detail |
|:---------|:-------|
| **Signatures** | Ed25519 (RFC 8032) |
| **Hashing** | SHA-256 content addressing |
| **Key Storage** | Local keyring, user-controlled |
| **Verification** | Client-side, zero external dependencies |
| **Viewer** | Embedded HTML - works offline forever |

The embedded viewer is part of the artifact, but operating systems do not
execute code from inside a file automatically. Double-click support requires a
registered external handler such as the Windows installer or `epi associate`.

See **[EPI Specification](docs/EPI-SPEC.md)** for technical details.

---

## Why EPI vs. Alternatives

EPI is not an observability dashboard. It is **AI evidence infrastructure for consequential AI decisions.**

| | **EPI** | LangSmith | Arize | W&B |
|:--|:--------|:----------|:------|:----|
| **Works offline** | Yes - Air-gapped ready | No - Cloud required | No - Cloud required | No - Cloud required |
| **Tamper-proof** | Yes - Ed25519 signatures | No | No | No |
| **Open format** | Yes - `.epi` spec | No - Proprietary | No - Proprietary | No - Proprietary |
| **Agent state** | Yes - Full checkpoints | Traces only | Predictions only | Experiments only |
| **Compliance** | Yes - EU AI Act, FDA, SEC | Limited | Limited | Not designed |
| **Local LLMs** | Yes - Ollama, llama.cpp | No | No | No |
| **CI/CD native** | Yes - GitHub Action + pytest | No | No | No |
| **Framework hooks** | Yes - LiteLLM, LangChain, OTel | LangChain only | No | No |
| **Cost** | **Free** (MIT) | $99+/mo | Custom | $50+/mo |

> **EPI complements these tools.** Use LangSmith for live traces, EPI for durable evidence.

---

## Use Cases

### Developer Workflow

- Debug multi-step agent failures with full decision tree visibility
- A/B test prompts and models with side-by-side `.epi` comparison
- Track agent performance over time (success rates, costs, errors)
- Replay production failures locally with Ollama
- Share `.epi` files with teammates - they open in any browser

### Enterprise Compliance

- **EU AI Act** - tamper-evident audit trails with cryptographic proof
- **FDA / Healthcare** - signed decision records for AI-assisted diagnostics
- **Financial services (SEC)** - litigation-grade evidence for automated trading
- **Data governance** - automatic PII redaction with `security.redaction` steps
- **Air-gapped deployment** - no internet required, ever

### Works With

LangGraph · LangChain · LiteLLM · AutoGen · CrewAI · OpenTelemetry · pytest · GitHub Actions · Ollama · Any Python agent

---

## CLI Reference

| Command | Purpose |
|:--------|:--------|
| `epi run <script.py>` | Record execution to `.epi` |
| `epi verify <file.epi>` | Verify integrity and signature |
| `epi view <file.epi>` | Open in browser review view |
| `epi keys list` | Manage signing keys |
| `epi debug <file.epi>` | Heuristic analysis |
| `epi chat <file.epi>` | Natural language querying |
| `epi install --global` | Auto-record all Python processes |
| `epi uninstall --global` | Remove auto-recording |
| `epi associate` | Register OS file association for double-clicking |
| `epi unassociate` | Remove OS file association |

See **[CLI Reference](docs/CLI.md)** for full documentation.

---

## Release History

| Version | Date | Highlights |
|:--------|:-----|:-----------|
| **2.8.10** | 2026-03-24 | **Notebook packaging correction** - ship the two supported Colab notebooks in the source release, add sdist audit coverage, and keep the wheel runtime-focused |
| **2.8.9** | 2026-03-24 | **Colab viewer and policy schema hotfix** - real embedded viewer rendering in notebooks, approval-policy ID alias support, list-valued `applies_at`, and refreshed Colab demos |
| **2.8.8** | 2026-03-24 | **Tight release hardening** - better `epi policy validate` diagnostics, OpenAI Agents-style event bridge, viewer auto-expand on control jumps, and installer regression guard |
| **2.8.7** | 2026-03-24 | **Policy v2 foundation and trust hardening** - control outcomes in artifacts, `tool_permission_guard`, viewer jump-to-step review flow, desktop viewer signature verification, and release/version consistency fixes |
| **2.8.6** | 2026-03-22 | **Agent-first product hardening** - clearer reviewer UX, stronger first-run onboarding, print capture in `epi run`, better viewer guidance, and agent-shaped evidence with approvals and lineage |
| **2.8.5** | 2026-03-20 | **Reliability patch** - guided policy UX, stable `epi review` CLI invocation, bootstrap manual-step support in `epi run`, and stronger Windows association repair paths |
| **2.8.4** | 2026-03-18 | **Windows double-click stability** - stronger association repair and diagnostics for desktop opening workflows |
| **2.8.3** | 2026-03-18 | **Viewer consistency and Colab-friendly packaging** - remove contradictory fault states, fix manifest fact fallback, clarify analyzer wording, and cap dependencies for cleaner installs |
| **2.8.2** | 2026-03-18 | **Front-door reliability and version consistency** - Fail loudly on zero-step `epi run`, report `No data to analyze` for empty artifacts, generate an instrumented `epi init` demo, and align package version surfaces |
| **2.8.1** | 2026-03-17 | **Viewer trust fixes and policy clarifications** - Correct `Signed` / `Unsigned` / `Tampered` rendering, embed the current viewer in new artifacts, and document `epi_policy.json` more clearly |
| **2.8.0** | 2026-03-16 | **Policy-grounded fault analysis and Windows file UX** - Enforced threshold/prohibition policy rules, sealed policy + analysis workflow, stronger `.epi` opening and icon behavior |
| **2.7.2** | 2026-03-14 | **Verification reliability & CLI polish** - Legacy signature compatibility, analytics import safety, missing exports, CLI exit code fixes |
| **2.7.1** | 2026-03-12 | **Decentralized trust & Self-healing** - Zero-config verification, OS registry self-repair, SQL integrity fixes, cryptographic symmetry |
| **2.7.0** | 2026-03-11 | **Zero-friction desktop integration** - Double-click `.epi` files to open, cross-platform file association, Unicode path safety |
| **2.6.0** | 2026-02-20 | **Framework integrations** - LiteLLM, LangChain, OpenTelemetry, pytest plugin, GitHub Action, streaming support, global install |
| **2.5.0** | 2026-02-13 | Anthropic Claude wrapper, path resolution fix |
| **2.4.0** | 2026-02-12 | Agent Analytics, async/await, LangGraph, Ollama |
| **2.3.0** | 2026-02-06 | Explicit API, wrapper clients |
| **2.2.0** | 2026-01-30 | SQLite WAL, async support, thread safety |
| **2.1.3** | 2026-01-24 | Google Gemini support |
| **1.0.0** | 2025-12-15 | Initial release |

See **[CHANGELOG.md](./CHANGELOG.md)** for detailed release notes.

---

## Roadmap

**Current (v2.8.10):**
- [Done] Framework-native integrations (LiteLLM, LangChain, OpenTelemetry)
- [Done] CI/CD verification (GitHub Action, pytest plugin)
- [Done] OpenAI streaming support
- [Done] Global install for automatic recording
- [Done] Agent-first recording and review surfaces
- [Done] Actionable policy validation and OpenAI Agents-style event bridge
- [Done] Real embedded viewer rendering in Colab demos and Policy v2 schema hotfixes
- [Done] Ship the supported Colab notebooks in the source release with audit coverage

**Next:**
- [Planned] Time-travel debugging (step through any past run)
- [Planned] Team collaboration features
- [Planned] Managed cloud platform (optional)
- [Planned] VS Code extension for `.epi` file viewing

---

## Documentation

| Document | Description |
|:---------|:------------|
| **[EPI Specification](docs/EPI-SPEC.md)** | Technical specification for `.epi` format |
| **[CLI Reference](docs/CLI.md)** | Command-line interface documentation |
| **[Policy Guide](docs/POLICY.md)** | How policy, fault analysis, and rulebooks work |
| **[Policy v2 Design](docs/POLICY-V2-DESIGN.md)** | Proposed enterprise policy model with layers, enforcement modes, and richer control types |
| **[CHANGELOG](CHANGELOG.md)** | Release notes |
| **[Contributing](CONTRIBUTING.md)** | Contribution guidelines |
| **[Security](SECURITY.md)** | Security policy and vulnerability reporting |

---

## Contributing

```bash
git clone https://github.com/mohdibrahimaiml/epi-recorder.git
cd epi-recorder
pip install -e ".[dev]"
pytest
```

See **[CONTRIBUTING.md](./CONTRIBUTING.md)** for guidelines.

---

## License

MIT License. See **[LICENSE](./LICENSE)**.

<p align="center">
  <strong>Built by <a href="https://epilabs.org">EPI Labs</a></strong><br>
  <em>Making AI agent execution verifiable.</em>
</p>
