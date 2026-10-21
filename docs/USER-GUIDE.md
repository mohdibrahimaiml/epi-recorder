# How to use EPI (normal path)

**Version:** 4.6.2  
You do not need an account, a dashboard, or EPI Cloud to record or verify.

This is the everyday guide. Bank / auditor briefing: [EPI_MASTER_DOCUMENTATION.md](./EPI_MASTER_DOCUMENTATION.md). Command list: [CLI.md](./CLI.md).

---

## What it does

EPI records what an AI agent did on one run, seals that record into a **`.epi` file**, and lets anyone else check that file later **offline**.

The file is the product. Not a login. Not a log you have to trust on our servers.

A sealed `.epi` answers: *these bytes were not changed after sealing, and they were signed by this public key.*  
It does **not** answer: *every call was captured*, or *the decision was correct*, or *you are compliant*.

---

## Where you use it

Use it on a **consequential agent path** — a workflow someone may ask you to prove six months later.

Typical places:

| You run an agent that… | What you hand over |
|------------------------|--------------------|
| Approves a loan, refund, or transfer | The sealed run behind that decision |
| Adjudicates a claim | The sealed run the reviewer opens |
| Screens a candidate or a transaction | The sealed run, with secrets redacted |
| Assists a clinician or a caseworker | The sealed run for later reconstruction |
| Sits in a vendor → bank / insurer deal | A file (or a Cloud trust link) the customer verifies themselves |

You wrap the code that already runs the agent. You do not replace the agent.

Skip EPI for throwaway chat UIs with no later audit question.

---

## Who does what

| Person | Job |
|--------|-----|
| **You (vendor / developer)** | Install, record one workflow, keep the `.epi` file. Optionally share it. |
| **Reviewer (customer, auditor, risk)** | Opens the file with `epi view` or `epi verify`. Pins **your** public key if identity matters. No EPI account. |
| **EPI Cloud (optional)** | Lets you send a browser link instead of emailing the file. Private beta. Verification stays free either way. |

---

## 1. Install

Python 3.11+. Use a virtual environment so EPI is not mixed with other tools.

```bash
python -m venv epienv
# Windows:
epienv\Scripts\activate
# macOS / Linux:
# source epienv/bin/activate

pip install epi-recorder
epi --version
```

If Windows says `epi` is not on PATH, stay in the same activated window, or run `python -m epi_cli`.

---

## 2. First run (no API key)

```bash
epi demo --no-browser
epi verify epi-recordings/demo_refund.epi
epi view epi-recordings/demo_refund.epi
```

That records a sample refund workflow, seals `epi-recordings/demo_refund.epi`, checks it, and opens the offline viewer.

First-run **LOCAL / NOT_PINNED** identity is normal. Integrity and signature can still be valid. Identity is a separate check (the receiver pins your key).

---

## 3. Record your own agent

**A. Log steps yourself** (no LLM required):

```python
from epi_recorder import record, get_current_session

with record("demo.epi", goal="show the golden path"):
    s = get_current_session()
    s.log("tool.call", tool="lookup", id="A-1")
    s.log("tool.response", ok=True, balance=250)
    s.log("decision", action="approve", reason="within limit")
```

A bare name such as `"demo.epi"` is written to `./epi-recordings/demo.epi`. A path with a folder (`out/run.epi`) is written exactly there. Re-running does not overwrite: you get `demo-2.epi`, then `demo-3.epi`, unless you set `EPI_OVERWRITE=1`.

**B. Wrap an existing OpenAI client:**

```python
from openai import OpenAI
from epi_recorder import record, wrap_openai

client = wrap_openai(OpenAI())  # needs OPENAI_API_KEY

with record("agent.epi", goal="Answer a user question"):
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}],
    )
```

LangChain, Anthropic, LiteLLM, LangGraph, OpenTelemetry, pytest: [FRAMEWORK-INTEGRATIONS-5-MINUTES.md](./FRAMEWORK-INTEGRATIONS-5-MINUTES.md).

**C. Wrap a script from the CLI:**

```bash
epi record --out refund.epi -- python process_refund.py
```

Secrets in prompts and headers are **redacted by default**. Do not turn redaction off in production.

---

## 4. Check the file

```bash
epi verify demo.epi
epi view demo.epi
```

`epi verify` finds `demo.epi` in `./epi-recordings/` if you recorded a bare name.

| What you are asking | Command |
|---------------------|---------|
| Was the file altered after seal? | `epi verify file.epi` — look at Integrity + Signature |
| Do I recognize who sealed it? | Receiver pins your `.pub` / `did.json`, then `epi verify --policy strict` |
| Did the run break our rules? | `epi policy init`, re-record, `epi analyze file.epi` (without a policy file, analyze is heuristic-only) |

In a browser with no install: https://epilabs.org/verify/ (default path does not upload the file).

Customers and auditors should use:

```bash
epi verify file.epi --policy strict
```

Add `--witness-log received.jsonl` only if a witness log was actually produced. Rely on the exit code only with `--policy strict` (WARN exits 0 under the default policy).

Exact meaning of PASS / WARN / FAIL: [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md).

---

## 5. Give it to someone else

**Simplest:** send the `.epi` file. They run `epi verify` / `epi view`, or drop it on https://epilabs.org/verify/.

If they need to know it was *you*, send your **public** key out of band (`.pub`, `did.json`, or `epi keys export` — never the private key). They pin it:

```bash
epi keys trust sender.pub --name acme
epi verify file.epi --policy strict
```

**Optional — EPI Cloud** (private beta), when you want a link instead of a file:

```bash
epi cloud login
epi demo
```

Type the short code at https://cloud.epilabs.org/auth/device, pick the customer this computer records for, then create a customer-scoped trust link on the dashboard. Details: [CLOUD.md](./CLOUD.md).

You do not need Cloud to prove a seal.

---

## What you can skip

| Skip this | Unless |
|-----------|--------|
| Account / Sign In | You are using EPI Cloud |
| `epi-register` / SCITT | You have an independent `--service` URL. Without it, the receipt is **self-issued** |
| Policy / `epi analyze` | You want rule-based checks. Without `epi_policy.json`, `epi analyze` still runs (heuristics only) |
| Self-hosted gateway | You want live capture in a shared workspace ([SELF-HOSTED-RUNBOOK.md](./SELF-HOSTED-RUNBOOK.md)) |
| MCP / ChatGPT / Claude connectors | You specifically want those hosted connectors |

---

## Honest limits (read these before a customer meeting)

- The seal covers **what was written into the file**. Unguarded calls are invisible.
- First-run identity WARN is expected until the receiver pins your key.
- EPI is evidence tooling, not a compliance certificate.
- Full list: [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md).

---

## Next

| If you want… | Open |
|--------------|------|
| 60-second copy-paste | Root [README.md](../README.md) |
| Command reference | [CLI.md](./CLI.md) |
| Framework wrappers | [FRAMEWORK-INTEGRATIONS-5-MINUTES.md](./FRAMEWORK-INTEGRATIONS-5-MINUTES.md) |
| Policy rules | [POLICY.md](./POLICY.md) |
| Keys / did:web | [IDENTITY-ONBOARDING.md](./IDENTITY-ONBOARDING.md) |
| Reviewer path | [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md) |
