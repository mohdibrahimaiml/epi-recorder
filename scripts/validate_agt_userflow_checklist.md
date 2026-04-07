# Manual AGT -> EPI Review Checklist

Use this after the scripted validation finishes and you have a generated `.epi` artifact.

## Browser / Viewer

- Run `epi view <case>.epi`.
- Confirm the browser opens, or that EPI clearly tells you what to run next if auto-open is blocked.
- Confirm the main timeline is readable without knowing EPI internals.

## Decision Clarity

- Confirm the key steps tell a coherent story from AGT evidence to final outcome.
- Confirm a failure case makes the policy issue obvious.
- Confirm a clean case makes the no-fault state obvious.

## Trust Clarity

- Run `epi verify <case>.epi` and confirm the integrity and signature story is understandable.
- Inspect `artifacts/agt/mapping_report.json` inside the `.epi` and confirm it is easy to find.
- Confirm the mapping report explains input counts, output counts, dedupe behavior, unknown events, and whether analysis was synthesized.

## Maintainer Question

- Ask: "If I were seeing this as a Microsoft AGT maintainer for the first time, would I understand what was imported, what was preserved, and what was transformed?"
