# EPI Forensic Artifact Viewer

`web_viewer/` is the browser-local forensic review app for portable `.epi` artifacts.
It powers both:

- the default `epi view` experience for preopened case files
- the packaged `viewer.html` embedded directly into each `.epi`

The interface is now forensic-first rather than setup-first:

- `Queue`: load multiple case files and open the case that needs attention first
- `Case`: read decision, trust, source, policy, evidence, review, mapping, and attachments in one place
- `Setup`: optional source-system configuration for safe samples, live previews, and recorder starter export
- `Rules` and `Reports`: secondary utilities once the case is understood

The loaded-case flow is designed to answer four questions quickly:

1. What happened?
2. Why did it happen?
3. Can I trust this file?
4. Do I need to act?

## Investigation model

The main case surface is organized as:

- `Overview`
- `Evidence`
- `Policy`
- `Review`
- `Mapping`
- `Trust`
- `Attachments`

This keeps native EPI recordings readable while also making imported AGT evidence feel first-class inside the same UI.

For AGT-imported artifacts, the viewer surfaces:

- `Source system: AGT`
- `Import mode: EPI`
- transformation audit from `artifacts/agt/mapping_report.json`
- preserved raw AGT payloads under attachments
- synthesized-analysis warnings when import created derived output

## What stays unchanged

The viewer redesign does not change the EPI artifact model:

- one `.epi` file
- offline/local review
- browser-side integrity checks
- browser-side signature verification when available
- optional browser signing for review notes
- packaged `viewer.html` remains self-contained when embedded or extracted

Everything stays local to the browser. The repo-hosted source app still expects its local companion assets, while packaged and extracted viewers inline what they need for offline use.

## Source and setup support

Optional setup still supports:

- safe sample preview
- local connector bridge via `epi connect serve`
- live source-record preview
- shared local workspace sync
- recorder starter export with `epi_policy.json` and recorder scaffolding

The setup flow remains secondary to the case reader so reviewers can open a saved artifact and investigate immediately.
