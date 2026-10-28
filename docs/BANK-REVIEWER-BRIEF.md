# Bank reviewer brief

One page, for the bank's security or risk reviewer. Every claim here is
checkable by running the command next to it or by following the link.

## What a verified file proves — and does not prove

**Proves (mathematically, offline):** the recorded steps have not changed since
the file was sealed; the seal was made by the private key whose fingerprint you
pinned; and each linked approval was signed by the approver key you pinned.

**Does not prove — timing, in particular:** an approval is signed *after* the run
has been sealed. It evidences that a person reviewed this record and signed off
on it; it does **not** prove the person approved the action *before* it happened.
If your control requires pre-action approval, that has to come from your workflow
at the time, not from the file. EPI also does not prove the recorded run is the
*only* thing that happened, that the agent was honest, or that the model's
decision was correct. EPI proves provenance and integrity — not truth. See
[docs/VERIFICATION_CONTRACT.md](VERIFICATION_CONTRACT.md) and
[docs/KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## The three commands you run

```bash
epi keys trust vendor.pub --name vendor --fingerprint <fingerprint from the vendor>
epi approvers add alice@bank.com.pub --name alice@bank.com --fingerprint <fingerprint from the approver>
epi verify run.epi --policy strict --require-human-approval
```

The vendor sends you **their sealing public key file** and each approver sends
**theirs** — the commands pin files, not numbers. The two fingerprints must
arrive on a **different channel** from the file (a phone call is enough). If an
attacker swaps the file and its key, the pinned fingerprint no longer matches and
`epi verify` fails.

## What each result means

| Exit | Output | Meaning |
|---|---|---|
| `0` | `DECISION: PASS` | Seal intact, signer pinned, every request signed off by a pinned approver (after sealing). |
| `1` | `Human approval: INCOMPLETE` | Some requests have no signed approval yet. Do not act on the run. |
| `1` | `Human approval: DENIED` | A pinned approver said no. Treat as rejected. |
| `1` | `DECISION: FAIL` / `Signature: Invalid` | The file changed after sealing, or the signature is bad. Do not use it. |
| `1` | `NOT A KEY YOU TRUST` | Sealed by a key you have not pinned. Confirm the fingerprint by phone. |

## Why you can rely on this

- **Verification is offline.** `epi verify` runs on your machine, from open
  source ([github.com/mohdibrahimaiml/epi-recorder](https://github.com/mohdibrahimaiml/epi-recorder)),
  with no network call required.
- **No client data goes to EPI.** The `.epi` file never leaves the vendor or the
  bank; there is no telemetry unless you opt in.
- **You can check a file in a browser** without installing anything:
  [epilabs.org/verify](https://epilabs.org/verify). The browser reports what it
  can check offline and never claims a human approval it cannot verify.
- **You can break-test the claims yourself:** [CHALLENGE.md](../CHALLENGE.md).

## The honest gaps

- Streaming through the hosted **gateway** is not captured yet; the SDK path is.
- The **analysis** approval checks are heuristics, not proofs. The
  cryptographic proof is `epi verify --require-human-approval`.
- **Azure Key Vault** is not supported (see [docs/KEY-CUSTODY.md](KEY-CUSTODY.md)).

Each of these is a known limitation, listed in
[docs/KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), not a marketing caveat.
