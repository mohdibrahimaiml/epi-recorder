# ADR-0004: Redaction preview — proposal, not built

**Date:** 2026-11. **Status:** Proposed. Not implemented.

## Context

Redaction is best-effort and pattern-based: regex patterns plus user-declared
literal secrets (`~/.epi/config.toml`, `EPI_REDACT_SECRETS`,
`EPI_REDACT_PATTERNS`). A user about to seal a run may want to see what will be
stored and what will be replaced *before* the file is written, so a missed
secret can be fixed by re-running, not by shipping the file.

Today the first sight of the result is the sealed artifact. `epi demo` prints
one line ("Secrets redacted") but there is no per-run preview.

## Why this was not built in 4.11.0

A preview cannot be added as a flag on an existing command without changing
what that command does:

- `epi record` runs a live child process. Previewing "what would be stored"
  means capturing the run, applying redaction, and showing the result before
  sealing — a new two-phase pipeline, not a display option.
- Re-running a command to preview it is unsafe: commands have side effects.
- `epi analyze`, `epi export-summary` and `epi view` read an already sealed
  file. They can show what *was* redacted, but not what *would* be, which is
  the useful moment.

Adding the flag without the pipeline would either run the command twice or
print the sealed result (too late), so the design work is deliberately
deferred rather than guessed.

## Proposal

Two steps, each shippable on its own.

1. **Post-seal report (small).** `epi analyze` gains a `Redactions` section:
   count by description, the step index and field path for each placeholder,
   and a warning when a run contains zero redactions (a likely miss for runs
   that carry prompts). Pure read of existing artifacts; no recorder changes.

2. **Pre-seal preview (new pipeline).**
   - The recorder already emits steps to `steps/` before sealing. Add a
     `--preview-redaction` mode that seals nothing: it runs the command,
     writes the step stream, applies the redactor, prints a table
     (`step · field path · description · placeholder hash prefix`) and exits
     with a non-zero code unless `--yes` is passed.
   - The table goes to stderr so the command's own stdout is untouched.
   - The run is then discarded; the operator re-runs with `--yes` once the
     preview is clean. Nothing is sealed from a preview run.
   - Limit: a preview cannot see values the recorder never captures (see
     `KNOWN_LIMITATIONS.md`). The output must say that.

## Alternatives considered

- **Print redacted steps as they stream.** Rejected: interleaves with the
  command's own output and cannot show a summary before the seal.
- **Dry-run by re-executing the command twice.** Rejected: side effects.
- **Only allowlist tooling.** Rejected: it hides what is stored instead of
  showing it.

## Consequences

- Until step 2 ships, the honest statement is the current one: redaction is
  best-effort and pattern-based, and the first complete view is the sealed
  file.
- Step 1 is additive and matches the existing `analyze` output style; it can
  ship without touching the recorder.
