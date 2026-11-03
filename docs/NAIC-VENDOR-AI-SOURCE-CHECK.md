# NAIC vendor-AI page: source check

Status: verification only. Nothing published. This file records what was checked
against primary NAIC documents before the three November assets are built.

Checked: 3 November 2026.

## Verdict

The angle holds. Every load-bearing claim survives contact with the primary
documents, with **one factual error that would have shipped**, one quote that is
a paraphrase rather than a quote, and one structural overlap with the existing
`/decision-record` page.

Do not publish the item number as written. See Correction 1.

## Primary documents retrieved

All from `content.naic.org`, retrieved 3 November 2026.

| Document | Locator |
|---|---|
| AI Risk Evaluation Supplement **v6.0 (clean)** | `inline-files/ai-risk-evaluation-supplement-v6.0-clean_1.docx` |
| AI Risk Evaluation Supplement **v5.0 (clean)** | `inline-files/ai-risk-evaluation-supplement-v5.0-clean.docx` |
| v5.0 as exposed, inside the 31 Aug meeting packet | `call_materials/materials-bdaiwg083126.pdf`, Exhibit B checklist, p.14 |
| 8 Oct 2026 meeting minutes + timeline slide | `call_materials/slides-bdaiwg110226.pdf` |
| 2 Nov 2026 meeting agenda | `call_materials/agenda-big-data-ai-wg110226.pdf` |
| Comments on v5.0, combined (225 pp) | `inline-files/comments-received-combined-10.02.2026-1-2.pdf` |
| NAIC Model Regulation 902 (Unfair Property/Casualty Claims Settlement Practices) | `inline-files/model-law-902.pdf` |

Note: `content.naic.org` returns 403 to default HTTP clients. Fetch with a
browser user agent, or the download silently fails.

## Corrections required before publishing

### Correction 1 (blocking): the vendor item is 3n, not 3p

The brief says "Exhibit B, item 3p". That was true of v5.0. **It is wrong in
v6.0**, which is the version in front of the working group.

v6.0 Exhibit B checklist, verbatim:

> 3n. Governs, monitors, tests and ensures transparency of AI Systems developed by vendors.

And 3p now means something else entirely, having moved up from 3e:

> 3p. Evaluates whether AI Systems are suitable for their intended use and should continue to be used as designed

Publishing "3p" on 9 November would point every reader at the wrong question in
the version that may be adopted on 16 November. v6.0 also added four elements
that did not exist in v5.0: 3d materiality, 3j complaints, 3k consumer
awareness and disclosures, 3l training and human oversight.

Because v7.0 is not public, the number may move again. Cite the text and give
the number as version-scoped:

> Exhibit B (checklist), item 3n in version 6.0 — item 3p in version 5.0

### Correction 2: the Monitaur quote is a paraphrase

The brief quotes Monitaur as advising governance evidence be "contemporaneous,
such as dated approval logs… not records assembled for an exam request". Those
words are not in the source. The source says:

> Contemporaneous records matter here. Dated approval logs, test results tied to
> actual deployment timelines, and change documentation that aligns with your
> system's history read as evidence of a control that functioned. Documentation
> assembled in advance of an exam request does not read the same way.

If it is used, quote the actual sentence, not the compression. Monitaur's other
line is verbatim and quotable:

> the carrier owns the governance responsibility, regardless of whether that
> system was built internally or purchased from a third party

### Correction 3: Model 902 is the property/casualty model

§4B is confirmed word-for-word:

> Detailed documentation shall be contained in each claim file in order to permit
> reconstruction of the insurer's activities relative to each claim.

§4C is also confirmed, and is better evidence for the timestamps field:

> Each relevant document within the claim file shall be noted as to date received,
> date processed or date mailed.

But the instrument is the *Unfair Property/Casualty Claims Settlement Practices
Model Regulation*. It covers P&C claims only, and it is a model regulation
adopted state by state with variation — not a federal rule. The page must not
let a life or health reader assume it applies to them. For life and health the
parallel instrument is Model 900.

## Claim-by-claim

| Claim in the brief | Status | Evidence |
|---|---|---|
| Renamed the AI Risk Evaluation Supplement | Yes | v5.0 and v6.0 titles; 8 Oct minutes record the rename |
| 12 states piloted, March–September 2026 | Yes | 8 Oct minutes; Pilot Project Summary p.2 |
| v5.0 comments closed 29 Sept | Yes | NAIC exposure notice |
| v6.0 comments closed 30 Oct | Yes | NAIC exposure notice, 14-day period |
| Working group meets 16 Nov, 12:00–1:00 PM CT | Yes | NAIC working-group page event data |
| Plan is to consider v7.0 for adoption there | Yes | Timeline slide: "Consider v. 7.0 for adoption at Fall NM"; 8 Oct minutes: "plans to adopt the supplement at the Fall National Meeting" |
| Not adopted yet | Yes | No adopted text published; v6.0 still a draft |
| Exhibits are optional supplemental material | Yes, and stronger | v6.0 Intent: "optional exhibits" and "does not independently create substantive legal duties, standards of conduct, admissions, or expanded regulatory authority" |
| Exhibit B 3p: vendor governance | **No — 3n in v6.0** | See Correction 1 |
| Exhibit B: human in the loop | Yes, plus a clause worth using | v6.0 narrative: "whether there is a human in the loop … how the company assures itself the human review is appropriate, and how any exceptions or errors are found and resolved" |
| Exhibit B: explainability and transparency | Yes | v6.0 narrative: "Discuss how the company ensures explainability and transparency into any AI models recommending or making decisions." |
| Exhibit C: internal vs vendor | Yes | Item 5: "Model development (internal, or third party, or a mix of both – include vendor name if applicable)" |
| Exhibit C: "can modify it" | Yes | Item 6, verbatim |
| Exhibit C: drift and unfair discrimination testing | Yes, plus proxy testing | Items 10 and 10a |
| APCIA: minimum information from third-party vendors | Yes, verbatim | See below |
| ACLI: no source code, training data, weights | Yes, with a nuance | See below |
| Monitaur "contemporaneous…" | **Paraphrase** | See Correction 2 |
| Model 902 §4B reconstruction | Yes, P&C only | See Correction 3 |
| Model 902 §4C dates | Yes | Verbatim, above |

### The two comment quotes, verbatim

APCIA, comments on v5.0:

> Additional guidance regarding the minimum information insurers are expected to
> obtain from third-party vendors would help companies better understand how to
> satisfy governance, validation, transparency, and oversight expectations for
> externally developed systems.

ACLI, comments on v5.0:

> The Supplement should not imply that an insurer must produce source code,
> training data, model weights, proprietary validation materials, or other
> information that it has no legal or contractual right to obtain.

The nuance matters and helps us. ACLI grounds the limit in *legal or contractual
right*, which implies the carrier is expected to have the right. That is an
argument for audit rights, not against documentation.

## Facts that strengthen the page

- **The disclaimer is in the draft itself.** "Does not independently create
  substantive legal duties, standards of conduct, admissions, or expanded
  regulatory authority." Quote it instead of hand-wringing about "not legal
  advice" alone.
- **Human oversight became its own checklist element in v6.0.** 3l: "Trains
  employees about AI System use, ensures human oversight is appropriate, and
  defines prohibited practices (if any)". Better citation than the narrative.
- **Exhibit C has no human-override field.** Human involvement is asked for in
  Exhibit B only. The record is what lets a carrier answer both consistently.
- **A commenter made our argument at the NAIC's own public meeting**, 8 Oct
  minutes, Dwayne Clark (Recon.AI): examiners may need to reconstruct "which
  system version operated, what it was authorized to do, whether required human
  oversight occurred, and whether drift was detected."
- **35 comment letters** on v5.0; NAIC has said an anonymized example company
  submission may be published after adoption. If it is, it becomes the reference
  answer and this page should be checked against it.
- **Responses are confidential** per the requesting state's authority. Say so;
  it lowers the fear of answering.

## Resolved: one checklist, not two

The first draft of this page carried its own ten questions alongside the ten on
`/decision-record`. Two lists of ten on one domain split inbound links and drift.
There is now one page, `/checklist`, with two sections — the general ten, then
"For insurance: four more questions" — and one PDF. The insurance page and
`/decision-record` both point at it rather than repeating it.

The four insurance questions are the ones the general ten do not ask:

1. Did the reviewer agree with the AI, change it, or override it?
2. Which version of the policy or rule was in force on the day of the decision?
3. Was the record made at the time of the decision, not assembled later for an exam?
4. Would the carrier notice if the record were changed after it was handed over?

`scripts/make_checklist.py` writes the page's text, `assets/checklist.pdf` and the
legacy `assets/decision-record-checklist.txt` from one source, so a stale copy
cannot survive.

## Provenance note on the sample record

`/decision-record` claims its example is "generated by the CLI, not written for
the page." The auto-claim sample respects that: it is produced by
`scripts/make_naic_claim_override_example.py` with invented data, and the file
says so in its own notes. The verification section in it is the renderer's
output, not page copy.

## Still unverified, and unreportable until 16 November

- Whether v7.0 is adopted, and whether the item number changes again.
- Whether the adopted text keeps the 3n wording as drafted.
- Whether the agentic AI questions NAIC said it expects to add land in v7.0.
- The outcome of the 2 November call. Minutes are posted about ten business days
  after a meeting, so they were not public at the time of this check.

Do not publish "the NAIC adopted" until the adopted text is posted. The 16–21
November follow-up email depends on this.

## Smaller edits

- The meeting is at the Fall National Meeting, 14–17 November. NAIC's own page
  places the session in "Convention Center—Grapevine CD—Level 3"; secondary
  coverage says Dallas. Grapevine is in the Dallas–Fort Worth area. Omit the
  city, or write "Dallas–Fort Worth".
- "12 states piloted it in exams" understates scope. The pilot covered market
  conduct exams, financial exams, financial analyses and general inquiries.
- The page is aimed at US carriers; the price on `/plans` is €4,500. Fine, but
  consider quoting USD on the insurance page.
- Keep the vendor names (Sixfold, Pibit.AI, Qumis, Avallon, CLARA, FurtherAI) out
  of the published pages. They belong in the outreach emails only.
