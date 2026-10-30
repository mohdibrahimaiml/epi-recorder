# Witnessed pilot: the customer holds the proof

Run it:

```bash
python examples/witness_pilot/run_witness_pilot.py     # or: bash run_witness_pilot.sh
```

Four roles, four separate `EPI_HOME` directories, nothing shared but the
fingerprints they read to each other:

| Role | What it does |
|---|---|
| **vendor** | runs a refund agent, seals `run.epi`, reports a hash-only line to the customer |
| **approver** | signs the payout request with their own key (RFC 3161 timestamped) |
| **customer** | runs the witness receiver, keeps `received.jsonl`, pins both fingerprints |
| **forger** | the vendor's key, a changed decision, re-sealed afterwards |

## What the demo proves

1. **The witness payload is hash-only.** It carries the workflow id, the file
   hash, the step count, the sealed-at time and the sealer's key. No prompts, no
   decision text, no case data. The demo asserts this.
2. **A signature alone does not protect the customer.** The last step re-seals a
   different decision (approve → deny) with the vendor's own key: the hash chain
   is rebuilt, the manifest hashes are recomputed, the signature is genuine.
   `epi verify` reports **Integrity: Verified / Signature: Valid**. Without the
   log, this file looks like a real record of the same case.
3. **The customer's own record catches it.** With `--witness-log`, the same file
   fails as **NOT THE VERSION REPORTED TO YOU**, and
   `epi witness report --cases --fail-on-unwitnessed` exits 1 for that case.

The forger drops the run's approval rather than carrying a broken binding: they
cannot mint the approver's signature. (If the approval is kept, its
artifact-binding catches the rewrite independently - a second defence this demo
does not rely on.)

## What it does not prove

- That the decision was right, or that the agent did what the steps say.
- That a vendor who also *reports* the forgery would be caught. The witness
  records what was reported, not what happened. Two different reports for one
  case are visible; one report that is simply false is not.

## Commands the demo runs (so you can run them yourself)

```bash
# customer: receiver (their machine, their log)
epi witness serve --port 8099 --out received.jsonl       # HMAC with EPI_WITNESS_SECRET

# vendor: seal with the customer's endpoint
EPI_WITNESS_URL=https://customer.example/ EPI_WITNESS_SECRET=… epi record …

# customer: what the log knows, by case
epi witness report --log received.jsonl
epi witness report --log received.jsonl --cases ./received/ --fail-on-unwitnessed

# customer: verify one file against their own record
epi verify run.epi --policy strict --witness-log received.jsonl
```

`epi witness report --cases` takes a file or a directory (repeatable) and
reports **WITNESSED**, **MISMATCH** (a different version of that case was
reported), **NOT IN WITNESS LOG** (never reported at all) or **NOT CONFIRMED**
(the log carries signed receipts and you have not pinned the witness key).

`--expect cases.csv` is for the claims an insurer already knows about: each row
is a claim or case id, and any with no witnessed record comes back **MISSING**.

The vendor sets `case_id="CLM-9001"` on `record(...)`; it travels in the
hash-only witness payload, so the report speaks claim numbers instead of
workflow ids, and a re-run under a new workflow id is matched back to the claim
by its goal.

## Files

- `run_witness_pilot.py` - the whole flow, including the forgery
- `run_witness_pilot.sh` - shell entry point
- Everything else is written to a temp directory and printed at the end
