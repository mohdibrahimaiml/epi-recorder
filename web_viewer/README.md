# EPI Web Viewer

A pure-browser viewer for `.epi` recordings. No server, no install required.

**Live:** https://epilabs.org/viewer
*(or hosted via GitHub Pages at `/web_viewer/`)*

## How it works

1. User drops a `.epi` file onto the page
2. [JSZip](https://stuk.github.io/jszip/) reads the ZIP in-browser
3. `manifest.json` + `steps.jsonl` are parsed client-side
4. SHA-256 integrity check runs via the Web Crypto API
5. Timeline is rendered — nothing ever leaves the user's machine

## Hosting on GitHub Pages

Point your GitHub Pages source to the repo root (or `/web_viewer/`).
Add a `CNAME` file with `epilabs.org` if using a custom domain.

## Built by

Mohd Ibrahim Afridi — mohd@epilabs.org
