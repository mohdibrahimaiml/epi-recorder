# Share One Failure With `.epi`

Use `.epi` as the bug-report artifact for AI systems: one file another engineer can open, verify, and inspect without reconstructing your environment first.

## Inspect before you share

`.epi` files can contain prompts, tool inputs, tool outputs, model responses, approval decisions, and review notes. Open the file yourself before attaching it outside your team, and remove or redact anything you would not paste into an issue or chat thread.

## What a `.epi` file actually contains

A typical `.epi` case file includes:

- `steps.jsonl`: the ordered step timeline
- tool calls and results when your run emitted them
- decisions, approvals, and fault-analysis output when present
- trust state from `manifest.json` and signature metadata
- `review.json` when a human later adds review notes
- a browser review view so the run is inspectable without custom tooling

Depending on how the run was captured, the file may also contain `policy.json`, `analysis.json`, or provider-specific metadata.

## Fast path

Use the sample flow:

```bash
epi demo
epi view refund_case.epi
epi verify refund_case.epi
```

Or capture your own run:

```bash
epi run my_agent.py
epi view my_agent.epi
epi verify my_agent.epi
```

## The engineer handoff loop

This is the pattern you want teammates to repeat:

```text
capture one run -> inspect it in the browser -> verify integrity -> attach the .epi file
```

In practice:

1. Capture one run with `epi demo`, `epi run`, `pytest --epi`, or a framework wrapper.
2. Open the result with `epi view <file.epi>`.
3. Verify trust with `epi verify <file.epi>`.
4. Attach the same `.epi` file to a GitHub issue, PR discussion, Slack thread, or incident doc.

The goal is not "share all logs." The goal is "share one portable repro that preserves the exact run."

## Copy-paste issue / PR template

```text
Title: Agent regression: refund approval skipped manager review

Expected:
- Refunds above $500 should pause for manager approval.

Actual:
- The run completed and approved the refund without the approval step.

Command / test:
- pytest --epi --epi-dir=evidence tests/test_refund_flow.py -k high_value_refund

Artifact:
- Attached: evidence/test_refund_flow.py__test_high_value_refund.epi

Verification:
- epi verify evidence/test_refund_flow.py__test_high_value_refund.epi
- Integrity: OK
- Signature: Valid

Notes:
- This started after the tool-routing refactor on branch feature/tool-router-v2.
```

That template is enough for another engineer to open the artifact, verify trust, and start debugging immediately.

## What the receiver can do

If the receiver has EPI installed:

```bash
pip install epi-recorder
epi view attached_case.epi
epi verify attached_case.epi
```

If the receiver does not have EPI installed:

- send the `.epi` file plus [epilabs.org/verify](https://epilabs.org/verify)
- they can drag and drop the file into the browser verifier
- this is enough to check integrity, signature state, and basic artifact contents

If they need the richer local review flow, they should install EPI and use `epi view`.

## When browser verify is enough

Use [epilabs.org/verify](https://epilabs.org/verify) when the receiver mainly needs to:

- confirm the file is intact
- confirm whether it is signed, unsigned, or tampered
- inspect the basic structure without setting up a local workspace

Use `epi view` when the receiver needs to:

- inspect the full browser review flow locally
- work with appended review notes
- compare steps, rules, and timeline details in the canonical review UI
- keep the whole review loop offline

Use `epi connect open` when you want a local team review workspace instead of handing around files one by one.

## Where `.epi` helps most

`.epi` is especially useful for:

- weird multi-step agent behavior
- regressions that only show up after several tool calls
- flaky CI failures where logs alone are not enough
- "works on my machine" debugging between teammates
- postmortems where you need the exact captured run later

## Suggested sharing pattern

For a GitHub issue or PR:

1. paste the short template above
2. attach the `.epi` file
3. include the output of `epi verify` if trust matters to the discussion

For Slack or incident docs:

1. summarize the symptom in one sentence
2. attach the `.epi`
3. add "open with `epi view`" or "verify at `epilabs.org/verify`"

That is usually enough to turn "I think the agent did something strange" into a reproducible debugging thread.

## Related guides

- [Use `pytest --epi` for agent regressions](PYTEST-AGENT-REGRESSIONS.md)
- [Framework integrations in 5 minutes](FRAMEWORK-INTEGRATIONS-5-MINUTES.md)
- [Share with your team locally](CONNECT.md)
