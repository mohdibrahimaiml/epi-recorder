# EPI evidence for AIUC-1 audits

**Status:** Draft mapping, not reviewed or endorsed by AIUC  
**Date:** 2026-10-10  
**Version:** 1.1.0

---

## What this document is

AIUC-1 is a certification standard for AI agents. An accredited auditor checks a company's policies,
operations and technical controls, and AIUC issues the certificate. EPI is not part of that process and
cannot certify anything.

What EPI can do is produce **evidence an auditor can check**: a signed `.epi` file of what an agent did,
which anyone can verify offline without trusting the company that produced it. This document lists which
parts of an `.epi` file are relevant to each AIUC-1 domain, and, just as important, what EPI does not cover.

Check the current AIUC-1 standard at aiuc-1.com for the exact controls. This mapping is by domain only;
it does not cite AIUC-1 control IDs, and it has not been checked against them.

## What an `.epi` file proves, and what it does not

It proves:

- **The record has not changed since it was sealed.** Every file in it has a SHA-256 hash in the manifest,
  and the manifest is signed with Ed25519. Any edit makes `epi verify` fail.
- **The steps are in the order they were sealed and none was removed or inserted in between.** Each step
  in `steps.jsonl` carries the hash of the step before it.
- **Which key sealed it.** The public key is inside the file. Whether that key belongs to the company you
  think it does is a separate question, answered only if you pin it (`epi keys trust`) or check it against
  a registry you trust.

It does not prove:

- **That the record is complete.** EPI records what its SDK, gateway or caller captured. Anything not sent
  to it is not in the file.
- **That the agent behaved safely, fairly or correctly.** The file preserves what happened so a person can
  judge it.
- **When it was sealed, beyond the sealer's own clock,** unless a trusted timestamp or transparency receipt
  is present. RFC 3161 timestamp tokens are stored, but `epi verify` does not yet validate their signature.

## Evidence by AIUC-1 domain

The six domain names below are the ones EPI's `--aiuc1` report uses (`epi_core/aiuc1_mapping.py`).

### A. Data and privacy

- **Redaction before sealing.** `epi_core/redactor.py` replaces matches for built-in patterns before steps
  are written. The patterns cover API keys and tokens for common providers, passwords and credential
  assignments, connection strings, private keys, JWTs, email addresses, phone numbers, US Social Security
  numbers and card numbers. Redaction is on by default.
- **Each redaction leaves a marker** with a description and an HMAC-SHA256 of the original value, so a
  reviewer can see that something was removed and what kind of thing it was, without seeing it.
- **Not covered:** the patterns are regular expressions. They miss secrets and personal data in formats they
  do not match (names, addresses, free-text health details and so on). They are a safety net, not a data
  protection programme.

### B. Security

- **Tamper evidence** through hashes, the step chain and the Ed25519 signature, as above.
- **Tool calls and their results** are recorded in order, so a reviewer can see which tools the agent
  called and with what arguments.
- **Optional SCITT receipt.** `epi scitt register` adds a COSE-signed receipt with a Merkle inclusion proof.
  By default this uses a local service on the sealing machine, which is not independent. An independent
  receipt needs `--service` pointing at a transparency service run by someone else.
- **Not covered:** EPI does not test the agent for prompt injection, jailbreaks or data exfiltration. It
  records what happened in runs it captured, including any attacks that occurred in them.

### C. Safety

- **A fixed record of each run,** so unsafe or out-of-scope behaviour that happened can be found and cannot
  later be edited out.
- **Policy checks.** When a policy file is present at sealing time, EPI evaluates the run against it and
  seals the policy, the result and the fault analysis with the run (`policy.json`, `policy_evaluation.json`,
  `analysis.json`). `epi analyze` shows the result and can test a different policy against the same run.
- **Not covered:** EPI does not prevent harmful behaviour, and a policy check only finds what the policy
  describes.

### D. Reliability

- **Errors are recorded,** including failed model calls (`llm.error` steps) when the SDK captures them, so a
  reviewer can see how failures were handled.
- **Not covered:** EPI does not measure accuracy or consistency across runs. `epi_compare_runs` (hosted
  connector) shows where two sealed runs differ, which can support such testing.

### E. Accountability

- **Human review is recorded separately.** `epi review` writes `review.json`, which is bound to the sealed
  artifact and can be signed, without changing the original run.
- **Signer identity** is reported by `epi verify` (`identity_status`), and `--policy strict` fails files from
  unknown signers.
- **Not covered:** incident response, ownership, disclosure policies and other organisational controls.
  Those are documents and processes the company provides to the auditor.

### F. Society

- **A durable, shareable record** supports investigations and disclosures after an incident.
- **Not covered:** EPI has no measure of societal impact. The `--aiuc1` report's checks under this heading
  (whether analysis findings and redaction markers are present) are evidence that review happened, not
  evidence of impact.

## The `epi verify --aiuc1` report

```bash
epi verify --aiuc1 run.epi
epi verify --aiuc1 --policy strict run.epi   # also fail if the signer is unknown
```

This runs the normal verification (hashes, chain, signature, identity, SCITT receipt if present) and then
groups the results under the six domain headings.

Each domain is reported as PASS, PARTIAL or FAIL. **These labels mean only "EPI found all, some or none of
the evidence it looks for under this heading".** They are EPI's own checks, they are not AIUC-1 controls,
and a PASS is not an AIUC-1 result. Use the report as an index to evidence, and give the auditor the `.epi`
files themselves.

## How a company would use this in an audit

1. Capture production or test runs with the EPI SDK or gateway, with redaction on.
2. Pin the company's signing key (`epi keys trust`) and give the public key to the auditor.
3. Hand the auditor the `.epi` files for the runs they sample. They verify them offline with `epi verify` or at
   https://epilabs.org/verify.
4. Record human review with `epi review`, so sign-offs are sealed alongside, not mixed into, the run.
5. Optionally register files with an independent SCITT service for third-party proof of when they existed.
