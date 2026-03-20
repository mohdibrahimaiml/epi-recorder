# EPI-OFFICIAL Website Improvements

This directory contains a patch for the `mohdibrahimaiml/EPI-OFFICIAL` repository
with 28 fixes across bugs, performance, accessibility, SEO, and error handling.

## How to apply

```bash
cd /path/to/EPI-OFFICIAL
git apply /path/to/website-improvements.patch
```

## Changes included

### Critical Bug Fixes
- `simulation.html`: Fixed broken `terminal-demo.js` path (missing `js/` prefix) — page was non-functional
- `js/terminal-demo.js`: Fixed typo `'accusing'` → `'usage'` in missing-argument error message
- `js/terminal-demo.js`: Removed duplicate `history.push(cmd)` causing doubled command history entries
- `sw.js`: Fixed null-crash in service worker — `headers.get('accept')` can return `null`

### Version Consistency
- All CSS cache-bust query strings updated from `v2.2`/`v2.6` → `v=2.8` across all 9 pages
- Terminal version string updated from `v2.7.2` → `v2.8.5` in `simulation.html`
- `terminal-demo.js` script version query updated from `v2.6.0` → `v2.8.4`

### Performance
- Added `defer` to CDN scripts in `<head>` of `verify.html` and `viewer.html` (were blocking HTML parsing)
- Added `defer` to end-of-body scripts across all pages

### Accessibility
- `verify.html` modals: Added `role="dialog"`, `aria-modal="true"`, `aria-labelledby`
- Modal close buttons now have `aria-label`
- Escape key closes open modals
- Clicking modal backdrop closes it
- Focus is moved to close button when modal opens

### SEO
- `<link rel="canonical">` added to all 9 HTML pages
- Fixed OG image paths: `cryptographic_visual.png` and `trust_network.png` were referenced without `assets/` prefix
- Replaced missing `epi-file-visual.png` with existing `assets/logo.png` in `index.html` OG tags

### Error Handling
- Contact form (`js/app.js`): Detects popup blocker, falls back to `mailto:` with user-visible feedback
- `verify.html`: Detects JSZip CDN load failure and shows a user-friendly error message instead of crashing
- `js/viewer.js`: Validates ZIP magic bytes (`PK` header) before attempting to parse `.epi` file
