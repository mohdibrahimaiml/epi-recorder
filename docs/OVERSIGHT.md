# The oversight report

`epi oversight report` answers the question a bank, an insurer or an auditor asks
in a period-shaped way:

> Over these three months: what did your AI decide, which model answered, who
> approved it, which cases did the vendor report but never deliver, and which
> cases did you expect that were never sealed at all?

A folder of decision files answers none of that on its own. The report joins the
three things a customer already holds — the sealed files, their own witness log,
and their own list of expected cases — and names the gaps instead of quietly
leaving them out.

## Run it

```bash
epi oversight report \
  --cases ./received \            # a .epi file, or a directory of them
  --log received.jsonl \          # the customer's witness log
  --since 2026-09-01 --until 2026-10-31 \
  --expect cases.csv \            # case IDs you expected to see
  --out oversight-2026-Q3.html
```

| Option | What it does |
|---|---|
| `--cases` | A `.epi` file or a directory. Repeatable. |
| `--log` | The witness log (`received.jsonl`, or a signed `witness.json`). Defaults to `EPI_WITNESS_LOG`, then `./received.jsonl`. |
| `--since` / `--until` | Inclusive UTC days. Selects which decisions and which reports are counted. |
| `--expect` | CSV whose first column is case IDs. Anything with no file and no report is listed. |
| `--witness-pubkey` | Pinned EPI witness key, for logs that carry signed receipts. |
| `--out` | The one-page HTML report. |
| `--json` | Machine-readable output, for a dashboard or a CI gate. |
| `--fail-on-gaps` | Exit 1 when a reported case has no file, an expected case was never sealed, or a file is not in the witness log. |

## What it reports

- **Decisions by outcome.** `DENY`, `deny_claim` and `Denied` are one outcome to a
  reader, so they are grouped after the same normalisation the Decision Record
  uses.
- **Model versions.** The served model per decision, with first and last seen —
  the change log a bank asks a vendor for, read from the records instead of asked
  for.
- **Human approvals**, kept distinct: signed with a pinned key, signed with a key
  this verifier has not pinned, no approval attached, a signature that does not
  verify, and a signature by the vendor's own sealing key (which is not an
  approval by a person).
- **Reported to you, but no file delivered.** Your witness log has a report for
  the case; no sealed file was handed over in this set.
- **Expected, but never sealed or reported.** In your `--expect` list with
  neither a file nor a report.
- **Decisions that do not match your witness log**, with the reason: never
  reported, or a different version of the same case. A file that is a different
  version of a reported case is listed but **not counted** in the outcome, model
  or approval totals — the customer cannot rely on anything inside it, least of
  all the decision it shows.

The period selects what is counted. The reconciliation is over the whole set, so
a file delivered last month still counts as delivered for a case reported this
month.

## What it proves — and what it does not

**Proves:** that these files exist, that they verify, that they are (or are not)
the files the vendor reported to you, and what they say about outcome, model and
approval.

**Does not prove:** that the AI was right, that the run was captured completely,
or that you met a regulatory duty. A vendor can choose not to report a seal at
all; the `--expect` list is what turns that silence into a visible gap.

## Example: the witness pilot

`examples/witness_pilot/run_witness_pilot.py` produces a vendor, an approver, a
customer and a forger. Pointed at the customer's files — the run they were told
about and the copy the vendor re-sealed afterwards — with their own log and
expectations, the report counts the one decision the log confirms and names the
other file as excluded:

```
Oversight report  all records, 2026-11-01 to 2026-11-01
  2 sealed file(s), 1 decision(s) counted, 1 excluded (not the copy your log reported)
Decisions by outcome        Approved 1
Human approvals             signed, key pinned 1
Against the witness log     witnessed 1 · mismatch 1
Not counted                 run-forged.epi — different version of this case
Expected, never sealed      CLM-2002
```

The forger's file is on the page, with its reason, but its outcome never joins
the totals. That is the shape of the conversation with a vendor: not "trust us",
but "this file is not the one you reported, and this case never arrived".
