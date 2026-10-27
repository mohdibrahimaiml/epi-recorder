# Break the seal

EPI claims that a sealed `.epi` file cannot be changed without detection, and
that an approval can only be called human-signed when a person's own key signed
it. **Try to break those claims.** If you do, we publish it, fix it, and credit
you.

This is a **credit-only** challenge. There is no money and no bug bounty —
[GOVERNANCE.md](GOVERNANCE.md) says so, and it stays that way. What you get is a
public write-up, a fix, and your name in the hall of fame below.

## What counts as a break

Use the latest released `epi-recorder` (`epi verify`) and the public
[epilabs.org/verify](https://epilabs.org/verify) page. A break is any of:

| # | Criterion | What it means |
|---|---|---|
| **a** | A file that `epi verify` reports as **intact and signed by the challenge key**, but whose steps differ from the published original. | The seal no longer proves what it says it proves. |
| **b** | A file where `epi verify --require-human-approval` **passes** (with the published approver key pinned) **without** the challenge approver's private key. | An approval is being accepted that no person signed. |
| **c** | A tampered file that the **browser verifier** shows as intact. | The display layer lies about integrity. |
| **d** | A file that makes `epi verify` report a **different signer fingerprint** than the key that actually signed it. | Identity is misattributed. |
| **e** | Anything that makes a verifier **crash, hang, or run code** from a crafted `.epi`. | The verifier itself is unsafe. |

Run the checker on any candidate before reporting:

```bash
python challenge/check_submission.py your-file.epi
```

It prints `BREAK` or `NO BREAK` for **a–d**. Criterion **e** needs a human —
report it privately.

## What does NOT count

- Stolen, leaked or coerced private keys, or being the legitimate owner of a key.
- Social engineering, phishing, or attacks on people.
- Attacks on EPI Cloud infrastructure, hosted services, or other customers'
  data. DoS of hosted services is out of scope.
- Anything that requires the challenge signing key or approver key.
- "The file says something false." EPI proves *what was recorded and that it has
  not changed*, not that the agent was honest — see
  [docs/VERIFICATION_CONTRACT.md](docs/VERIFICATION_CONTRACT.md) and
  [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

## Rules and safe harbour

- **Report privately first.** Use GitHub's private vulnerability reporting on
  this repository (Security → Report a vulnerability), not a public issue.
  See [SECURITY.md](SECURITY.md).
- **90-day disclosure.** We will acknowledge within 5 working days, fix, and
  coordinate publication. If a fix takes longer, we will say so and keep you
  updated.
- **Test only your own artifacts.** Do not use other people's data, and do not
  run attacks against infrastructure you do not own.
- We will not pursue legal action for good-faith research that follows these
  rules.
- Public write-ups are welcome **after** a fix ships, using the
  "Challenge result (public write-up)" issue template.

## The challenge artifacts

| File | What it is |
|---|---|
| [`challenge/challenge-original.epi`](challenge/challenge-original.epi) | A refund decision with two approval requests, sealed and approved by the keys below. |
| [`challenge/challenge-signing-key.pub`](challenge/challenge-signing-key.pub) | The sealing key (public half). Fingerprint **50d9 acec 3999 5405**. |
| [`challenge/challenge-approver-key.pub`](challenge/challenge-approver-key.pub) | The approver key (public half). Fingerprint **3920 dbca e514 b67c**. |

The private halves are held offline and are not in this repository. You do not
need them to try: the whole point is that you cannot produce these without them.

Regenerate everything (new keys, new artifact) with:

```bash
python scripts/make_challenge_artifacts.py
```

It writes the private keys to a temp directory **outside** the repository and
prints where. Never commit them.

## Hall of fame

Credit-only, in the order the report arrived. Each entry names the criterion and
links the fix.

| Date | Researcher | Criterion | Fix |
|---|---|---|---|
| _empty — be the first_ | | | |
