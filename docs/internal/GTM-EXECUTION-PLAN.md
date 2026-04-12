# EPI Go-To-Market Execution Plan

This file tracks the go-to-market layer on top of the already shipped `epi-recorder` product. The product center remains:

Tool: https://github.com/mohdibrahimaiml/epi-recorder

Spec: https://github.com/mohdibrahimaiml/epi-spec

## Immediate Action: v4.0.1, April 12-18 2026

- Ship privacy-first opt-in telemetry:
  - `epi telemetry status`
  - `epi telemetry enable`
  - `epi telemetry disable`
  - `epi telemetry test`
- Keep defaults strict:
  - default off
  - no import tracking
  - no install ID before opt-in
  - no prompts, outputs, paths, repos, hostnames, usernames, keys, artifact content, or customer data
- Add reachable pilot signup after `epi telemetry enable`:
  - email
  - org
  - role/use case
  - consent to contact
  - optional consent to link telemetry to pilot profile
- Add gateway telemetry endpoints behind `EPI_GATEWAY_TELEMETRY_ENABLED=true`:
  - `POST /api/telemetry/events`
  - `POST /api/telemetry/pilot-signups`
- Improve onboarding:
  - `epi init --github-action --force`
  - `epi integrate <target>` for `pytest`, `langchain`, `litellm`, `opentelemetry`, and `agt`
- Release only after targeted tests and the full release gate pass.

## Hard Metrics For AGT Outreach

By May 23, send the Imran update if any trigger is true:

- 1,000+ GitHub Action runs
- 500+ active opt-in telemetry installs
- 100+ pilot signups total
- 25+ pilot signups with `agt integration`, `governance`, or `compliance` use case
- 3+ public GitHub issues or discussions asking about AGT compatibility

If none are true by May 23:

- delay AGT outreach to June 15
- publish more framework guides
- push GitHub Action distribution first

## Adoption Scenarios On May 23

High adoption:

- 100%+ of target
- send AGT update May 24-30
- prepare the 30-minute technical alignment call

Medium adoption:

- 50-75% of target
- extend collection to June 6
- prioritize framework PRs and community examples
- delay AGT outreach to June 10

Low adoption:

- under 50% of target
- pause AGT outreach until July
- pivot to community distribution, CI/CD, and direct pilot conversations

## Framework Distribution Plan

Week 2, April 19-25:

- publish the `v4.0.1` announcement
- publish a `pytest --epi` CI workflow guide

Week 3, April 26-May 2:

- open pytest/docs promotion issue or PR where appropriate

Week 4, May 3-9:

- open LangChain docs/example PR for `EPICallbackHandler`
- if rejected, publish `EPI + LangChain Best Practices` in `epi-recorder` and distribute in LangChain community channels

Week 5, May 10-16:

- open CrewAI template/example PR
- if rejected, publish a standalone community example under `epi-recorder/examples/` and link it from README/docs

Week 6, May 17-23:

- open AutoGen example PR using EPI logging or the OpenTelemetry bridge
- if rejected or stale, publish the example in `epi-recorder` and use it in outreach

If 2+ framework PRs fail or stall by May 30:

- pivot to `epi integrate` and GitHub Action distribution as the primary lever
- create a dedicated `epi-action` repo for Marketplace only if ready
- make that repo README funnel first to `epi-recorder`

## Dashboard Monetization Definition

Pilot waitlist starts in `v4.0.1`.

Free dashboard beta target: May 24-June 6.

- upload/view `.epi` artifacts
- verify integrity
- show project summary: total artifacts, date range, pass/fail rate
- export summary as JSON and PDF

Paid team beta target: June 7-June 20.

- price target: `$299/mo` for up to 5 users
- team access and roles
- audit history: who viewed/reviewed what and when
- search by artifact metadata
- compliance report export
- webhooks
- 24-hour support response target

Enterprise:

- custom pricing target: `$3K-$10K/mo`
- custom integrations
- on-prem/self-hosted deployment
- SLA
- reporting formats
- volume support

## AGT Outreach Draft

Subject: `EPI Adoption Update + AGT Integration Path`

```text
Hi Imran,

Quick update on the .epi RFC path.

Since then, we shipped:
- EPI Recorder v4.0.1 with privacy-first opt-in telemetry
- Pilot signup for teams that want dashboard/support access
- GitHub Action and framework integration workflows

Real adoption metrics as of [DATE]:
- [ACTUAL GitHub Action runs]
- [ACTUAL opt-in telemetry installs]
- [ACTUAL pilot signups]
- [ACTUAL AGT/governance/compliance signups]
- [ACTUAL public AGT compatibility asks]

The pattern I am seeing:
[INSERT REAL PATTERN ONLY]

Rather than more async RFC back-and-forth, a 30-minute technical call would clarify:
- Integration surface: AGT evidence -> .epi export
- Timeline fit with your roadmap
- Maintenance ownership: EPI owns the artifact format, AGT owns its exporter layer

Available:
- [TIME SLOT 1]
- [TIME SLOT 2]
- [TIME SLOT 3]

Best,
Afridi
```

## If AGT Says No

Default Plan B:

- keep AGT import EPI-side
- publish `How to export AGT evidence as .epi`
- position EPI as external portable evidence packaging for AGT users without claiming native AGT support

Secondary Plan B:

- shift partnership energy to framework and CI/CD distribution
- strengthen `epi integrate agt` and AGT import docs

Tertiary Plan B:

- go deep on regulated verticals: insurance, healthcare, finance
- sell EPI as compliance evidence infrastructure independent of AGT

## EU AI Act Evidence-Prep Guide

Public guide: [Using .epi Artifacts For AI Evidence Preparation](../EU-AI-ACT-EVIDENCE-PREP.md)

Use legal-safe language:

- EPI supports evidence workflows
- EPI does not guarantee compliance
- EPI is not regulator approval
- EPI is not legal advice
- organizations remain responsible for governance, retention, and legal review
