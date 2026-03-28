# EPI-OFFICIAL Viewer Bundle

This folder is a copy-ready bundle for hosting the EPI Decision Ops app from your website repo.

## What to copy into `EPI-OFFICIAL`

- `viewer/index.html`
- `viewer/app.js`
- `viewer/styles.css`
- `viewer/crypto.js`

After copying, the EPI app will be available at:

- `https://epilabs.org/viewer/`

or, if your site uses a different base path:

- `https://epilabs.org/viewer/index.html`

## Important

- This bundle is safe to host publicly as a static frontend.
- Do not expose the raw connector bridge publicly without auth.
- The live bridge should stay local, customer-hosted, or protected behind authentication.

## Deployment options

### Option 1: Your website repo already deploys Pages

If `EPI-OFFICIAL` already deploys `epilabs.org`, just copy the `viewer/` folder into that repo and add a link from the main site to `/viewer/`.

### Option 2: You want a Pages workflow example

Use `.github/workflows/deploy-viewer-subpath-example.yml` as a reference.

Only use that workflow if it matches how `EPI-OFFICIAL` already deploys. If your site already has a Pages workflow, merge the `viewer/` folder into the existing deployment instead of running two competing Pages deploy workflows.
