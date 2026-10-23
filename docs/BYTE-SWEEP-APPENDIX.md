# Byte-sweep appendix (moved out of KNOWN_LIMITATIONS.md)

**Product version:** 4.6.2. Overview first: [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md).

This is the full 1 KB byte-flip sweep that backs the short summary in KNOWN_LIMITATIONS.md ("Byte-level seal scope"). Read the summary first; come here only for the per-region table and the offset-658 evidence.

---

## Byte-level seal scope (from 1KB sweep, 4.4.0 demo-banking-aml.epi, 405612 B)

**Task:** flip one byte at every 1 KB, plus first/last byte of every ZIP member and file, then `epi verify`. Offset 658 is the example from the report.

**Map for `verify_portal/static/assets/demo/demo-banking-aml.epi` (marker at 305552, payload at 305584, 12 ZIP members):**

| Outer offset | Region (from `ZipInfo.header_offset` + `compress_size`) | In `file_manifest`? | In `payload_sha256`? | In `__polyglot_viewer__` (reserved_tail[0:32])? | `epi verify` after flip |
|---|---|---|---|---|---|
| `0` | Envelope header byte 0 (`<` of `<!--`) | — | — | — | **PASS** (not detected — header magic not strictly hashed) |
| `10` | Envelope header | — | — | — | **FAIL** (`payload_sha256` or header length) |
| `128` | HTML prelude start (outer viewer) | No | No | **Yes** | **FAIL** (`__polyglot_viewer__` mismatch) |
| `658` | **HTML prelude** (outer viewer, `viewer.html` not inner) | No | No | **Yes** | **FAIL** `integrity False {__polyglot_viewer__: expected 0c1f..., got 6c8a...}` `signature_valid True` `decision FAIL` |
| `305542` | HTML prelude near marker | No | No | Yes | **FAIL** |
| `305552` | Marker `<!-- EPI_ZIP_PAYLOAD_START -->` | No | No | No | **FAIL** (marker not hashed, but payload length changes) |
| `305584` | ZIP local header for `mimetype` | No (mimetype excluded) | **Yes** (full ZIP hash) | No | **FAIL** |
| `305622` | ZIP data `mimetype` | No | Yes | No | **FAIL** |
| `310040` | ZIP data `steps.jsonl` start | **Yes** (`steps.jsonl` in `file_manifest`) | Yes | No | **FAIL** (both) |
| `405611` | File last byte (EOCD) | — | Yes | No | **FAIL** |
| `405512` | ZIP central directory | — | Yes | No | **FAIL** |

**Summary from full 1 KB sweep (405 offsets + 26 member edges + 2 file edges = 433):**

* **HTML prelude [128, 305552)** — 298 KB of outer viewer HTML **is sealed** via `reserved_tail[0:32]` (`__polyglot_viewer__`). Flipping any byte there → `integrity False` `__polyglot_viewer__` mismatch, not `file_manifest` or `step chain`. This is the display layer, not the evidence, but it is tamper-evident since 4.4.1 (legacy all-zero tail was not).
  * **Red-team caveat (fixed):** this sweep flipped bytes one at a time. A *consistent* forgery — edit the outer HTML **and** recompute the `reserved_tail[0:32]` copy — produced **no** mismatch at all, because that copy is unsigned and self-referential. The outer region is byte-identical to the sealed `viewer.html` member, so `epi verify` now also checks it against the signed `file_manifest` entry; a consistent forgery now fails. See "Polyglot embedded viewer (display layer)" above.
* **ZIP payload [305584, 405612)** — all 12 members' headers, compressed data, central directory, and EOCD are sealed via `payload_sha256` (envelope) **and** for members listed in `file_manifest` (including inner `viewer.html` and `steps.jsonl`). Flipping any byte there → `FAIL` (either `payload_sha256` or `file_manifest` mismatch, plus `step chain` for `steps.jsonl`).
* **Envelope header [0,128)** — exhaustive 2026-08-29 XOR of every byte, then `epi verify` (4.4.1): **undetected** offsets **0–3** (magic), **16–31** (artifact UUID), **32–39** (`created_at_micros`). Detected: 4–15 (version/format/flags/length), 40–71 (`payload_sha256`), 72–103 (viewer hash), 104–127 (padding must be zero). These PASS bytes are not `spec_version` (that field is not in the 128-byte header).

**Classification for offset 658:** **Inside sealed scope** (`__polyglot_viewer__`), **correctly detected** (`FAIL` with `integrity False`, `signature_valid True`), **not a verifier bug**. Documented here as display-layer seal, not evidence-layer. If the HTML were outside scope it would be a limitation, but it is inside when `reserved_tail[0:32]` is non-zero. Artifacts with an all-zero viewer hash still skip this check (legacy warning).

**Offset 658 PASS vs FAIL contradiction:** Isolated re-run (2026-08-29) of the same `docs/assets/demo-banking-aml.epi` XOR at byte 658: **PyPI 4.4.0 and local 4.4.1 both FAIL** via `__polyglot_viewer__` (`verifier_version` 4.4.0 vs 4.4.1). Official `epi-recorder==4.4.0` wheel already contains `verify_polyglot_viewer`. 4.4.1 did not close a 4.4.0 detection hole for this offset. An earlier `rc=0 PASS` is not a version split; likely a sweep that only hashed ZIP/`file_manifest` (HTML prelude at 658 is outside those hashes) or `python -m epi_cli` from the repo cwd importing 4.4.1 sources while `pip show` said 4.4.0. The 433-offset sweep that reported FAIL used a verifier with `__polyglot_viewer__` (present in both 4.4.0 PyPI and 4.4.1).

**Evidence for offset 658 flip (literal `epi verify --json`):**
```
manifest spec_version 4.4.0
integrity False {'__polyglot_viewer__': 'polyglot viewer HTML hash mismatch: expected 0c1f41d1ef6281e7…, got 6c8a8cb340e25c1d… (display layer may have been tampered)'}
signature_valid True
decision FAIL Integrity compromised
```

---
