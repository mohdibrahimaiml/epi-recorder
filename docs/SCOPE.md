# Scope

## The rule

**No new surface until three external companies use the core.** A surface is
a package, a hosted endpoint, an export format, or a docs site. Fixes to
existing surfaces are always allowed; new ones need three external users of
the core first.

## Core (invest here)

- `epi_recorder` — SDK and integrations (OpenAI, Anthropic, LangChain,
  LangGraph, LiteLLM, OpenAI Agents SDK, OpenTelemetry)
- `epi_core`
- `epi_cli` — record, verify, view, keys, policy, witness
- `epi_gateway` — capture, proxy, cases, review, export
- `web_viewer` and `epi_viewer_static`
- `pytest_epi`
- `website/` (static, Cloudflare Pages free tier)

Core is covered by the release gate (`pytest -m "not browser and not
experimental"`); nothing core depends on paid hosting or the Render free
tier at runtime.

## Experimental (frozen)

Works as documented; bug fixes allowed; no new features until a paying user
asks. Not on the critical path. Covered by a separate non-blocking CI job
(`pytest -m experimental`).

- `epi_mcp` (ChatGPT/Claude connector)
- `verify_portal` (hosted portal, auth, Paddle billing, tier gating)
- TRACE export (`epi_recorder/integrations/trace_exporter.py`)
- Microsoft AGT import/export (`epi_recorder/integrations/agt*`)
- `epi_guardrails`
- `website-v2/`
- remote SCITT service
