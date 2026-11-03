# Sales questions and the kill test (internal)

Not published. Customer-facing offer: `docs/PILOT-OFFER.md`.

## The ten questions

Ask these in the first call. Do not pitch before question 5.

1. "In your last carrier or bank security review, what exact questions did they ask about AI audit trails, explanations or logging? Can you show me the questionnaire item?"
2. "Has any customer ever asked you to prove a past decision record was not altered? What happened?"
3. "When a customer disputes a specific AI decision today, how long does it take you to reconstruct what the model saw, which version answered, and who approved it?"
4. "Which deal is stuck right now because of AI governance questions, what is it worth, and what is the deadline?"
5. "Who in your company would sign a €10,000 purchase to unblock that deal, and from which budget?"
6. "What do you already use for logs and traces (Langfuse, Datadog, S3 Object Lock, SIEM)? Why is that not enough for the customer?"
7. "Would your customer (the carrier or bank) accept a record they can verify themselves, and would they keep a hash log on their side? Who there would own it?"
8. "Does your contract with the carrier or bank include audit rights or regulator-cooperation clauses? What do they say about records?"
9. "What would you need from us (entity, DPA, insurance, SOC 2) before you let our code into your decision path?"
10. "If this worked, would you pay monthly for hosted retention and sharing with customers? What would make that a yes?"

## Qualification rule

Take the engagement only when all three are true:

- a **named relying party** (carrier, bank, auditor);
- a **specific stuck item** (questionnaire question, contract clause, review finding);
- a **deadline**.

Otherwise sell the **€4,500 readiness assessment**, or walk away.

## Buyer order

1. US insurtech / claims / underwriting AI vendors selling to carriers (NYDFS CL7, NAIC states).
2. Lending and credit-decisioning AI vendors selling to US banks (Reg B specific reasons).
3. Agent companies pursuing AIUC-1 or SOC 2 + AIUC-1.
4. Vendors selling into EU banks and insurers (DORA now; AI Act high-risk from Dec 2027).
5. Canada and Singapore — pipeline for 2027, not revenue now.

## Channels

- AIUC-1 accredited auditors: Schellman, A-LIGN, Coalfire.
- Governance platforms that consume evidence: Credo AI, ValidMind.

## Do not lead with

- Ed25519, hash chains, "customer witness", SCITT.
- Compliance or certification claims.
- The €4,500 as the headline for a bank-facing deal; it anchors too low.

Lead with: the record, the reasons, the approval, audit rights, and the review the customer is running.

## Kill test

If **20 qualified conversations** (named relying party, stuck item, deadline) produce **fewer than 2 paid engagements by 31 March 2027**, stop selling this offer and pivot to supplying evidence packs to governance platforms or AIUC-1 auditors.

## Stop spending time on

- EPI Cloud tier work.
- India / RBI positioning until the draft model-risk guidance is final.
- More public code. The free core is complete; paid value lives in hosting, documents and the signature.
