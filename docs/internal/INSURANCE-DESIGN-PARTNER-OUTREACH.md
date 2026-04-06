# Insurance Design-Partner Outreach

Use this as the operating script for the first insurance design-partner push.

## One-sentence positioning

EPI produces a signed Decision Record for every AI claim decision so a carrier can show what happened, who approved it, and whether the record was changed afterward.

## Demo path

```bash
cd examples/starter_kits/insurance_claim
python agent.py
epi view insurance_claim_case.epi
epi export-summary summary insurance_claim_case.epi
epi verify insurance_claim_case.epi
```

Show these in order:

1. Decision Summary in the browser
2. Human review flow
3. Decision Record export
4. `epi verify` tamper-evidence proof

## Outreach message

```text
Hi [Name], saw [company] was navigating [specific regulatory situation]. We built a tool that produces a cryptographically signed audit trail for every AI claim decision - the file you hand a regulator when they ask what your model decided and why. 20 minutes to see it on a real claims workflow?
```

Do not send a deck first.
Do not lead with Python, Ed25519, or architecture.
Lead with defensible evidence for claim denials under scrutiny.

## Qualification question

Ask this at the end of every demo:

```text
Is this the problem you are trying to solve?
```

## Commercial default

- `$2,500/month`
- annual commitment
- 3 feedback calls per month
- case-study permission after 90 days

## Prospect tracker template

| Company | Segment | AI / CTO Lead | Compliance / Risk Lead | Regulatory trigger | Outreach date | Reply | Demo date | Next step |
|:--------|:--------|:--------------|:------------------------|:-------------------|:-------------|:------|:----------|:----------|
| Example Carrier | Insurance | name@company.com | name@company.com | claim denial scrutiny | YYYY-MM-DD | pending | - | research |
