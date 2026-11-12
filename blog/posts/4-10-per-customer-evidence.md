---
title: "4.10.0: evidence per customer, releases you can check, Apache-2.0"
date: November 12, 2026
description: What changed in EPI 4.10.0, why seal numbers are now per customer, and what a reviewer can actually verify.
excerpt: One signing key can serve several banks without leaking one customer's numbers to another. That is the core of 4.10.0.
---

# 4.10.0: evidence per customer, releases you can check, Apache-2.0

4.10.0 is out. It is the release where EPI stops being a good record for one company and becomes a record that survives a **relationship** between companies.

## The problem with one key and several customers

An AI vendor rarely has one customer. The same signing key seals runs for several banks, insurers or hospital groups. Before 4.10, that key produced one seal sequence: customer A saw seals #1, #3, #4 and concluded #2 was missing, when #2 belonged to customer B.

4.10 gives every customer an independent chain. Each seal number, previous link and content digest is scoped to the audience that received it. A file sealed for two customers stores only salted commitments, so neither copy reveals the other's numbers, count or identity. `epi witness audit` reports gaps per customer, and a withheld seal is visible only in the chain it belongs to.

This matters in a sales conversation: a bank does not want a report that leaks its competitor's activity. Per-customer chains make the same artifact safe to hand to both.

## Releases and approvals became records, not settings

A decision is only defensible if you can show what policy and model produced it, and who approved the action before it ran.

- `epi release create` seals the policy, prompts, model ids, tool schemas and code by hash. `required_approvals` is inside the digest.
- `epi release approve` adds a signature from the approver's own key and reports it to the witness, so approval time is observed outside the vendor's system.
- `epi verify --release` answers MATCHES, DRIFT, UNAPPROVED RELEASE, APPROVED AFTER USE and the rest.
- `ApprovalGate` binds one exact tool call and blocks expiry, changed arguments, nonce reuse, the sealing key and unpinned approvers. `--require-pre-action-approval` reports APPROVED BEFORE ACTION only when the witness order is request < response < executed.

The demo on [epilabs.org/verify](https://epilabs.org/verify) runs those commands against files we ship.

## Apache-2.0, and what stays free

From 4.10.0 the public tool is Apache-2.0, with an explicit patent grant. Versions up to and including 4.9.0 remain MIT, permanently.

Recording, sealing, verification, release and approval records, analysis, oversight, the witness receiver, AGT/TRACE conversion and the reviewer tooling stay free. The paid `epi-enterprise` package is the operational layer: gateway, adapters, guardrails, integrate, and the compliance command surface. The free wheel ships a stub at each moved import path so nothing fails with a parse error.

## What a reviewer still has to decide

A signature proves the file has not changed since it was sealed. It does not prove nothing was omitted: that needs a witness that existed before sealing. An unpinned file reports **NOT A KEY YOU TRUST** until you confirm the sender's key out of band. Release and pre-action checks are CLI checks; the browser verifier covers the seal.

Those are properties, not defects. The [known limitations](https://github.com/mohdibrahimaiml/epi-recorder/blob/main/docs/KNOWN_LIMITATIONS.md) say so plainly.

## Try it

```bash
pip install -U epi-recorder
epi demo --no-browser
epi verify epi-recordings/demo_refund.epi
```

Then hand the file to someone who has no reason to trust you, and see whether they can check it without asking you to log in. That is the only test that matters.
