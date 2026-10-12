# EPI Auditor's Guide — Independent Verification of .epi Evidence

**Version:** 2.0 (epi-recorder 4.6.0) | **Last updated:** 2026-10-12

For banks, insurers, auditors and other reviewers who receive a `.epi` file
from a vendor and need to check it themselves, offline, without trusting
the vendor's word.

**Docs map:** [README.md](./README.md) · **Verdict semantics:** [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md) · **Witness log:** [WITNESS.md](./WITNESS.md)

---

## The one command

```bash
pip install epi-recorder
epi verify case.epi --policy strict --witness-log received.jsonl
```

Add `--require-timestamp` **only if** your vendor seals with a reachable
RFC 3161 timestamp service (ask them). Without one, every file fails that
requirement even when the seal is intact.

```bash
epi verify case.epi --policy strict --witness-log received.jsonl --require-timestamp
```

What each part does:

| Part | Why |
|------|-----|
| `--policy strict` | FAILs unless the file was sealed by a key **you** pinned, and FAILs on incomplete evidence (e.g. a tool call with no recorded result). The default (`standard`) only WARNs on both, and anyone can make a valid-looking seal with a fresh key. |
| `--witness-log received.jsonl` | Checks the file against the seal reports the vendor's system sent to **your** server at seal time. Run the receiver with `epi witness serve --out received.jsonl` (installed with the package); see [WITNESS.md](./WITNESS.md). Leave the flag out if you do not run a witness receiver. |
| `--require-timestamp` | FAILs unless an independent timestamp (RFC 3161) in the file validates offline. |
| `--offline` | Optional: no network at all (skips DID resolution and remote fetches; your local pins still apply). |

Exit code: `1` on FAIL, `0` on PASS **and on WARN**. Scripts must rely on
the exit code **with `--policy strict`**: under the default policy an
unpinned sealer, a seal missing from your witness log, or incomplete
evidence is only a WARN and exits `0`. For a written
record, add `--report verification_report.txt`. For machine-readable output,
add `--json`.

Before this command can PASS, you must pin the vendor's key once
(next section).

---

## Pin the vendor's key (once per vendor)

Pinning is what turns "someone sealed this" into "**our vendor** sealed this".

### Online: from the vendor's did:web

The vendor publishes their key at `https://vendor.com/.well-known/did.json`
(they generate it with `epi keys did --domain vendor.com`). You run:

```bash
epi keys trust --from-did did:web:vendor.com --name vendor
```

Real output (resolved from a test `did.json`; paths shortened):

```text
[OK] Trusted key from did:web:vendor.example.com:
/home/auditor/.epi/trusted_keys/vendor-did.pub
  Fingerprint (confirm with the vendor): <fingerprint>
Files sealed by any other key now report NOT A KEY YOU TRUST. For key rotation, pin each key in the
vendor did.json.
```

Confirm the printed fingerprint with the vendor by phone or another channel
you already trust. A website can be compromised; a phone call to a known
number is a second, independent channel.

### Offline: from a file the vendor gives you

Get one of these from the vendor out of band (signed email, a meeting, a
USB stick), then pin it with `epi keys trust <file> --name vendor`. No
network is used.

- **Their `did.json` file** (the same file they host for did:web; they
  create it with `epi keys did --domain vendor.com`):

  ```bash
  epi keys trust did.json --name vendor
  ```

- **The base64 key printed by `epi keys export`.** The vendor runs
  `epi keys export` and sends you the key line; save that single line to a
  file and pin it:

  ```text
  $ epi keys export          # on the vendor's machine
  Public key for 'default': (base64-encoded Ed25519 raw public key, 32 bytes)
  w5mhgILRaU7w3GUaPmqnr++J+hSLEj4bA0fPu1hhpdI=
  Fingerprint: 5a32 47ae cc11 f185  (customers see this in epi verify; confirm it with them by phone)
  ```

  ```bash
  echo 'w5mhgILRaU7w3GUaPmqnr++J+hSLEj4bA0fPu1hhpdI=' > vendor.b64
  epi keys trust vendor.b64 --name vendor
  ```

- **Their PEM public key file** (`~/.epi/keys/default.pub` on the vendor's
  machine, starting `-----BEGIN PUBLIC KEY-----`):

  ```bash
  epi keys trust vendor.pub --name vendor
  ```

Each prints the fingerprint:

```text
[OK] Trusted key: /home/auditor/.epi/trusted_keys/vendor.pub
  Fingerprint: 5a32 47ae cc11 f185  (read it to the sender by phone; it must match theirs)
```

Read that fingerprint to the vendor over the phone; it must match the one
they see (`epi keys export`, `epi keys list`, or the **Fingerprint** line
when they verify one of their own files). `epi keys list` shows every pin
with its fingerprint and status.

Pins live in `~/.epi/trusted_keys/`. Once you have pinned any key, files
sealed by a different key show `✘ FAIL — NOT A KEY YOU TRUST` under the
default policy as well as under `--policy strict`.

Never pin a key just because a file you are checking was sealed with it.
The key must come from the vendor through a channel you already trust.

### Revoking a key

`epi keys revoke vendor` marks the pinned key as revoked (for example, the
vendor reports it compromised or retired). Revocation applies to the **key**,
so every pin holding that key shows `revoked` in `epi keys list`, and files
it sealed FAIL with `Status: REVOKED` under the default and strict policies. `epi keys unrevoke vendor` undoes it.

---

## Reading the verdict

The first line of the report (the panel title) is the verdict. These are
all of them, with real samples below.

| Headline | Decision | What it means | What to do |
|----------|----------|---------------|------------|
| `✔ SEAL · IDENTITY PINNED` | PASS | Contents unchanged since sealing, signature valid, **and** sealed by a key you pinned. | Accept (subject to your own review of the content). |
| `✔ PASS` | PASS | Passed the selected policy without a pinned identity. Seen with `--policy permissive` (integrity only). | Not enough for a claim or audit. Re-run with `--policy strict`. |
| `⚠ LOCAL SEALER · NOT ORG-PINNED` | WARN | Seal valid and the key is on **this** computer, but it is not pinned. Normal on the vendor's own machine. | If you are the auditor and see this, you are on the sealing machine; verify on your own. |
| `⚠ UNVERIFIED IDENTITY` | WARN | Seal valid, sealer unknown. Anyone can produce this with a fresh key. | Pin the vendor key, then re-run with `--policy strict`. |
| `⚠ NOT IN YOUR WITNESS LOG · SIGNER PINNED` | WARN | Seal valid and sealed by the pinned vendor key, but the vendor never reported this seal to your witness log. This is what a re-run or re-sealed case looks like. | Ask for the copy that is in your witness log. |
| `⚠ SIGNER PINNED · SEE WARNING` | WARN | Pinned signer, but something else needs a look (e.g. a clock warning). `Reason:` says what. | Read the reason. |
| `✘ SEAL FAIL — FILE ALTERED` | FAIL | A sealed file inside the `.epi` changed after sealing (hash or `prev_hash` chain mismatch). | Reject. Ask the vendor for the original. Keep the altered file. |
| `✘ SEAL FAIL — SIGNATURE INVALID` | FAIL | The manifest was edited after signing, or the signature is corrupt. | Reject. Ask the vendor for the original. |
| `✘ FAIL — NOT A KEY YOU TRUST` | FAIL | The seal is valid but was made by a key other than the one(s) you pinned. | Reject unless the vendor explains (e.g. key rotation) **and** you pin the new key after confirming it. |
| `✘ FAIL — SEAL INTACT, REQUIREMENT NOT MET` | FAIL | Contents and signature are fine, but a requirement you asked for is not met: an unpinned sealer under `--policy strict`, no valid timestamp under `--require-timestamp`, or incomplete evidence under `--policy strict`. The `Reason:` line says which. | Pin the key (out of band), ask the vendor why the file carries no valid timestamp, or see "Evidence incomplete" below. |
| `✘ FAIL — SEAL INTACT, REQUIREMENT NOT MET` with IDENTITY `Status: REVOKED` | FAIL | Contents and signature are fine, but the sealing key is one you revoked (`epi keys revoke`). | Reject unless you revoked by mistake; undo with `epi keys unrevoke <name>`. |

Below the headline, read three blocks:

- **DECISION** — `PASS`, `WARN` or `FAIL`, the policy used, and a one-line `Reason:`.
- **IDENTITY** — `Status:` is `KNOWN` (pinned), `LOCAL` (key on this computer),
  `NOT_PINNED` (unknown sealer), or `NOT A KEY YOU TRUST (you have pinned: …)`.
  The **Fingerprint** line identifies the sealing key.
- **SEAL** — `Integrity`, `Signature`, `Forensic` (step chain and
  completeness), `Timestamp`, and `Witness` (only with `--witness-log`).

The IDENTITY `Status:` can also be `REVOKED` (a key you revoked).

### Evidence incomplete

`Forensic: FAIL — tool.call at step 2 is missing a corresponding tool.response`
(or a similar gap) means the sealed record is internally unfinished: a tool
call with no recorded result, an LLM request with no response. The seal can
still be intact. Under the default policy this gives **WARN**; under
`--policy strict` it is **FAIL** with
`Reason: Evidence incomplete (Strict Policy requires full telemetry coverage)`.
Ask the vendor why the run's evidence is incomplete (a crash, a timeout, or a
capture path that logs calls but not results).

### Witness line (with `--witness-log`)

| Line | Meaning |
|------|---------|
| `Witness: WITNESSED (received <time>)` | The sealed contents match a report the vendor's system sent you at seal time. A file re-packaged later (e.g. by `epi-register`) still matches. Shown in green only when the file's integrity also passed. |
| `Witness: a report for this case exists …, but THIS file was altered` | You were told about this case, but this file is not what was reported. Verification FAILs on integrity. |
| `Witness: NOT IN WITNESS LOG — never reported to you at seal time` | You were never sent a report for this seal. A PASS becomes WARN (`⚠ NOT IN YOUR WITNESS LOG`), and FAIL (exit 1) under `--policy strict`. For a case you know happened, ask the vendor why. |
| `Witness: NOT CHECKED — witness log … could not be read` | The `--witness-log` path is wrong or unreadable. Verification FAILs so a typo never skips the check. |
| `Witness: DIFFERENT VERSION — …` | You were told about this case (same workflow id), but not about this copy: a re-signed copy or an unreported gateway re-export. Headline `✘ FAIL — NOT THE VERSION REPORTED TO YOU`. Ask for the reported copy. |

A vendor re-running a case produces a new, separately witnessed seal. Look
for more than one log entry for the same case; see [WITNESS.md](./WITNESS.md).

---

## Real samples

Generated with epi-recorder 4.6.0. A small script sealed `case-001.epi` with
the vendor's key; the auditor pinned `vendor.pub`. Output trimmed to the
header and the relevant lines; fingerprints shown as `<fingerprint>`.

**Pinned vendor, strict policy, witnessed** (`exit 0`):

```text
╭──────────────────────── ✔ SEAL · IDENTITY PINNED EPI Verification Report ────────────────────────╮
│ DECISION: PASS                                                                                   │
│ Policy: strict                                                                                   │
│ Reason: All strict criteria met (Integrity, Identity, Completeness)                              │
│                                                                                                  │
│ IDENTITY (who sealed — required for claim trust)                                                 │
│   - Status:       KNOWN                                                                          │
│   - Name:         vendor                                                                         │
│   - Fingerprint:  <fingerprint>                                                                  │
│   - Detail:       Verified via local trusted registry                                            │
│                                                                                                  │
│ SEAL (Objective Proofs — not identity)                                                           │
│   - Integrity:    Verified                                                                       │
│   - Signature:    Valid                                                                          │
│   - Forensic:     PASS                                                                           │
│   - Timestamp:  none                                                                             │
│   - Witness:      WITNESSED (received 2026-10-12T09:34:55.487339+00:00)                          │
```

**Same file, auditor has not pinned anything, default policy** (`exit 0`, WARN):

```text
╭───────────────────────── ⚠ UNVERIFIED IDENTITY EPI Verification Report ──────────────────────────╮
│ DECISION: WARN  — UNVERIFIED IDENTITY (seal valid · signer unknown)                              │
│ Policy: standard                                                                                 │
│ Reason: Unverified identity — signature valid but signer not pinned in any trusted registry.     │
│ Anyone can generate a key and re-sign a rebuilt chain. ...                                       │
│   - Status:       NOT_PINNED                                                                     │
```

**Not pinned, `--policy strict`** (`exit 1`):

```text
╭─────────────── ✘ FAIL — SEAL INTACT, REQUIREMENT NOT MET EPI Verification Report ────────────────╮
│ DECISION: FAIL                                                                                   │
│ Policy: strict                                                                                   │
│ Reason: Identity unknown or revoked (Strict Policy requires trusted signer; LOCAL self-match is  │
│ not enough — pin the sender's key obtained from them directly, then confirm its fingerprint by   │
│ phone)                                                                                           │
│   - Status:       NOT_PINNED                                                                     │
```

**Pinned, but `--require-timestamp` and the file has no timestamp** (`exit 1`):

```text
╭─────────────── ✘ FAIL — SEAL INTACT, REQUIREMENT NOT MET EPI Verification Report ────────────────╮
│ DECISION: FAIL                                                                                   │
│ Policy: strict                                                                                   │
│ Reason: No valid seal-time timestamp (--require-timestamp). The seal itself is intact.           │
```

**Sealed by a second key while `vendor` is pinned** (`exit 1`, under the
default and strict policies; `--policy permissive` ignores identity and PASSes):

```text
╭────────────────────── ✘ FAIL — NOT A KEY YOU TRUST EPI Verification Report ──────────────────────╮
│ DECISION: FAIL                                                                                   │
│ Policy: strict                                                                                   │
│   - Status:       NOT A KEY YOU TRUST (you have pinned: vendor)                                  │
│   - Trust:        This file was not sealed by a key you trust.                                   │
│   - Integrity:    Verified                                                                       │
│   - Signature:    Valid                                                                          │
```

**Tampered: unzipped, one value in `steps.jsonl` edited, re-zipped** (`exit 1`):

```text
╭─────────────────────── ✘ SEAL FAIL — FILE ALTERED EPI Verification Report ───────────────────────╮
│ DECISION: FAIL                                                                                   │
│ Policy: strict                                                                                   │
│ Reason: Integrity compromised (file tampering detected)                                          │
│   - Integrity:    FAILED                                                                         │
│   - Signature:    Valid                                                                          │
│   - Forensic:     FAIL — step 3: prev_hash mismatch                                              │
│   - Chain:        BROKEN (prev_hash mismatch)                                                    │
```

**Pinned key later revoked, `--policy strict`** (`exit 1`):

```text
╭───── ✘ FAIL — SEAL INTACT, REQUIREMENT NOT MET EPI Verification Report ──────╮
│ DECISION: FAIL                                                               │
│ Policy: strict                                                               │
│   - Status:       REVOKED                                                    │
│   - Name:         vendor                                                     │
│   - Detail:       REVOKED: This key has been explicitly compromised or       │
│ retired.                                                                     │
```

**A `tool.call` with no `tool.response`, `--policy strict`** (`exit 1`):

```text
╭───── ✘ FAIL — SEAL INTACT, REQUIREMENT NOT MET EPI Verification Report ──────╮
│ DECISION: FAIL                                                               │
│ Policy: strict                                                               │
│ Reason: Evidence incomplete (Strict Policy requires full telemetry coverage) │
│   - Forensic:     FAIL — tool.call at step 2 is missing a corresponding      │
│ tool.response                                                                │
```

**Manifest edited after signing (the `goal` field changed)** (`exit 1`):

```text
╭──────────────────── ✘ SEAL FAIL — SIGNATURE INVALID EPI Verification Report ─────────────────────╮
│ DECISION: FAIL                                                                                   │
│ Policy: strict                                                                                   │
│ Reason: Invalid signature                                                                        │
│   - Integrity:    Verified                                                                       │
│   - Signature:    INVALID                                                                        │
```

With `--witness-log`, the same edited manifest also shows
`Witness: DIFFERENT VERSION — a different version of this case (same workflow id) was reported to you …`.

**Permissive policy (integrity only)** (`exit 0`, not claim-ready):

```text
╭───────────────────────────────── ✔ PASS EPI Verification Report ─────────────────────────────────╮
│ DECISION: PASS                                                                                   │
│ Policy: permissive                                                                               │
│ Reason: Integrity verified (Permissive Policy)                                                   │
```

**On the vendor's own machine, default policy:**

```text
╭──────────────────── ⚠ LOCAL SEALER · NOT ORG-PINNED EPI Verification Report ─────────────────────╮
│ DECISION: WARN  — LOCAL SEALER (seal valid · not org-pinned)                                     │
│   - Status:       LOCAL                                                                          │
│   - Local key:    default (matches this computer — not org pin)                                  │
```

---

## Browser check (no install)

At https://epilabs.org/verify/ :

| Mode | What happens to the file | Use when |
|------|---------------------------|----------|
| **Private check** (default) | Read **in the browser tab only**, not uploaded | Quick look, sensitive evidence |
| **Full report** (`?mode=server`) | **Uploaded** to EPI for a hosted report | Your organization accepts upload |

The browser check covers file hashes and the signature only. It does not
check pins, the step chain, timestamps or the witness log, and it never
shows a stronger result than the CLI. For acceptance decisions, use the
CLI command above.

---

## What a PASS does and does not prove

- **Proves:** the files in the `.epi` are exactly what the holder of the
  pinned key sealed; with `--require-timestamp`, they existed no later than
  the timestamp; with `--witness-log`, you were told about this seal when it
  happened.
- **Does not prove:** that the vendor recorded everything, that the agent
  behaved correctly, or compliance with any regulation. The SEAL block's
  `Known gaps:` lines list what the capture path does not see.

---

## If verification fails

1. Keep the file exactly as received. Record its SHA-256 (`sha256sum case.epi`).
2. Save the output: `epi verify case.epi --policy strict --witness-log received.jsonl --report verification_report.txt`.
3. Ask the vendor for the original file and an explanation, quoting the headline and `Reason:` line.
4. For `NOT A KEY YOU TRUST`, do not pin the new key until you have confirmed it with the vendor by an independent channel.

---

## Looking inside a file

An `.epi` is an HTML+ZIP file: a browser-viewable HTML page with the ZIP
archive after it. Plain `unzip` therefore warns, and exits non-zero, even on
a good file:

```text
warning [case.epi]:  326022 extra bytes at beginning or within zipfile
  (attempting to process anyway)
```

That is expected and not a sign of tampering. To extract cleanly use either
of:

```bash
epi view case.epi --extract case_dir      # extracts the contents and viewer.html
python -m zipfile -e case.epi case_dir
```

Extracting does not verify anything; `epi verify` on the original file is
the check.

## Going further

```bash
epi view case.epi          # open the timeline in a browser (offline); exits 1 on an altered file
epi analyze case.epi       # fault / policy summary sealed in the file
epi verify case.epi --verbose --aiuc1   # evidence grouped by AIUC-1 domain (not a certification)
```

To map evidence to EU AI Act articles, see
[EU-AI-ACT-COMPLIANCE-MATRIX.md](./EU-AI-ACT-COMPLIANCE-MATRIX.md). Whether
evidence meets a regulatory threshold is for you to decide.

## Glossary

| Term | Meaning |
|------|---------|
| **.epi** | Portable evidence file: an HTML+ZIP container holding the sealed record |
| **Seal** | SHA-256 hashes of every sealed file plus an Ed25519 signature over the manifest |
| **Pin** | A vendor public key you trust, stored in `~/.epi/trusted_keys/` |
| **Fingerprint** | Short identifier of a signing key; confirm it with the vendor out of band |
| **Witness log** | `received.jsonl` on your server: hash-only reports the vendor's system sent at seal time |
| **RFC 3161 timestamp** | Independent third-party proof that the contents existed no later than a given time |
| **prev_hash** | Each step's link to the previous step; any edit breaks the chain |
