# Manual External-User Validation Checklist

Use this after `python scripts/validate_external_userflow.py --out-dir <path>` finishes.

The automated harness proves install, trust, AGT import, extraction, and review-save flows.
This checklist covers the remaining browser-facing checks a maintainer or reviewer should see manually.

## Local Artifact Browser Check

- Open the signed local artifact with `epi view <signed-local.epi>`.
- Confirm the browser opens, or that EPI prints a clear fallback path if auto-open is blocked.
- Confirm the embedded case view opens directly into the investigation surface.
- Confirm the rendered embedded UI does **not** show the file-drop / onboarding launcher.
- Confirm trust state is visible without digging.

## AGT Artifact Browser Check

- Open the signed AGT artifact with `epi view <signed-agt.epi>`.
- Confirm `Source system: AGT` and the import framing are visible.
- Confirm decision, policy, trust, and review state are understandable without reading raw files first.
- Confirm the AGT case still renders as a focused case view, not the generic open-local-cases launcher.

## Trust Clarity

- Run `epi verify <signed-local.epi>` and `epi verify <signed-agt.epi>`.
- Confirm the trust report is understandable to someone who did not build the artifact.
- Confirm the signed artifact says it was verified and the unsigned artifact says it is intact but unsigned.
- Confirm the tampered artifact clearly fails and does not look reviewable.

## AGT Mapping Clarity

- Open `artifacts/agt/mapping_report.json` from the extracted AGT review folder.
- Confirm it is easy to locate.
- Confirm it explains what was preserved, translated, derived, or synthesized.
- Ask: "If I were seeing this as an AGT maintainer for the first time, would I understand what EPI imported and what it changed?"

## Final Sanity Check

- Confirm the reviewed AGT artifact still verifies after `review.json` is appended.
- Confirm the extracted `viewer.html` opens offline.
- Confirm the generated `summary.md` and `summary.json` match what you observed manually.
