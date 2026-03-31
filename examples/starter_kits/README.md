# EPI Starter Kits

Starter kits are the fastest path to making EPI easy for high-risk AI teams.

The goal is simple: a team should be able to pick a workflow, run one setup path, and get a realistic case-file flow without inventing policy, review, trust, and export behavior from scratch.

## What belongs here

Each starter kit should be a production-shaped example for one consequential workflow, not a toy demo.

Initial target kits:

- refunds
- insurance claim denial
- underwriting
- support escalation

## Required contents for each kit

- `README.md` with the buyer problem, workflow story, and setup steps
- `workflow.py` or app entrypoint
- `epi_policy.json` with a realistic control baseline
- one signed sample artifact
- one reviewed sample artifact
- one tampered sample artifact
- reviewer walkthrough
- deployment notes
- expected `epi verify` output

## Quality bar

A good starter kit should let a new user understand:

- what business decision is being made
- which control framework applies
- where human approval fits
- how trust is verified
- how the case file would be used in audit or incident review

## Relationship to `epi init`

The long-term plan is for `epi init` to scaffold from these kits by industry, workflow type, framework, jurisdiction, and deployment mode.

This directory is the source material for that first-run experience.
