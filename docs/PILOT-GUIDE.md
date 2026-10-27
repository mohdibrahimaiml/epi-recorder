# Pilot guide — for the AI vendor

How to run a bank pilot in a day. Two pages, no jargon. Everything here is
checkable against `examples/pilot_kit/run_pilot_demo.sh` (which runs the same
steps as a script, offline, with no API key).

## 1. Install

```bash
pip install "epi-recorder[pkcs11]"     # SoftHSM / PKCS#11 vault
# or
pip install "epi-recorder[aws-kms]"    # AWS KMS
```

LangGraph is optional but the pilot kit uses it when present:

```bash
pip install langgraph
```

## 2. Record your agent

Wrap the run. Nothing changes about how the agent works.

```python
from epi_recorder import record

with record("run.epi", goal="Refund decision"):
    ...                      # your LangGraph graph, your tools, your model
```

Framework integrations (`wrap_openai`, `wrap_anthropic`, LangGraph) are listed in
[README.md](../README.md). The pilot kit's
[`agent.py`](../examples/pilot_kit/agent.py) is a complete example.

## 3. Put the sealing key in a vault

The key that seals must live where the agent cannot read it, and EPI will refuse
to seal without it:

```bash
export EPI_REQUIRE_EXTERNAL_KEY=1
epi keys generate                          # one time
epi keys link --name default --uri "pkcs11:token=epi-pilot"
```

Full detail, including AWS KMS and Azure caveats:
[docs/KEY-CUSTODY.md](KEY-CUSTODY.md).

## 4. Set up approvers

Each approver makes their **own** key. The private half never leaves their
machine, and you never hold it.

```bash
epi approvers keygen --name alice@bank.com     # the approver runs this
```

They read their fingerprint out loud (or over the phone). That is the whole
trust story: [docs/HUMAN-APPROVAL.md](HUMAN-APPROVAL.md).

## 5. Where the files live

`run.epi` is an ordinary file on the vendor's (or the bank's) storage. **Nothing
has to be sent to EPI Cloud** — verification is offline and open source. EPI
Cloud is optional, for hosted inboxes and dashboards.

## 6. Hand over to the bank

Send the `.epi` file however you already send documents. Then, **on a separate
channel**, give the bank:

1. your **sealing key fingerprint** (the 16 hex characters `epi keys list`
   prints) — a human reads this aloud, so a swapped file cannot pass;
2. the **approver fingerprints** for anyone whose sign-off should count.

The bank pins both by fingerprint ([docs/BANK-REVIEWER-BRIEF.md](BANK-REVIEWER-BRIEF.md))
and runs three commands. That is the pilot.
