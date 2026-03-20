# EPI-OFFICIAL Website Improvements

This directory contains a comprehensive patch for the `mohdibrahimaiml/EPI-OFFICIAL` repository
covering **40+ fixes** across two passes: bugs, security, performance, accessibility, SEO, and UX.

## How to apply

```bash
cd /path/to/EPI-OFFICIAL
git apply /path/to/website-improvements.patch
```

## Pass 1 — Critical Bugs, Versions, Performance, SEO

### Critical Bug Fixes
- `simulation.html` — Fixed broken `js/terminal-demo.js` path (missing `js/` prefix) — page was non-functional
- `js/terminal-demo.js` — Fixed typo `'accusing'` → `'usage'` in missing-argument error message
- `js/terminal-demo.js` — Removed duplicate `history.push(cmd)` causing doubled command history entries
- `sw.js` — Fixed null-crash in service worker (`headers.get('accept')` can return `null`)

### Version Consistency
- All CSS cache-bust query strings updated `v2.2`/`v2.6` → `v=2.8` across all 9 pages
- Terminal version display updated `v2.7.2` → `v2.8.5` in `simulation.html`
- Script version query updated `v2.6.0` → `v2.8.4`

### Performance
- Added `defer` to CDN scripts in `<head>` of `verify.html` and `viewer.html` (were blocking HTML parsing)
- Added `defer` to end-of-body scripts across all pages

### Accessibility (Pass 1)
- `verify.html` modals: Added `role="dialog"`, `aria-modal="true"`, `aria-labelledby`
- Modal close buttons now have `aria-label`
- Escape key closes open modals; backdrop click closes them
- Focus moves to close button when modal opens

### SEO
- `<link rel="canonical">` added to all 9 HTML pages
- Fixed OG image paths: `cryptographic_visual.png` and `trust_network.png` were missing `assets/` prefix
- Replaced missing `epi-file-visual.png` with existing `assets/logo.png`

### Error Handling (Pass 1)
- Contact form: Detects popup blocker, falls back to `mailto:` with user-visible feedback
- `verify.html`: Detects JSZip CDN load failure and shows user-friendly error message
- `js/viewer.js`: Validates ZIP magic bytes (`PK`) before attempting to parse `.epi` file

---

## Pass 2 — Deep Bugs, Security, Accessibility, Performance

### Security
- `verify.html` — Replaced `window.open(blob)` with sandboxed iframe for embedded viewer content,
  preventing XSS from untrusted `viewer.html` inside the `.epi` archive

### CSS/HTML Structural Bugs
- `terminal.css:100` — Fix CSS variable typo `--term-gree` → `--term-green` (broke prompt color)
- `style.css` — Removed duplicate `html { scroll-behavior: smooth }` rule
- `style.css` — Merged duplicate `p {}` selectors into single canonical rule
- `index.html` — Removed extra stray `</div>` (unbalanced DOM)
- `viewer.css` — Added `:focus-visible` ring to `.tab-btn` for keyboard navigation

### JavaScript Bugs & Performance
- `particles.js` — Debounced resize handler (150ms) to prevent thrashing
- `particles.js` — Guard against zero-width parent in `resize()`
- `particles.js` — Used squared distance in `drawConnections()` to skip `Math.sqrt` in hot path
- `particles.js` — Disabled on touch/mobile devices (saves battery)
- `app.js` — Removed dead `InteractiveTerminal` DOMContentLoaded init loop
- `app.js` — Fixed CountUp: unobserve element **before** animation starts (not after)
- `app.js` — Added email regex validation before Gmail compose opens
- `terminal-demo.js` — Updated version strings `v2.7.0` → `v2.8.5`

### Accessibility (Pass 2)
- `viewer.html` — Added `role="button"`, `tabindex="0"`, `aria-label` to `#drop-zone`
- `viewer.html` — Added `aria-hidden` to decorative emojis and hidden file input
- `viewer.js` — Added keyboard handler: Enter/Space activates file picker from drop zone
- `index.html` — Added `aria-hidden` to decorative `.seal-icon` emoji
- `css/style.css` — Added `min-height: 44px` to interactive elements at mobile breakpoint (WCAG 2.1)

### UX
- `viewer.js` — Show spinner while sandboxed iframe loads; swap to iframe on `onload`; revoke blob URL
- `app.js` — Trim whitespace from contact form fields before validation
