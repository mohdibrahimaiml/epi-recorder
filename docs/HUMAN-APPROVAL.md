# Human approval

**Product version:** 4.7.0. Product map: [README.md](./README.md).

A sealed `.epi` can prove **"a specific, known person approved this exact
decision"** — with a signature from *that person's own key*. This page says
exactly what that proves and what it does not.

Read it with [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md) (what a
verify result means) and [THREAT_MODEL.md](./THREAT_MODEL.md).

---

## Seal, identity, approval are three different things

| Question | Answered by | Needs |
|---|---|---|
| Was this file changed after sealing? | `epi verify` integrity + signature | the file alone |
| Do I recognise who sealed it? | `epi keys trust` (a pin) | the sender's key, out of band |
| Did a **person** approve this decision? | `epi approvers add` (an approver pin) | that person's key, out of band |

An approval is a review record (version `1.2.0`) carrying a single approval
entry inside its `reviews` list, bound to the artifact and linked into the
review hash chain. It is signed with the **approver's** key, never the agent's.

A run is reported as `human_signed` only when **all** of these hold:

1. the approval record is well-formed, its `review_hash` matches its canonical
   content, its `artifact_binding` matches *this* file, and the review chain is
   intact;
2. the signature verifies against the key it names;
3. that key is pinned in the verifier's **approver** registry (`epi approvers`)
   **with the `approver` role** — a key pinned only as, say, an `auditor` does
   not count, and is reported as `signed_unknown_key`;
4. that key is **not** the key that sealed the run.

Anything else is reported honestly: `unsigned`, `signed_by_sealing_key`
("not independent of the agent"), `signed_unknown_key`, or `invalid`.

**The approver registry is not the signer registry.** Pinning a vendor's
sealing key with `epi keys trust` never makes that key an approver, and pinning
an approver never makes them a trusted sealer.

---

## Onboarding an approver

The person keeps their own key. The verifier pins its public half.

```bash
# 1. The person creates their own key (in the approver keys dir, never the agent keys dir)
epi approvers keygen --name alice@bank.com
#    prints: Fingerprint 3f78 7c9e 1a2b 4c5d

# 2. The person reads that fingerprint to the verifier's admin by phone
#    (never paste the key from a file the same channel sent)

# 3. The admin pins it, and must supply the fingerprint that was read aloud
epi approvers add alice.pub --name alice@bank.com --fingerprint "3f78 7c9e 1a2b 4c5d"

# 4. List what is pinned
epi approvers list
```

`epi approvers keygen` requires encryption at rest (`EPI_KEY_PASSWORD`, or an
interactive prompt), refuses to use the agent keys directory, and its key is
stored in `EPI_APPROVER_KEYS_DIR` (default `~/.epi/approver_keys/`). A key held
in an HSM or cloud KMS works too:

```bash
epi approvers link --name alice@bank.com --uri "pkcs11:... | awskms:... | gcpkms:..."
```

`epi approvers add` **refuses** a key that is a local agent key or an already
pinned *signer* — an approver key held by the agent host proves nothing about a
person. `--force` overrides it and prints a warning.

---

## Approving a decision

```bash
epi review run.epi approve --approval-id refund-7 --decision approve --as alice@bank.com
```

`epi review approve`:

1. verifies the file first (integrity + seal signature) and refuses otherwise;
2. shows the person the goal, the decision, the matching
   `agent.approval.request` step, the action, the manifest and the sealing key
   fingerprint;
3. requires a typed confirmation (`--yes` skips it for scripted tests and prints
   a warning);
4. refuses an `--approval-id` that is not a sealed `agent.approval.request`,
   refuses a decision other than `approve`/`deny`, and refuses to sign with the
   sealing key (separation of duties);
5. loads the signing key from the approver keys directory **only** — a missing
   entry is an error, never a silent fallback to the agent key.

Add `--case-level` to approve the whole run when there is no request step.

Adding an approval does **not** change the sealed evidence: the manifest,
`steps.jsonl` and the seal signature are untouched, so the original seal still
verifies byte-for-byte. Reviews (and therefore approvals) are additive.

### What the record carries

```json
{
  "review_version": "1.2.0",
  "reviewer_identity": {"type": "email", "value": "alice@bank.com", "role": "Approver", "verified": false},
  "reviews": [{
    "entry_type": "approval",
    "approval_version": "1.0.0",
    "approval_id": "refund-7",
    "case_level": false,
    "decision": "approve",
    "action": "refund REF-7",
    "reason": "checked against ledger",
    "approver": {"name": "alice@bank.com", "key_fingerprint": "3f787c9e1a2b4c5d"}
  }]
}
```

`reviewer_identity.verified` is always **false** on records we write. Anything
inside the file is the writer's claim; only the verifier decides, against its own
registry. `approver.key_fingerprint` is likewise a claim, checked against the
key that actually signed. `approver.name` is a claim too: the name shown is the
verifier's **own** registry entry for the signing key, and a mismatch is printed
as `(claimed: …)` with a warning (it does not make the record invalid —
registries differ between hosts).

**Backward compatibility.** The approval lives inside the existing `reviews`
list, not a new top-level field. An older reader (4.6.x) keeps `reviews`
verbatim, so its content hash is unchanged and it never raises a false tamper
alarm. It simply shows a signed review and never "human approved".

---

## Verification

```bash
epi verify run.epi                              # one plain line when the run has approvals
epi verify run.epi --require-human-approval     # exit non-zero unless satisfied
```

The report gains `human_approval`: `status` (`verified` / `incomplete` / `denied`
/ `unverified` / `none` / `failed`), one entry per approval with its
`classification`, and `requests` — one result per sealed
`agent.approval.request`. When the run has sealed requests, the headline
summarises them rather than the most recent approval:

```text
Human approval: VERIFIED — 2 of 2 requests approved by pinned approvers (alice@bank.com)
Human approval: INCOMPLETE — 1 of 2 requests approved; missing: refund-8
Human approval: DENIED — refund-7 denied by alice@bank.com
```

An approval whose `approval_id` is not a sealed request is listed in
`approvals_not_in_run` and never makes the status `verified`.

`--require-human-approval` passes only when:

- **every** sealed `agent.approval.request` has a human-signed approval whose
  latest human-signed decision is `approve`; **or**
- the latest human-signed **case-level** approval is `approve` and no request
  was denied.

A human-signed `deny` on any request fails. An approval whose `approval_id` is
not a sealed request satisfies nothing (it is still reported, with
`approval_id_present: false`). A run with neither requests nor a case-level
approval fails.

**`--policy strict` does *not* imply `--require-human-approval`.** Strict is
about *who sealed this* (a pinned signer + completeness + a provable chain);
human approval is about *who approved this*. A bank that needs both asks for
both:

```bash
epi verify run.epi --policy strict --require-human-approval
```

**"Latest" means latest in the review hash chain** — walking
`previous_review_hash` back from the tail — not `reviewed_at`, which the signer
writes. A record signed by the sealing key or by an unknown key never overrides
a human decision.

---

## What an approval does NOT prove

- **Not that the person saw the truth.** It proves they signed *this* artifact's
  decision; the run's contents are still whatever the recorder wrote.
- **Not identity beyond the pin.** It says "the key you pinned as
  alice@bank.com signed this". Verifying that the key really belongs to Alice is
  a human step, done out of band.
- **Not that the approval is on the same host.** Registries differ; pin the key
  yourself and change nothing about the others.
- **`agent.approval.response` steps and `record(approved_by=…)` are agent
  claims.** They are labelled "reported by the agent (not signed by a person)"
  wherever the CLI prints them. They are never counted as human-signed.

## Gateway link clicks vs signed approvals

A gateway link records a **click**. Whether that click came from a logged-in
user changes what *analysis* may say about it — never what verification says.

| Kind of approval | Who can write it | Counts for "approval required" in `epi analyze`? | Counts for `--require-human-approval`? |
|---|---|---|---|
| Signed with the approver's key (`epi review … approve`, 3a) | only the approver's key | yes | **yes** (only this) |
| Click by a logged-in gateway user (`gateway_link_authenticated`) | the gateway — or anything that writes steps in an SDK recording | **yes**, labelled "gateway-attested (logged-in user), not a signed approval" | no |
| Anonymous link click (`gateway_link_unsigned`) | the gateway — or anything that writes steps in an SDK recording | no, labelled self-reported | no |
| Old `gateway_human` events from before 3b | the gateway (pre-3b) — or anything that writes steps in an SDK recording | yes, unchanged, with a note that anyone with the URL could trigger them | no |

So a gateway customer who has login turned on keeps their "approval required"
checks passing, while a claim that needs a *signature* still needs
`epi review … approve`.

**`approval_source` is a claim, not a proof.** It is a plain string in the
step content, so anything that records a step can write it. At the gateway's
HTTP capture endpoints (`/capture`, `/capture/batch`, `/capture/llm` and the
proxy paths) a client-supplied gateway label is demoted to
`raw_api_unverified` and kept as `claimed_approval_source`, so the analysis can
say "the client claimed X; the gateway did not accept it". Only the gateway's
own approval route writes these labels. In an **SDK** recording the agent writes
its own steps, so it can write any label it likes — that is why the analysis
approval checks are **heuristics**. The only cryptographic proof is
`epi verify --require-human-approval` with a signed approval from a pinned
approver key.

## Fail-closed, on purpose

Anyone who can edit the file can append a review record. If they append a
**broken** one — a bad signature, a hash that does not match, a fingerprint that
does not match the signing key, a broken chain — the file's human-approval
status becomes **FAILED** and `epi verify` exits non-zero. That is deliberate:
a tampered ledger can **block** a run, but it can never **forge** an approval.
Deleting a review record entirely is likewise visible: the chain no longer
matches, and the approval is simply absent.

What an attacker *cannot* do without the approver's private key is produce a
record that classifies as `human_signed`.

---

## Related

- [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md) — what a verify result means.
- [THREAT_MODEL.md](./THREAT_MODEL.md) — agent self-approval and gateway-link forgery.
- [CLI.md](./CLI.md) — `epi approvers`, `epi review approve`, `--require-human-approval`.
- The gateway approval link records an **unsigned** click, never a human-signed
  approval. The link is a single-use, expiring token: `GET` shows a
  confirmation page (mail scanners pre-open links) and records nothing; only
  the POST records, once. The event carries
  `approval_source: "gateway_link_unsigned"`, and `epi analyze` treats it as a
  self-reported approval. A link issued before the upgrade is refused.
