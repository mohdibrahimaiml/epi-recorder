# EPI Decision Ops Web Viewer

`web_viewer/` is the browser-only Decision Ops dashboard for local `.epi` case files.
It now powers both:

- the default `epi view` experience for preopened case files
- the packaged `viewer.html` baked directly into each `.epi` artifact

It turns EPI into a much simpler workflow for non-technical reviewers:

- one-click example case: open a ready-made case immediately so first-time users can explore the review flow without importing files first
- `Setup Wizard`: choose the system and workflow first, then let EPI prepare a starter rulebook before any `.epi` files are loaded
- safe sample preview: if real connector credentials are not ready yet, EPI can open a realistic local bridge sample so the workflow is still testable end to end
- saved connector setup: keep connector fields stored only in this browser on this device, while secret keys stay only in the current session
- local connector bridge: point the Setup Wizard at `epi connect serve`, check the bridge, and fetch a live source record without leaving the browser flow
- live record case preview: when a bridge fetch succeeds, EPI now opens that real source record as a reviewable case immediately instead of leaving it hidden in setup
- shared team workspace: when multiple people use the same self-hosted bridge, case previews and review updates can be synced through the bridge instead of staying single-user only
- optional local sign-in: a self-hosted gateway can use either one shared bearer token or a small local users file, and the browser keeps session tokens only in the current tab
- recorder starter export: download a zip with `epi_policy.json`, a real `epi_recorder` starter script, system-specific connector helpers, sample input, and a run guide
- live source record export: when a bridge fetch succeeds, the starter pack also carries `live_source_record.json` so the first run can start with real business context
- `Inbox`: load multiple case files and see what needs attention first
- `Case`: open a decision case file, review trust, findings, timeline, and download a reviewed `.epi`
- guided next steps: each case now tells the reviewer what matters most and which action to take next
- optional browser signing: paste the same EPI Ed25519 `.key` private key the CLI generates to produce a signed `review.json`
- signed review status: reloaded reviewed artifacts show whether the attached review is signed, unsigned, or has a bad signature
- packaged artifact rebuild: the baked `viewer.html` can rebuild a reviewed `.epi` offline from embedded `epi-data`
- `Rules`: load the sealed `policy.json`, edit real EPI rule types in plain language, and export a valid `epi_policy.json`
- `Reports`: export a summary, review, or trust report without using the CLI

The starter rule families in this editor are aligned with `epi policy init --starter-rule ...`, so the browser and CLI now generate the same custom starter shapes.
`epi policy init --open-editor` and `epi policy show --open-editor` now jump straight into this same Rules screen with the policy preloaded.
The setup export now generates connector-aware recorder scaffolding for Zendesk, Salesforce, ServiceNow, internal apps, and CSV-based workflows.
The same Setup Wizard can also call a self-hosted local bridge from `epi connect serve`, which lets the browser fetch a real source record and bundle it into the starter pack.
For the simplest local path, `epi connect open` now starts both the bridge and the local web app together, opens the browser, and leaves the workspace running in one command.
If the gateway was started with `--users-file`, the browser app shows a built-in sign-in form for `admin`, `reviewer`, and `auditor` roles.

## How it works

1. User drops one or more `.epi` files onto the page
2. [JSZip](https://stuk.github.io/jszip/) reads the ZIP contents in-browser
3. `manifest.json`, `steps.jsonl`, `analysis.json`, `policy.json`, and `review.json` are parsed client-side when available
4. SHA-256 integrity checks run in the browser
5. Ed25519 verification is attempted with the bundled browser crypto verifier
6. Optional review signing uses the pasted Ed25519 PKCS#8 private key directly in the browser
7. Reloaded artifacts verify `review_signature` and show a clear signed or unsigned review badge
8. Everything stays local to the browser
9. Packaged artifacts can open immediately from embedded `epi-data`, while `epi view` can preload archive bytes for reviewed `.epi` downloads
10. The Rules screen exports an actual `epi_policy.json` that EPI can load on future runs
11. If `epi connect serve` is running, the Setup Wizard can fetch one live source record or safe sample, open it as a case preview right away, and keep it local to the browser session until you export the starter pack
12. If the bridge shared workspace is enabled, case previews and review updates can be synced to other users on the same self-hosted workspace

## Why this viewer exists

The core EPI infrastructure is still the moat:

- trace capture
- file integrity
- signatures
- review records
- policy evaluation

This viewer changes the interface on top of that moat so operators, compliance teams, and reviewers can use EPI without needing to think in terms of manifests, hashes, or CLI commands.

## Hosting

Host the repo root or `/web_viewer/` on GitHub Pages and keep `../epi_viewer_static/crypto.js` available so browser-side signature verification continues to work.
When EPI packages `viewer.html` into an artifact, the same interface is inlined for offline use.
For live source-record fetches during setup, run `epi connect serve` locally and leave the bridge URL at `http://127.0.0.1:8765` unless your environment needs a different port.
