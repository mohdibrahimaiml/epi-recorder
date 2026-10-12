# Framework Integrations in 5 Minutes

Pick the integration that already matches your stack. The goal is to get one good `.epi` artifact quickly, not redesign your whole system.

Install only the extras you need, for example `pip install "epi-recorder[litellm]"`, `pip install "epi-recorder[langchain]"`, or `pip install "epi-recorder[opentelemetry]"`.

## Fast comparison

| Integration | Best when | What it captures |
| --- | --- | --- |
| OpenAI wrapper | You already call the OpenAI SDK directly | request/response steps, model metadata, usage, surrounding workflow steps inside `record()` |
| Anthropic wrapper | You use Claude via the Anthropic SDK | messages request/response steps, model metadata, usage, surrounding workflow steps inside `record()` |
| LiteLLM callback | You fan out across many providers through LiteLLM | provider-normalized completion calls across your LiteLLM entrypoints |
| LangChain callback | You already use chains, tools, or agents in LangChain | chain/tool/agent callbacks plus whatever your app logs around them |
| LangGraph checkpoint saver | You want stateful agent graphs and replayable checkpoints | graph checkpoint save/load events and graph state transitions |
| OpenTelemetry exporter | You already have tracing and want portable signed repros | spans grouped into `.epi` artifacts per trace |
| pytest plugin | You want repro artifacts from tests with almost no app changes | per-test metadata, test result, and any captured LLM/tool calls inside that test |

## OpenAI wrapper

```python
from openai import OpenAI
from epi_recorder import record, wrap_openai

client = wrap_openai(OpenAI())

with record("openai-run.epi", goal="Debug one agent run"):
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Debug this workflow"}],
    )
```

Use this when you want the shortest path from "existing SDK call" to "portable repro artifact."

## Anthropic wrapper

```python
from anthropic import Anthropic
from epi_recorder import record, wrap_anthropic

client = wrap_anthropic(Anthropic())

with record("anthropic-run.epi", goal="Inspect one Claude exchange"):
    client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=256,
        messages=[{"role": "user", "content": "Summarize the failing trace"}],
    )
```

Use this when Claude is already in your stack and you want the same capture flow as `wrap_openai()`.

## LiteLLM

```python
import litellm
from epi_recorder import record
from epi_recorder.integrations.litellm import enable_epi

enable_epi()

with record("litellm-run.epi", goal="Capture one LiteLLM exchange"):
    response = litellm.completion(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Explain the regression"}],
    )
```

Use this when your app already routes multiple providers through LiteLLM.

## LangChain

```python
from langchain_openai import ChatOpenAI
from epi_recorder import record
from epi_recorder.adapters.langchain import EpiCallbackHandler

with record("run.epi", goal="Capture one LangChain call") as session:
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        callbacks=[EpiCallbackHandler(session)],
    )
    result = llm.invoke("Analyze this tool trace")
```

The handler must be given the active `session` and used inside `with record(...)`.
That is what writes the file. Here `record("run.epi")` writes `epi-recordings/run.epi`.

The old `from epi_recorder.integrations import EPICallbackHandler` with
`callbacks=[EPICallbackHandler()]` is deprecated. Used outside `record()`, it
writes no `.epi` file at all.

Checked without an API key by swapping `ChatOpenAI` for LangChain's
`FakeListChatModel` (`pip install langchain-core`):

```text
$ python lc.py
Looks fine.

[EPI] 3 steps → epi-recordings/run.epi  Signed ✓
      1x llm · 1x print · 1x custom
```

For agents and chains, pass the handler per call instead:
`agent_executor.invoke({"input": "..."}, config={"callbacks": [EpiCallbackHandler(session)]})`.

Use this when you want chain, retriever, tool, and agent callback events in the same artifact.

## LangGraph

```python
from epi_recorder.integrations.langgraph import record_langgraph


async def run_graph(graph, input_data):
    async with record_langgraph("langgraph-run.epi", goal="Capture one graph run") as checkpointer:
        return await graph.ainvoke(
            input_data,
            config={"configurable": {"thread_id": "thread-1"}},
            checkpointer=checkpointer,
        )
```

Use this when graph state and checkpoint history matter as much as the final answer.

## OpenTelemetry

```python
from opentelemetry import trace
from epi_recorder.integrations.opentelemetry import setup_epi_tracing

exporter = setup_epi_tracing(
    output_dir="./epi-recordings",
    service_name="support-agent",
)

tracer = trace.get_tracer("support-agent")
with tracer.start_as_current_span("refund-decision"):
    pass

exporter.shutdown()
```

Use this when you already have tracing instrumentation and want portable, signed repro artifacts in addition to traces.

## HTTP / no-code connectors

Start the gateway (it seals exports with your key, so run `epi keys generate` once first):

```bash
epi keys generate
epi gateway serve --host 127.0.0.1 --port 8787
```

Send each tool call **and** its result. Every event with the same `traceId`
lands in the same case; `payload.call_id` pairs a `tool.call` with its
`tool.response`:

```http
POST /capture
Content-Type: application/json

{
  "eventType": "tool.call",
  "traceId": "trace-123",
  "workflowName": "Refund approvals",
  "sourceApp": "n8n",
  "payload": {
    "tool": "lookup_order",
    "call_id": "call-1",
    "input": {"order_id": "123"}
  }
}
```

```http
POST /capture
Content-Type: application/json

{
  "eventType": "tool.response",
  "traceId": "trace-123",
  "workflowName": "Refund approvals",
  "sourceApp": "n8n",
  "payload": {
    "tool": "lookup_order",
    "call_id": "call-1",
    "output": {"status": "shipped"}
  }
}
```

Export the case (its id is `trace::<traceId>`) and verify it:

```bash
epi gateway export --case-id "trace::trace-123" --out refund.epi
epi verify refund.epi
```

`Forensic: PASS` confirms every call has its response. A `tool.call` sent
without a matching `tool.response` seals fine but verifies as
`Forensic: FAIL — tool.call at step 2 is missing a corresponding tool.response`,
which is a WARN under the default policy and a FAIL under `--policy strict`.

Use this for n8n, Flowise, Langflow, Dify, or any adapter that can send JSON to the EPI gateway. The gateway also accepts `kind` / `content` if you prefer the native schema, and `/capture/batch` accepts either `items` or `events`.

## pytest

```bash
pytest --epi
pytest --epi --epi-dir=evidence
pytest --epi --epi-on-pass
```

Use this when you want artifacts from failing tests with almost no application code changes. Files go to `./test-evidence/` by default, one per failing test (`--epi-on-pass` keeps passing tests too); a re-run replaces the file for the same test.

## After capture

No matter which integration you choose, the next commands are the same:

```bash
epi view my_agent.epi
epi verify my_agent.epi
```

That is the core loop:

```text
capture -> open -> verify -> share
```

## I already use tracing. Do I still need EPI?

Usually yes, if you want something portable to attach to a bug report or PR.

Tracing and EPI solve different problems:

- tracing is great for live observability and cross-service debugging
- EPI is for portable, signed, shareable run artifacts

If you already use OpenTelemetry, EPI works well as the handoff layer:

- traces help you find the bad run
- `.epi` helps you package that run and hand it to another engineer

## Suggested starting points

- already on OpenAI or Anthropic SDKs: start with wrappers
- already on LiteLLM: start with `EPICallback`
- already on LangChain or LangGraph: use the native integration first
- already invested in tracing: layer EPI on top with OpenTelemetry
- debugging a failing workflow today: start with `pytest --epi`

## Related guides

- [Share one failure with `.epi`](SHARE-A-FAILURE.md)
- [Use `pytest --epi` for agent regressions](PYTEST-AGENT-REGRESSIONS.md)
- [Share with your team locally](CONNECT.md)
