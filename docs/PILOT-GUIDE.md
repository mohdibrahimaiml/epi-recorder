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

with record("run.epi", goal="Refund decision") as session:
    ...                      # your LangGraph graph, your tools, your model

    # Ask for a human decision, and name it so the sign-off can be matched to
    # it. The agent never answers this itself: a person signs the sealed record
    # with their own key (step 4).
    session.approval_request(
        "refund REF-7",
        approval_id="refund-7",
        reason="over the auto-approve limit",
    )
```

Framework integrations (`wrap_openai`, `wrap_anthropic`, LangGraph) are listed in
[README.md](../README.md). The pilot kit's
[`agent.py`](../examples/pilot_kit/agent.py) is a complete example.

## 3. Put the sealing key in a vault

The key that seals must live where the agent cannot read it, and EPI will refuse
to seal without it. Create the Ed25519 key **inside** the vault first — the
SoftHSM token setup, the right module path for your platform, and the AWS KMS
variant are in [docs/KEY-CUSTODY.md](KEY-CUSTODY.md). Then point EPI at it:

```bash
export EPI_PKCS11_PIN='the vault PIN'
export EPI_REQUIRE_EXTERNAL_KEY=1
epi keys link --name default --uri "pkcs11:token=epi-pilot;object=epi-sealer;module-path=/usr/lib/softhsm/libsofthsm2.so"
```

Run `epi keys link` with **no** key file of that name present. Never run
`epi keys generate` first: it writes a private key to disk — exactly what this
step exists to avoid — and `link` then refuses, because a link name must not
shadow a local key. If an earlier attempt left `default.key` behind, delete it
before linking.

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

Send the `.epi` file however you already send documents. Then exchange **key
files** with the bank — not just numbers — and read the numbers aloud to confirm
them:

1. **You send your sealing public key file** — the `.pub` beside your sealing
   key (`epi keys list` prints where it lives).
2. **Each approver sends their own public key file**, for everyone whose
   sign-off should count (`epi approvers list` prints their paths).
3. **Then read the fingerprints aloud, by phone.** Your sealing key's
   fingerprint — the 16 hex characters `epi keys list` prints — and each
   approver's. The *file* is what the bank pins; the *spoken number* is how it
   knows the file arrived unswapped.

The bank pins the keys by fingerprint ([docs/BANK-REVIEWER-BRIEF.md](BANK-REVIEWER-BRIEF.md))
and runs three commands. That is the pilot.
