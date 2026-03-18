<p align="center">
  <img src="https://raw.githubusercontent.com/mohdibrahimaiml/epi-recorder/main/docs/assets/logo.png" alt="EPI Logo" width="180"/>
  <br>
  <h1 align="center">EPI</h1>
  <p align="center"><strong>The flight recorder for AI agents</strong></p>
  <p align="center">
    <em>Capture, seal, and verify every decision your agents make - offline, tamper-proof, forever.</em>
  </p>
</p>

---

<p align="center">
  <a href="https://pypi.org/project/epi-recorder/"><img src="https://img.shields.io/pypi/v/epi-recorder?style=flat-square&label=pypi&color=0073b7" alt="PyPI Version"/></a>
  <a href="https://pepy.tech/project/epi-recorder"><img src="https://img.shields.io/pepy/dt/epi-recorder?style=flat-square&label=downloads&color=0073b7" alt="Downloads"/></a>
  <a href="https://github.com/mohdibrahimaiml/epi-recorder"><img src="https://img.shields.io/pypi/pyversions/epi-recorder?style=flat-square&color=0073b7" alt="Python"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/mohdibrahimaiml/epi-recorder?style=flat-square&color=0073b7" alt="License"/></a>
  <a href="https://github.com/mohdibrahimaiml/epi-recorder/stargazers"><img src="https://img.shields.io/github/stars/mohdibrahimaiml/epi-recorder?style=flat-square&color=0073b7" alt="Stars"/></a>
</p>

<p align="center">
  <strong>
    <a href="#quick-start">Quick Start</a> ·
    <a href="docs/EPI-SPEC.md">Specification</a> ·
    <a href="docs/CLI.md">CLI Reference</a> ·
    <a href="docs/POLICY.md">Policy Guide</a> ·
    <a href="CHANGELOG.md">Changelog</a> ·
    <a href="https://epilabs.org">Website</a>
  </strong>
</p>

---

## Why EPI?

Production agents fail in ways traditional logging can't capture.

A LangGraph agent processes 47 steps overnight. Step 31 makes a bad decision that cascades into failure. CloudWatch logs expired. You have no idea what the agent was "thinking."

**EPI captures everything** - every prompt, every response, every tool call, every state transition - sealed into a single, portable, cryptographically signed file. Open it a year later. Debug it locally. Present it in an audit. No cloud required.

```python
pip install epi-recorder
```

---

## Quick Start

### Record any LLM call in 3 lines

```python
from epi_recorder import record, wrap_openai
from openai import OpenAI

client = wrap_openai(OpenAI())

with record("my_agent.epi"):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "Plan a trip to Tokyo"}]
    )
```

**What gets captured:** full prompt & response, token usage & estimated cost, timestamps & model info, complete environment snapshot, and an Ed25519 signature.

For guaranteed evidence capture, instrument your workflow with `record()` or use a supported integration. `epi run` is best for scripts that already emit EPI steps.

### Windows double-click support

`.epi` files contain an embedded offline viewer, but Windows still needs an
installed handler application to open them by double-click. For the best
Windows experience, use the packaged installer so `.epi` is registered as a
first-class file type.

```text
Recommended for Windows users:
  install epi-setup-<version>.exe

Developer path:
  pip install epi-recorder
  epi associate --system   # or: epi associate
```

### Inspect the results

```bash
epi view my_agent.epi    # Opens in browser - no login, no cloud, no internet
epi verify my_agent.epi  # Cryptographic integrity check
```

---

## New in v2.8.4 - Windows Double-Click Stability

- Windows file association now prefers a real `epi.exe` launcher before falling back to the VBS helper
- this makes double-click opening much more stable for installed EPI on Windows
- the older VBS path remains as a compatibility fallback for Python-only environments where needed

## New in v2.8.3 - Viewer Consistency and Colab-Friendly Packaging

- viewer now derives fault presence from the embedded primary finding, avoiding contradictory `Fault detected: No` states
- manifest facts no longer risk showing `Files in manifest: undefined`
- analyzer wording now clearly separates deterministic policy matches from heuristic observations
- package dependency pins are tightened to avoid common Colab resolver warnings and the deprecated `typer[all]` extra

This patch release hardens the default user path and cleans up release consistency.

- **Honest `epi run` behavior**: if a script records `0` execution steps, `epi run` now exits non-zero and clearly explains that the script is not instrumented.
- **Truthful analysis for empty artifacts**: `epi analyze` now reports `No data to analyze` instead of implying a clean run.
- **Safer onboarding**: `epi init` now generates an explicitly instrumented demo using `record()` and tells users to run it with plain Python.
- **Viewer empty-data warning**: zero-step artifacts now show a visible warning so they cannot be mistaken for meaningful evidence.
- **Version consistency**: Python package version surfaces are aligned again across the release.

## New in v2.8.1 - Viewer Trust Fixes and Policy Clarifications

This patch release hardens the embedded viewer and trust rendering path.

- **Correct viewer trust states**: the viewer now receives trust context before app initialization, so `Signed`, `Unsigned`, and `Tampered` render correctly in the main viewer flow.
- **Current viewer embedded in new artifacts**: newly generated `.epi` files now reliably carry the updated `v2.8.x` viewer template.
- **Policy clarity**: `epi_policy.json` behavior is now documented more clearly, including where to store it and when it is loaded.
- **Policy compatibility improvements**: `prohibition_guard` accepts both `pattern` and `prohibited_pattern`, and `threshold_guard` supports `watch_for` as a fallback field selector.

## New in v2.8.0 - Policy-Grounded Fault Analysis and Windows File UX

This release makes EPI's policy and fault-analysis story real at runtime and further hardens the `.epi` desktop experience on Windows.

- **Full policy rule enforcement**: `constraint_guard`, `sequence_guard`, `threshold_guard`, and `prohibition_guard` are all enforced by the analyzer.
- **Sealed policy context**: `policy.json` and `analysis.json` are embedded into the artifact so later reviewers can see both the execution and the rules active at the time.
- **Human review flow**: `epi review` turns flagged policy violations into a practical workflow with additive `review.json` records.
- **Windows file-opening reliability**: the `.epi` handler now uses the repaired standalone launcher path, supports a custom `.epi` icon, and keeps a self-healing repair path for developer installs.
- **Installer-first Windows UX**: the packaged installer remains the recommended path for normal users, with `epi associate` as the developer and repair fallback.

### Practical workflow

```text
define policy -> run agent with EPI -> open .epi -> inspect analysis -> review flagged faults
```

Key commands:

```bash
epi policy init
epi policy validate
python my_agent.py
epi view my_agent.epi
epi review my_agent.epi
```

### Where `epi_policy.json` goes

Today, `epi_policy.json` should live in the same working directory where you run EPI.

Example:

```text
loan-underwriting/
  underwriter.py
  epi_policy.json
```

```bash
cd loan-underwriting
python underwriter.py
```

EPI loads that file during packing, embeds it into the artifact as `policy.json`, and writes analyzer output as `analysis.json`.

See [`docs/POLICY.md`](docs/POLICY.md) for the full explanation of how policy loading and fault analysis work.

## Framework Integrations (v2.6.0)

EPI now plugs directly into the tools you already use. **Zero refactoring required.**

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

```
======================== EPI Evidence Summary ========================
  [OK] test_auth_flow.epi (signed, 12 steps)
  [OK] test_payment.epi (signed, 8 steps)
  [OK] test_refund.epi (signed, 6 steps)
======================================================================
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

---

## The `.epi` File Format

An `.epi` file is a self-contained ZIP archive:

```
my_agent.epi
|- mimetype              # "application/epi+zip"
|- manifest.json         # Metadata + Ed25519 signature + content hashes
|- steps.jsonl           # Execution timeline (NDJSON)
|- environment.json      # Runtime environment snapshot
|- *.db                  # Crash-safe SQLite storage
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

EPI is not an observability dashboard. It's a **durable execution artifact system.**

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
| `epi view <file.epi>` | Open in browser viewer |
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
| **2.8.4** | 2026-03-18 | **Windows double-click stability** - prefer a real `epi.exe` open command over the VBS helper so `.epi` files open more reliably on Windows installs |
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

**Current (v2.8.4):**
- [Done] Framework-native integrations (LiteLLM, LangChain, OpenTelemetry)
- [Done] CI/CD verification (GitHub Action, pytest plugin)
- [Done] OpenAI streaming support
- [Done] Global install for automatic recording

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
| **[Investor Demo](docs/INVESTOR-DEMO.md)** | 3-minute live investor screenshare guide |
| **[CHANGELOG](CHANGELOG.md)** | Release notes |
| **[Contributing](CONTRIBUTING.md)** | Contribution guidelines |
| **[Security](SECURITY.md)** | Security policy and vulnerability reporting |

---

## Beta Program

We're looking for teams running agents in production.

**You get:** priority support, free forever, custom integrations.

**[Apply for Beta Access](https://www.epilabs.org/contact.html)**

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

## Traction

**6,500+ downloads** in 10 weeks · **v2.8.4** shipped Mar 2026

> *"EPI saved us 4 hours debugging a production agent failure."*
> - ML Engineer, Fintech

> *"The LangGraph integration is killer. Zero config."*
> - AI Platform Team Lead

---

## License

MIT License. See **[LICENSE](./LICENSE)**.

<p align="center">
  <strong>Built by <a href="https://epilabs.org">EPI Labs</a></strong><br>
  <em>Making AI agent execution verifiable.</em>
</p>

