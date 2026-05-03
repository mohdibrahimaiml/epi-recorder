# EPI DOC v4.0.3

Author: Codex
Date: 2026-05-03
Repo analyzed: `C:\Users\dell\epi-recorder`
Release line observed in source: `v4.0.3`

---

## 1. What EPI is

EPI turns an AI workflow into a sealed, reviewable case file.

Its core job:

- capture what happened during an AI workflow execution
- seal it into one portable `.epi` artifact
- let reviewers reopen and investigate it later
- let anyone verify the artifact was not changed after sealing

The product center is the artifact itself, not a hosted dashboard. One file, portable, verifiable, self-contained.

---

## 2. What v4.0.3 adds over v4.0.2

`v4.0.3` is a forensic polish release. Every change here either fixes a trust surface or makes the viewer more honest and more readable. No new artifact format changes. No breaking API changes. The ten specific improvements are:

### 2.1 Forensic Document Viewer -- complete redesign

The embedded browser viewer was replaced from scratch.

Old viewer: 8,382-line SPA with inbox queues, message filters, team panels, and dashboard chrome. That surface was oriented around a team workspace, not a forensic investigation.

New viewer: 2,340-line forensic document viewer. The design principles are:
- monospace aesthetic throughout
- numbered sections (section 0 through section 8) so every panel has a stable address
- expandable step rows -- click any step to expand a terminal-style JSON block
- heatmap timeline bar showing step density across the execution timeline
- fixed sidebar navigation that stays anchored while you scroll

Section numbering:
- section 0: artifact header (name, status badges, signature state)
- section 1: trust report (signature verification, forensic pass/fail, integrity)
- section 2: case context (goal, notes, metrics, approved_by from manifest)
- section 3: environment (captured platform, Python version, hostname)
- section 4: policy (policy name, rules, evaluation outcome)
- section 5: review (human review record if present)
- section 6: evidence timeline (all steps, expandable, heatmap bar)
- section 7: attachments (artifact files list)
- section 8: raw manifest (the sealed manifest.json for inspection)

The viewer is self-contained HTML. No CDN. No external requests. Opens offline.

### 2.2 workflow_name resolution fixed

In v4.0.2, the viewer title and source name always showed the raw UUID session ID instead of the human-readable workflow name.

Root cause: both `epi_core/container.py` (`_create_embedded_viewer`) and `epi_cli/view.py` (`_build_preloaded_case_payload`) were reading from the wrong location.

Fix: both now read `session.start` step content's `workflow_name` field as the authoritative source. That is where the recorder writes the name. The viewer title and the case header now show the workflow name correctly.

If you record with:

```python
with epi.record("my-case.epi", workflow_name="Loan Approval v3") as session:
    ...
```

The viewer now shows `Loan Approval v3` as the case title, not a UUID.

### 2.3 Case context surfaced in viewer

Four manifest fields that were previously invisible in the viewer are now shown as a dedicated section 2 (Case Context):

- `manifest.goal` -- the stated purpose of this workflow run
- `manifest.notes` -- freeform operator notes attached at record time
- `manifest.metrics` -- key/value performance or outcome metrics
- `manifest.approved_by` -- the approver identity if a human approval was captured

These fields let operators annotate a case at capture time so reviewers immediately understand context without reading raw steps.

### 2.4 Smart step summaries

In v4.0.2 every step in the timeline showed a raw `JSON.stringify` dump. That was unreadable for most step kinds.

In v4.0.3, 14+ step kinds have human-readable summaries:

| Step kind | Summary format |
|:----------|:---------------|
| `session.start` | `Workflow: <workflow_name> -- started` |
| `session.end` | `Completed in <duration>s -- status: <status>` |
| `llm.request` | `LLM request: <model> -- <n> messages` |
| `llm.response` | `LLM: <model> -- <tokens> tokens -- <finish_reason>` |
| `tool.call` | `Tool call: <tool_name>(<args_summary>)` |
| `tool.response` | `Tool result: <tool_name> -- <status>` |
| `agent.decision` | `Decision: <decision_text>` |
| `agent.approval.request` | `Approval requested: <reason>` |
| `agent.approval.response` | `Approval: <outcome> by <approver>` |
| `agent.run.start` | `Agent run started: <agent_name>` |
| `agent.run.end` | `Agent run ended: <agent_name> -- <status>` |
| `application.intake` | `Intake: <application_id> -- <applicant_name>` |
| `credit.check` | `Credit check: score <score> -- <outcome>` |
| `policy.check` | `Policy: <rule_name> -- <result>` |
| `environment.captured` | `Environment: <platform> / Python <version>` |
| `source.record.loaded` | `Record loaded: <record_id>` |

Unknown step kinds fall back to showing the step kind and a brief JSON excerpt, not the full raw dump.

### 2.5 DID:WEB improvements

`epi_core/did_web.py` was rewritten to use Python's standard library `urllib.request` instead of the `requests` package. The `requests` package was not listed as a declared dependency. This caused `ImportError` on clean installs without `requests` installed.

Additional improvements:

- Added `generate_did_document()` helper function for teams that want to self-host a DID:WEB document to back their governance identity
- Added support for `publicKeyMultibase` format -- z-prefixed base58btc encoding
- Added support for `publicKeyJwk` format with `crv=Ed25519`

Both key formats are now correctly parsed when verifying an artifact's DID:WEB governance binding.

### 2.6 epi verify Forensic: PASS for normal recordings

In v4.0.2, `epi verify` showed `Forensic: FAIL` for perfectly normal recordings that did not contain guardrails steps.

Root cause: `completeness_ok` in `epi_cli/verify.py` required at least one guardrails step in every recording. That assumption was wrong -- guardrails steps only appear when the epi_guardrails integration is active.

Fix: the condition is now `len(iteration_steps) == 0 or all(...)`. An empty guardrails step list is treated as complete (no violations possible). Only non-empty guardrails step lists can trigger a forensic completeness failure.

Normal recordings without guardrails integration now show `Forensic: PASS` as expected.

### 2.7 VERIFY.txt contains the real signing key

In v4.0.2, `VERIFY.txt` was written to the artifact before signing. That meant it always showed `public_key: None`.

Fix: `VERIFY.txt` is now written after the signing step, so it correctly shows the actual Ed25519 public key used to sign the artifact.

`VERIFY.txt` is also excluded from `file_manifest` to prevent integrity check failures on re-open. The file is informational metadata, not sealed evidence content.

### 2.8 DID identity shown in epi verify trust report

When an artifact was recorded with a DID:WEB governance binding, `epi verify` now includes the DID in the trust report:

```text
DID: did:web:governance.example.com
```

Previously the trust report showed no identity information even when a DID was present in the manifest.

### 2.9 Signature display correct

In v4.0.2 the viewer hardcoded the signature state to `false` (unsigned) regardless of the actual artifact state.

Fix: the viewer now reads signature state from the case payload's signature verification result, which is computed server-side (or at load time) from the actual manifest signature field.

Artifacts signed with a valid Ed25519 key now show `SIGNED` in the viewer header.

### 2.10 Simulation framework

Added `simulation/run_simulation.py` with five realistic test scenarios:

- Loan happy path -- approval at all policy checkpoints
- Loan policy fault -- triggers a policy violation
- Medical triage -- multi-step clinical decision workflow
- Refund compliant -- policy-passing refund workflow
- Refund policy fault -- triggers a refund policy violation

All five scenarios pass end-to-end. The simulation framework is useful for:
- testing the viewer against realistic step data
- regression-testing the forensic logic without a live AI backend
- demonstrating the product to new users

---

## 3. The forensic document viewer explained

The v4.0.3 viewer is designed around a single mental model:

**A case file is read once, carefully, by a human who needs to understand what happened and decide whether to trust it.**

That is a different mental model from a live monitoring dashboard. A dashboard is for ongoing awareness. A case file is for retrospective investigation.

The design follows from that model:

### Monospace aesthetic

Monospace fonts signal: this is a technical document, read carefully. The viewer looks like a terminal/editor output, not a web app. That aesthetic is intentional. It reduces confusion about whether the viewer is interactive (it is, but only to expand details) vs. authoritative (it is, by design).

### Numbered sections

Every section has a stable number (section 0 through section 8). This means you can refer to "section 6, step 14" in a conversation, in a bug report, or in a compliance note. The section numbers are not cosmetic.

### Expandable step rows

The evidence timeline (section 6) shows one row per step. Each row shows:
- step index
- timestamp
- step kind
- human-readable summary (see section 2.4 above)

Clicking a row expands a terminal-style JSON block showing the full step content. Collapsing it returns to the summary. This means the timeline stays readable even for 200-step workflows, but the full detail is always one click away.

### Heatmap timeline bar

Above the step list, a horizontal bar shows step density across the execution timeline. Darker cells = more steps in that time window. This gives reviewers a quick visual sense of where the work happened -- useful for long-running workflows with bursty activity patterns.

### Fixed sidebar navigation

The sidebar lists all sections by number and title. It stays fixed as you scroll. Clicking a section jumps to it. This is essential for long artifacts where the viewer page is much taller than the screen.

### What the viewer answers

In 5 seconds:
- what workflow ran, when, and what was its stated goal
- whether the artifact is signed and forensically complete
- whether a human reviewer has already acted on it

In 30 seconds:
- what policy applied and whether it passed
- what the major decision points were (expandable summaries)

In 2 minutes:
- the full evidence trail, step by step
- the raw manifest for deep inspection
- any attached artifacts

---

## 4. DID:WEB identity binding

EPI supports optional DID:WEB governance identity binding. When a recording organization controls a web domain, they can self-host a DID document and reference it in their EPI artifacts. This lets downstream verifiers check the artifact's governance identity without a centralized registry.

### What DID:WEB provides

- a stable governance identity (`did:web:governance.example.com`) tied to a web domain you control
- a public key document at a well-known URL that verifiers can fetch
- a link between the Ed25519 signing key in the artifact and an organizational identity

### Self-hosting a DID document

```python
from epi_core.did_web import generate_did_document

# Generate a DID document for your governance domain
did_doc = generate_did_document(
    domain="governance.example.com",
    public_key_hex="<your_ed25519_public_key_hex>",
)

# Write to your web server at:
# https://governance.example.com/.well-known/did.json
import json
with open(".well-known/did.json", "w") as f:
    json.dump(did_doc, f, indent=2)
```

The generated document supports both key formats:
- `publicKeyMultibase`: z-prefixed base58btc (e.g. `z6Mk...`)
- `publicKeyJwk`: JWK with `crv=Ed25519`

### Attaching a DID to a recording

```python
import epi

with epi.record(
    "my-case.epi",
    workflow_name="Loan Approval v3",
    governance_did="did:web:governance.example.com",
) as session:
    session.log_step("session.start", {"workflow_name": "Loan Approval v3"})
    # ... workflow steps ...
```

### Verifying a DID-bound artifact

```bash
epi verify my-case.epi
```

Output now includes:

```text
Signature:  VALID
DID:        did:web:governance.example.com
Forensic:   PASS
Integrity:  OK
```

### How verification works

1. `epi verify` reads the `governance_did` field from `manifest.json`
2. It constructs the DID URL: `https://<domain>/.well-known/did.json`
3. It fetches the document using Python stdlib `urllib.request` (no external dependencies)
4. It extracts the verification method's public key (supporting both `publicKeyMultibase` and `publicKeyJwk`)
5. It checks whether the extracted key matches the artifact's signing key

If the DID document fetch fails (network unavailable, domain changed), verification still succeeds on the local key material and reports the DID lookup result separately.

---

## 5. Rich viewer output -- workflow_name, goal, notes, metrics

The v4.0.3 viewer surfaces four manifest fields that were previously invisible. Here is how to use them to produce informative case files.

### workflow_name

Set this when you call `epi.record()`. It becomes the case title in the viewer and the source name in the trust report.

```python
with epi.record("case.epi", workflow_name="Mortgage Approval Pipeline v2") as session:
    ...
```

Alternatively, the recorder picks it up from the `session.start` step's `workflow_name` field:

```python
session.log_step("session.start", {
    "workflow_name": "Mortgage Approval Pipeline v2",
    "start_time": "2026-05-03T10:00:00Z",
})
```

### goal

Describe what this workflow run was trying to accomplish:

```python
with epi.record(
    "case.epi",
    workflow_name="Mortgage Approval Pipeline v2",
    goal="Evaluate mortgage application #APP-20260503-001 for compliance and creditworthiness",
) as session:
    ...
```

Shown in section 2 (Case Context) of the viewer.

### notes

Freeform operator notes attached at record time:

```python
with epi.record(
    "case.epi",
    notes="Re-run after fixing credit bureau timeout issue. First attempt at 09:48 timed out.",
) as session:
    ...
```

Useful for recording context that is not part of the workflow itself -- why a run was retried, what environment it ran in, etc.

### metrics

Key/value pairs capturing outcome metrics:

```python
with epi.record(
    "case.epi",
    metrics={
        "credit_score": 742,
        "loan_amount_usd": 280000,
        "decision": "APPROVED",
        "processing_time_ms": 1420,
    },
) as session:
    ...
```

Shown as a structured table in section 2. Reviewers can scan these at a glance without reading the full step trail.

### approved_by

If a human approval step was captured, the approver identity can be promoted to the manifest level:

```python
with epi.record("case.epi", approved_by="j.smith@example.com") as session:
    ...
```

This makes the approver visible in the case header without requiring the reviewer to find the approval step in the timeline.

### Complete example

```python
import epi

with epi.record(
    "loan-approval-20260503.epi",
    workflow_name="Loan Approval Pipeline",
    goal="Evaluate personal loan application #LA-20260503-042",
    notes="Standard automated evaluation. Escalation threshold: score < 620.",
    metrics={"applicant_id": "C-00421", "loan_amount": 15000, "term_months": 36},
    governance_did="did:web:governance.acmefinance.com",
) as session:
    session.log_step("session.start", {
        "workflow_name": "Loan Approval Pipeline",
        "start_time": "2026-05-03T14:00:00Z",
    })
    session.log_step("application.intake", {
        "application_id": "LA-20260503-042",
        "applicant_name": "Jane Doe",
        "loan_amount": 15000,
    })
    session.log_step("credit.check", {
        "score": 720,
        "bureau": "Experian",
        "outcome": "PASS",
    })
    session.log_step("llm.request", {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Evaluate risk for applicant..."}],
    })
    # ... more steps ...
    session.log_step("agent.decision", {
        "decision": "APPROVED",
        "reason": "Credit score above threshold, income verified, no adverse history",
    })
    session.log_step("session.end", {
        "status": "completed",
        "duration_s": 1.42,
    })
```

The resulting artifact opens in the viewer showing:
- title: "Loan Approval Pipeline"
- section 2 with goal, notes, and metrics table
- section 6 with human-readable step summaries
- section 1 with SIGNED / Forensic: PASS trust report

---

## 6. Integrations roadmap

EPI's goal is to become the universal evidence layer for AI workflows across every major platform and framework. The `.epi` format is designed to be framework-agnostic -- any system that can log structured steps can produce a valid artifact.

The following integrations are planned. They fall into two categories: framework integrations (recording evidence from a running agent or LLM pipeline) and compliance integrations (formatting evidence for a specific regulatory standard).

---

### Guardrails AI

**Status:** Planned

Guardrails AI is a Python framework for defining and enforcing output validators (guards) on LLM responses. It runs validators in sequence and can block, fix, or escalate on validation failures.

Planned integration: a native `EPIGuardrailsTracer` that captures:
- the guard stack applied to each LLM call
- individual validator outcomes (pass/fail/fix) and their reasons
- the pre-guard and post-guard response content
- any reask or fix cycles
- the final guard decision

This produces a `policy.check` step for each validator, making the full guard execution trail inspectable inside the EPI viewer.

```python
from epi_recorder.integrations.guardrails import EPIGuardrailsTracer
import guardrails as gd

guard = gd.Guard.from_pydantic(output_class=MyOutputModel)
with epi.record("guarded-run.epi") as session:
    with EPIGuardrailsTracer(session):
        result = guard(llm_api=openai.chat.completions.create, ...)
```

---

### Microsoft Azure AI and Semantic Kernel

**Status:** Planned

Azure OpenAI Service is one of the most common enterprise LLM backends. Semantic Kernel is Microsoft's orchestration framework for building AI agents on top of Azure.

Planned integrations:

- `EPIAzureOpenAIWrapper` -- wraps `AzureOpenAI` client calls, recording each request and response as `llm.request` / `llm.response` steps with Azure-specific metadata (deployment name, API version, resource endpoint)
- `EPISemanticKernelPlugin` -- a Semantic Kernel `KernelPlugin` that instruments kernel invocations, function calls, planner decisions, and memory operations
- DID:WEB binding support for Azure Active Directory-backed governance identities

```python
from epi_recorder.integrations.azure import EPIAzureOpenAIWrapper
from openai import AzureOpenAI

client = EPIAzureOpenAIWrapper(
    AzureOpenAI(
        azure_endpoint="https://myorg.openai.azure.com",
        api_version="2024-02-01",
    ),
    session=session,
)
```

---

### AutoGen and AG2

**Status:** Planned

AutoGen (now AG2) is a Microsoft Research framework for multi-agent conversation and collaboration. Agents exchange messages, delegate tasks, and produce collaborative outputs.

Planned integration: an `EPIAutoGenTracer` that captures:
- each agent's message send/receive as `agent.run.start` / `agent.decision` steps
- tool calls made by code-executing agents
- the conversation graph (who delegated to whom)
- termination conditions and final outputs

Multi-agent evidence is particularly valuable for compliance because you need to attribute decisions to specific agents in the conversation chain.

```python
from epi_recorder.integrations.autogen import EPIAutoGenTracer

with epi.record("multi-agent-run.epi") as session:
    tracer = EPIAutoGenTracer(session)
    user_proxy = autogen.UserProxyAgent("user", ...)
    assistant = autogen.AssistantAgent("assistant", ..., code_execution_config={...})
    tracer.attach(user_proxy, assistant)
    user_proxy.initiate_chat(assistant, message="Analyze this dataset...")
```

---

### CrewAI

**Status:** Planned

CrewAI is a framework for building role-based multi-agent teams where each agent has a defined role, goal, and backstory. Crews execute tasks collaboratively.

Planned integration: an `EPICrewCallback` that captures:
- crew and agent initialization (roles, goals, tools)
- task assignment and execution
- inter-agent delegation
- final crew output

```python
from epi_recorder.integrations.crewai import EPICrewCallback
from crewai import Crew, Agent, Task

with epi.record("crew-run.epi") as session:
    callback = EPICrewCallback(session)
    crew = Crew(
        agents=[analyst, writer],
        tasks=[analysis_task, report_task],
        callbacks=[callback],
    )
    result = crew.kickoff()
```

---

### AWS Bedrock Agents

**Status:** Planned

Amazon Bedrock Agents is AWS's managed service for building AI agents backed by foundation models available on Bedrock. Bedrock agents support action groups, knowledge bases, and multi-agent collaboration.

Planned integration: an `EPIBedrockAgentsRecorder` that captures:
- `InvokeAgent` API calls and their trace events
- action group invocations and Lambda results
- knowledge base retrieval results
- orchestration trace showing the agent's reasoning chain
- final response and attribution

AWS Bedrock provides detailed trace data in the `InvokeAgentResponse`. The integration would parse these traces into EPI steps.

```python
from epi_recorder.integrations.aws_bedrock import EPIBedrockAgentsRecorder
import boto3

bedrock_client = boto3.client("bedrock-agent-runtime")
with epi.record("bedrock-run.epi") as session:
    recorder = EPIBedrockAgentsRecorder(session, bedrock_client)
    response = recorder.invoke_agent(
        agentId="ABCDEF1234",
        agentAliasId="TSTALIASID",
        sessionId="my-session",
        inputText="Process this insurance claim...",
    )
```

---

### Google Vertex AI Agents

**Status:** Planned

Google Vertex AI provides managed agent infrastructure including Agent Builder, Dialogflow CX, and Gemini-backed agents. Vertex AI also supports grounding, tool use, and multi-turn conversations.

Planned integration: an `EPIVertexAgentRecorder` that captures:
- `generate_content` calls with tool use and function calling
- grounding metadata (search results, citations)
- multi-turn conversation turns
- agent builder flow execution traces

```python
from epi_recorder.integrations.vertex import EPIVertexAgentRecorder
import vertexai
from vertexai.generative_models import GenerativeModel

with epi.record("vertex-run.epi") as session:
    recorder = EPIVertexAgentRecorder(session)
    model = recorder.wrap(GenerativeModel("gemini-1.5-pro"))
    response = model.generate_content("Assess this clinical note for risk factors...")
```

---

### LangSmith and LangGraph (deep integration)

**Status:** Planned (extending current basic tracing)

LangChain already has basic EPI tracing via `EPICallbackHandler`. The planned deeper integration covers:

**LangSmith:**
- bidirectional sync: export LangSmith traces as `.epi` artifacts
- import LangSmith run data into existing EPI cases
- use LangSmith run IDs as external references in EPI manifests

**LangGraph:**
- first-class graph node step recording (each node = one `agent.run.start` / `agent.run.end` pair)
- edge traversal tracing (which conditional edges fired and why)
- state snapshot at each checkpoint
- interrupt and resume event capture for human-in-the-loop graphs

```python
from epi_recorder.integrations.langgraph import EPILangGraphTracer
from langgraph.graph import StateGraph

with epi.record("langgraph-run.epi") as session:
    tracer = EPILangGraphTracer(session)
    graph = StateGraph(MyState)
    # ... add nodes and edges ...
    compiled = graph.compile(checkpointer=tracer.checkpointer)
    result = compiled.invoke({"input": "..."}, config={"callbacks": [tracer]})
```

---

### Pydantic AI

**Status:** Planned

Pydantic AI is a Python agent framework built around Pydantic's type system. Agents are defined with typed inputs and outputs, and the framework handles structured output validation natively.

Planned integration: an `EPIPydanticAIAgent` wrapper that captures:
- agent invocation with typed input
- tool calls and their typed results
- structured output validation
- retry attempts on validation failure

```python
from epi_recorder.integrations.pydantic_ai import EPIPydanticAITracer
from pydantic_ai import Agent

with epi.record("pydantic-ai-run.epi") as session:
    tracer = EPIPydanticAITracer(session)
    agent = Agent("openai:gpt-4o", result_type=MyOutputModel)
    result = await agent.run("Classify this document...", tracer=tracer)
```

---

### smolagents (HuggingFace)

**Status:** Planned

smolagents is HuggingFace's lightweight agent framework. Agents use Python code execution as the primary tool and can run local or remote LLMs.

Planned integration: an `EPIsmolagentsCallback` that captures:
- agent step loop iterations
- code generation and execution steps
- tool call results
- final answer and its derivation path

```python
from epi_recorder.integrations.smolagents import EPIsmolagentsCallback
from smolagents import CodeAgent, HfApiModel

with epi.record("smolagents-run.epi") as session:
    callback = EPIsmolagentsCallback(session)
    agent = CodeAgent(
        tools=[...],
        model=HfApiModel(),
        additional_authorized_imports=["pandas"],
        callbacks=[callback],
    )
    result = agent.run("Analyze the attached dataset and summarize key trends.")
```

---

### Compliance standards

#### EU AI Act -- Article 13 transparency logging

Article 13 of the EU AI Act requires that high-risk AI systems be transparent and that users can interpret their outputs. Article 12 requires automatic logging sufficient to identify risks post-deployment.

EPI's `.epi` format directly addresses these requirements:
- `steps.jsonl` provides automatic logging of all AI system interactions
- `manifest.json` with Ed25519 signatures provides tamper-evident integrity
- `policy.json` and `policy_evaluation.json` document which controls applied
- `review.json` captures human oversight events
- the embedded viewer enables human interpretation of AI outputs

Planned work: an `EU_AI_Act_ArticleMapping` export that generates a structured report mapping `.epi` artifact contents to specific Article 13 and Article 12 obligations. This report can accompany the `.epi` file in regulatory submissions.

See also: [`docs/EU-AI-ACT-EVIDENCE-PREP.md`](EU-AI-ACT-EVIDENCE-PREP.md).

#### NIST AI RMF -- evidence packaging

The NIST AI Risk Management Framework (AI RMF 1.0) organizes AI governance around four functions: GOVERN, MAP, MEASURE, MANAGE. Each `.epi` artifact is a unit of MEASURE evidence.

Planned work: an `NIST_RMF_ExportProfile` that:
- tags each step with its AI RMF function and subcategory
- generates a `nist_rmf_evidence_index.json` mapping artifact contents to AI RMF subcategories
- packages the index alongside the `.epi` artifact for use in AI RMF conformance documentation

---

## 7. Quick reference -- CLI commands

All commands use the `epi` entrypoint installed by `pip install epi-recorder`.

### Recording

```bash
# Run a Python script and record its execution
epi run my_workflow.py

# Start a new recording session interactively
epi init

# Run the built-in demo to see EPI in action
epi demo
```

### Viewing

```bash
# Open the forensic document viewer in the browser
epi view my-case.epi

# Extract viewer and artifact to a directory
epi view --extract my-case.epi

# Refresh the embedded viewer in an existing artifact
epi refresh-viewer my-case.epi
```

### Verifying

```bash
# Full forensic trust report
epi verify my-case.epi

# Verbose output with step-level detail
epi verify --verbose my-case.epi
```

### Import and export

```bash
# Import AGT evidence bundle
epi import agt examples/agt/sample_bundle.json --out sample.epi

# Export an AGT-compatible bundle from an EPI artifact
epi export agt my-case.epi --out agt-bundle.json

# Export a human-readable summary
epi export-summary my-case.epi
```

### Review and policy

```bash
# Open review UI for an artifact
epi review my-case.epi

# Validate a policy file
epi policy validate my-policy.json

# Show the policy embedded in an artifact
epi policy show my-case.epi
```

### Identity and trust

```bash
# Show or generate your Ed25519 signing identity
epi identity show
epi identity generate

# Associate .epi file extension with the viewer (OS-level)
epi associate
epi unassociate
```

### Infrastructure

```bash
# Migrate legacy ZIP-format artifact to EPI1 envelope
epi migrate my-case.epi

# Start local review gateway
epi connect open

# Check installation health
epi doctor

# Telemetry opt-in management
epi telemetry status
epi telemetry enable
epi telemetry disable
```

### Integrations

```bash
# Generate integration example code
epi integrate langchain
epi integrate litellm
epi integrate opentelemetry
epi integrate pytest
epi integrate agt
```

See [`docs/CLI.md`](CLI.md) for the full command reference.

---

## 8. Related docs

- [AGT Import Quickstart](AGT-IMPORT-QUICKSTART.md)
- [CLI Reference](CLI.md)
- [Policy Guide](POLICY.md)
- [Self-Hosted Runbook](SELF-HOSTED-RUNBOOK.md)
- [EPI Specification](EPI-SPEC.md)
- [EPI Codebase Walkthrough](EPI-CODEBASE-WALKTHROUGH.md)
- [EU AI Act Evidence Prep](EU-AI-ACT-EVIDENCE-PREP.md)
- [Framework Integrations in 5 Minutes](FRAMEWORK-INTEGRATIONS-5-MINUTES.md)
- [Changelog](../CHANGELOG.md)

---

## 9. Final plain-language summary

EPI is infrastructure for portable AI case files.

`v4.0.3` strengthens that infrastructure in the places that matter most to reviewers and auditors:

- the viewer now reads like a forensic document, not a dashboard
- workflow names and case context are correctly surfaced
- trust reporting is accurate -- no more false `Forensic: FAIL` on normal runs
- the signing key is now visible in `VERIFY.txt`
- DID:WEB governance identity is shown in verify output
- the simulation framework makes the full system testable end-to-end

The artifact format is unchanged. Existing artifacts remain valid. The CLI interface is unchanged.

The right description of the current product:

**portable AI case files with built-in trust, forensic review, and governance identity**
