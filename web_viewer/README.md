# EPI Case Review Web Viewer

`web_viewer/` is the browser-only case review app for local `.epi` case files.
It powers both:

- the default `epi view` experience for preopened case files
- the packaged `viewer.html` baked directly into each `.epi` case file

It is designed to feel simple for non-technical reviewers:

- case-first entry: open one example case or one saved case file before touching setup
- optional setup: connect a real system only when you want a safe sample, live case preview, or starter kit
- refund approvals first: the default starter flow is built around refund approvals as the easiest business workflow to understand
- safe sample preview: if real connector credentials are not ready yet, EPI can open a realistic local bridge sample so the workflow is still testable end to end
- saved connector setup: keep connector fields stored only in this browser on this device, while secret keys stay only in the current session
- local connector bridge: point the setup flow at `epi connect serve`, check the bridge, and fetch a live source record without leaving the browser review flow
- live case preview: when a bridge fetch succeeds, EPI opens that real source record as a reviewable case immediately instead of leaving it buried in setup
- shared team workspace: when multiple people use the same self-hosted bridge, case previews and review updates can be synced through the bridge instead of staying single-user only
- optional local sign-in: a self-hosted workspace can use either one shared bearer token or a small local users file, and the browser keeps session tokens only in the current tab
- recorder starter export: download a zip with `epi_policy.json`, a real `epi_recorder` starter script, system-specific connector helpers, sample input, and a run guide
- live source record export: when a bridge fetch succeeds, the starter pack also carries `live_source_record.json` so the first run can start with real business context
- `Inbox`: load multiple case files and see what needs attention first
- `Case`: open one decision case file, understand what happened, and record a human outcome
- guided next steps: each case tells the reviewer what matters most and which action to take next
- plain-English review actions: approve the decision, reject the decision, or escalate and decide later
- browser signing: paste the same EPI Ed25519 `.key` private key the CLI generates to produce signed review notes
- signed review status: reloaded reviewed artifacts show whether the attached review notes are signed, unsigned, or have a bad signature
- packaged artifact rebuild: the baked `viewer.html` can rebuild a reviewed `.epi` offline from embedded `epi-data`
- extracted review export: `epi view --extract` writes a self-contained `viewer.html` with vendored JSZip so the extracted review page also works offline and in air-gapped environments
- `Rules`: load the sealed `policy.json`, edit real EPI rule types in plain language, and export a valid `epi_policy.json`
- `Reports`: export a summary, review, or trust report without using the CLI

The starter rule families in this editor are aligned with `epi policy init --starter-rule ...`, so the browser and CLI generate the same custom starter shapes.
`epi policy init --open-editor` and `epi policy show --open-editor` jump into the same Rules screen with the policy preloaded.
The setup export generates connector-aware recorder scaffolding for Zendesk, Salesforce, ServiceNow, internal apps, and CSV-based workflows.
For the simplest local path, `epi connect open` starts both the local review service and the browser app together, opens the browser, and leaves the workspace running in one command.
If the local review service was started with `--users-file`, the browser app shows a built-in sign-in form for `admin`, `reviewer`, and `auditor` roles.

## How it works

1. User opens one or more `.epi` files or starts with the example case
2. [JSZip](https://stuk.github.io/jszip/) reads the ZIP contents in-browser
3. `manifest.json`, `steps.jsonl`, `analysis.json`, `policy.json`, and `review.json` are parsed client-side when available
4. SHA-256 integrity checks run in the browser
5. Ed25519 verification is attempted with the bundled browser crypto verifier
6. Optional browser signing uses the pasted Ed25519 PKCS#8 private key directly in the browser
7. Reloaded case files verify `review_signature` and show a clear signed or unsigned review badge
8. Everything stays local to the browser
9. Packaged case files can open immediately from embedded `epi-data`, while `epi view` can preload archive bytes for reviewed `.epi` downloads
10. The Rules screen exports an actual `epi_policy.json` that EPI can load on future runs
11. If `epi connect serve` is running, the optional setup flow can fetch one live source record or safe sample, open it as a case preview right away, and keep it local to the browser session until you export the starter pack
12. If the shared workspace is enabled, case previews and review updates can be synced to other users on the same self-hosted workspace

## Why this viewer exists

The core EPI infrastructure is still the moat:

- trace capture
- file integrity
- signatures
- review notes
- policy evaluation

This viewer changes the interface on top of that moat so operators, compliance teams, and reviewers can use EPI without needing to think first about manifests, hashes, or CLI commands.

## Hosting

Host the repo root or `/web_viewer/` on GitHub Pages and keep `../epi_viewer_static/crypto.js` available so browser-side signature verification continues to work.
When EPI packages `viewer.html` into an artifact, the same interface is inlined for offline use.
`epi view --extract` produces that same single-file offline review surface with vendored JSZip and no remote script dependencies.
The raw repo-hosted `web_viewer/index.html` is still a source app that expects its companion static assets nearby; the single-file offline guarantee applies to the generated embedded and extracted viewer HTML, not to the raw source page by itself.
For live source-record fetches during optional setup, run `epi connect serve` locally and leave the bridge URL at `http://127.0.0.1:8765` unless your environment needs a different port.
