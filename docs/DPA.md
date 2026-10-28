# Data Processing Addendum (starting point — have counsel review)

**Product version:** 4.7.0. Related: [SUBPROCESSORS](./SUBPROCESSORS.md),
[DATA-RETENTION](./DATA-RETENTION.md). **Not legal advice.** This is a
starting-point DPA for EPI Cloud private-beta pilots. Both sides should have
counsel review it before signing. If it conflicts with a signed agreement,
the signed agreement wins.

## 1. Subject matter and duration

EPI Labs processes customer data to provide EPI Cloud (witness receipts,
trust links, Evidence Room storage, login) for the duration of the pilot or
subscription, plus the retention windows in [DATA-RETENTION](./DATA-RETENTION.md).

## 2. Nature, purpose, and types of data

| Category | Examples | Notes |
|---|---|---|
| Witness receipts | Workflow IDs, file/manifest hashes, timestamps | Hash-only by design. Not reversible into content. |
| Evidence Room files | `.epi` files the vendor selects and uploads | Full bytes, max 25 MB each. Only what you upload. |
| Trust-link metadata | Link scope, expiry, view events | Metadata, not content. |
| Account data | OAuth identifiers (GitHub/Google), workspace name | Login only. |
| Bucket metadata | Endpoint/region/bucket names for customer-owned storage | Credentials and objects never reach EPI Labs. |

No special-category data is solicited. Do not upload secrets into evidence
files; the recorder redacts known patterns by default, but redaction is
regex-based and not exhaustive ([KNOWN_LIMITATIONS](./KNOWN_LIMITATIONS.md)).

## 3. Processor obligations (EPI Labs)

- Process only to provide EPI Cloud and only on documented instructions
  (your uploads, your witness configuration, your deletion requests).
- Confidentiality: personnel access is limited to operating the service.
- Security measures: encryption in transit (Cloudflare TLS), hash-only
  witness default, Ed25519-signed checkpoints, no customer credentials held
  (see §5 and [THREAT_MODEL](./THREAT_MODEL.md)).
- Breach notification: without undue delay and within 72 hours of becoming
  aware, with nature, likely consequences, and mitigation.
- Assistance with data-subject requests and impact assessments, to the extent
  the service configuration allows.
- Return or delete on termination per [DATA-RETENTION](./DATA-RETENTION.md).

## 4. Controller obligations (you)

- Lawful basis for what you upload and witness.
- No prohibited content: do not use EPI Cloud to exfiltrate or store data
  you have no right to process.
- Pin and manage your own signing keys; a valid signature proves key
  possession, not organizational authority ([VERIFICATION_CONTRACT](./VERIFICATION_CONTRACT.md)).

## 5. Sub-processors

Listed in [SUBPROCESSORS](./SUBPROCESSORS.md). A new sub-processor is added
there before it receives customer data; object in writing within 14 days and
we will work in good faith on an alternative or wind the pilot down.

## 6. International transfers

Processing runs on Cloudflare's network and the legacy Render hosts named in
[SUBPROCESSORS](./SUBPROCESSORS.md) (US). EU/UK customers: transfers rely on
the providers' transfer mechanisms plus this DPA. Tell us if you need a
region-pinned deployment — that is a scoping conversation, not a default.

## 7. Liability and order of precedence

Liability caps follow the pilot agreement or, absent one, are limited to fees
paid in the preceding 3 months. Order of precedence: signed pilot/MSA terms,
then this DPA, then the docs. Nothing here limits liability that cannot be
limited by law.

## Annex: EU Standard Contractual Clauses (2021/914, Module Two) — $0 path

A lawyer's review stamp costs money; the legal instrument itself does not.
For EU/UK transfers, the parties incorporate the European Commission's
Standard Contractual Clauses of 4 June 2021 ( Implementing Decision
2021/914), **Module Two (controller to processor)**, by reference, with the
choices and completions below. The full SCC text prevails over this summary.

- **Docking clause (Clause 7):** applies — additional controllers/processors
  may accede in writing.
- **Clause 9 (sub-processors):** Option 2 (general authorisation) with the
  list in [SUBPROCESSORS](./SUBPROCESSORS.md) and the 14-day objection
  window in §5 above.
- **Clause 11 (redress):** data subjects may enforce as third-party
  beneficiaries as provided in the SCCs; complaints to `mohdibrahim@epilabs.org`
  first, then the competent authority.
- **Clause 13 (supervision):** the authority of the customer's establishment;
  if none in the EU/EEA, as agreed in the pilot terms (TBD per customer).
- **Clause 17/18 (law/forum):** as agreed in the pilot terms (TBD per
  customer); absent agreement, the law of Ireland.
- **Annex I.A (parties):** controller = you (details in the pilot terms);
  processor = EPI Labs (contact `mohdibrahim@epilabs.org`).
- **Annex I.B (transfer details):** categories and purposes per §2 above;
  hash-only witness receipts, vendor-selected evidence files (max 25 MB),
  trust-link metadata, account identifiers, bucket metadata.
  Retention per [DATA-RETENTION](./DATA-RETENTION.md). No sensitive data
  solicited.
- **Annex I.C:** competent authority per Clause 13 above.
- **Annex II (security measures):** §3 above plus, by reference, the controls
  in [THREAT_MODEL](./THREAT_MODEL.md) (Ed25519 seals, hash-chained steps,
  offline TSA validation, hash-only witness) and the limits in
  [KNOWN_LIMITATIONS](./KNOWN_LIMITATIONS.md).
- **Annex III (sub-processors):** [SUBPROCESSORS](./SUBPROCESSORS.md).
