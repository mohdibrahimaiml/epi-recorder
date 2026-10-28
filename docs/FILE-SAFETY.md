# File safety — is a `.epi` file safe to open?

**Product version:** 4.7.0. Docs map: [README.md](./README.md).

This page answers one question a bank, hospital, or insurer asks before it
lets a vendor's evidence file through the email gateway: **"Is this `.epi`
file malicious, and is it safe to open?"** It says what is inside the file,
proves the embedded viewer makes no network calls, explains how to verify a
file **without** opening it, and is honest about the parts that are not yet
hardened.

Related: [THREAT_MODEL.md](./THREAT_MODEL.md) (attacks), [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md)
(what a verdict means), [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md) (boundaries).

---

## 1. What is inside a `.epi` file

A sealed `.epi` (container `envelope-v2`) is a **polyglot**: the same bytes are
a valid HTML page *and* a binary envelope carrying a ZIP. This is deliberate —
it lets a reviewer double-click the file and see the run in a browser with
nothing installed. The layout is:

```
[ 128-byte binary header ]  magic "<!--", version, payload length,
                            artifact UUID, created_at, payload SHA-256,
                            SHA-256 of the outer viewer HTML
[ outer viewer HTML      ]  self-contained forensic UI (inlined CSS/JS)
[ marker                 ]  "<!-- EPI_ZIP_PAYLOAD_START -->"
[ ZIP payload            ]  the sealed evidence
```

The ZIP payload of a real 4.6.3 seal contains (names vary with options; the
[spec](./spec/EPI-SPEC.md) is the contract):

```
mimetype
manifest.json            ← signed: file_manifest (SHA-256 per member), goal,
                            created_at, public key, Ed25519 signature
steps.jsonl              ← the run timeline (hash-chained)
environment.json
policy.json / policy_evaluation.json / epi_policy.json   (when policy ran)
analysis.json            (when fault analysis ran)
viewer.html              ← the same offline UI, inside the archive
VERIFY.txt               ← plain-text "how to check this file" instructions
artifacts/manifest.json
artifacts/notarization/notarization.json
artifacts/notarization/tsa_reply.tsr, tsa_reply_1.tsr   (RFC 3161 timestamps)
```

There is **no executable, no installer, no macro, no native binary** in the
payload. The only thing that "runs" is the viewer's JavaScript, in your
browser's sandbox, when (and only when) you open the file in a browser.

> **Note for email/DLP filters.** HTML + JavaScript + a ZIP in one attachment
> is exactly the shape that HTML-smuggling filters flag. That is a *shape*
> match, not a behaviour match: the sections below show the embedded viewer
> loads nothing external and calls nothing over the network, and the file can
> be verified without ever rendering its HTML. If your gateway still blocks the
> polyglot, ask the sender for the **data-only** form (§6).

---

## 2. The embedded viewer makes no network calls (evidence)

We scanned a sealed **4.6.3** artifact — `docs/assets/demo-banking-aml.epi`
(SHA-256 `bc8e900bbe508a1662bb85cb8e8a7107fc6044dab710d8c08703327af2b1c0a8`) —
for any way the viewer could reach out. Both the **outer** polyglot HTML and
the **inner** `viewer.html` were checked.

| Check | Outer viewer | Inner `viewer.html` |
|-------|:---:|:---:|
| External `<script src=…>` | 0 | 0 |
| External `<link href="http…">` | 0 | 0 |
| `fetch(` | 0 | 0 |
| `XMLHttpRequest` | 0 | 0 |
| `WebSocket` | 0 | 0 |
| `EventSource` | 0 | 0 |
| Dynamic `import(` | 0 | 0 |
| `navigator.sendBeacon` | 0 | 0 |

Every library the viewer needs — JSZip, pako (inflate), and the `noble`
Ed25519/SHA-256 code — is **inlined** at seal time. The only `http(s)://`
strings anywhere in the viewer are:

- **TSA endpoint URLs** (`freetsa.org`, `timestamp.digicert.com`) inside the
  *notarization metadata* — recorded data that names which timestamp service
  issued a token. The viewer **displays** these; it never fetches them.
- **License/doc URLs** in the bundled JSZip and pako source comments
  (`stuartk.com/jszip`, `raw.github.com/Stuk/jszip/main/LICENSE.markdown`,
  `stuk.github.io/jszip/documentation/...`, `github.com/nodeca/pako/...`) —
  inert text.

Reproduce it yourself (no EPI install needed):

```python
import io, re, zipfile, pathlib
data = pathlib.Path("docs/assets/demo-banking-aml.epi").read_bytes()
idx = data.find(b"PK\x03\x04")          # start of the ZIP payload
outer, zf = data[:idx], zipfile.ZipFile(io.BytesIO(data[idx:]))
inner = zf.read("viewer.html")
net = rb"<script[^>]+src=|\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|\bimport\s*\("
for name, blob in (("outer", outer), ("inner", inner)):
    print(name, "network primitives:", len(re.findall(net, blob)))
```

Both print `0`. Offline integrity/signature verification needs no network
either — `epi verify` (§3) runs entirely on the local bytes.

---

## 3. Verify a file **without** opening it

You never have to render a `.epi` to check it. The authoritative check is the
CLI, which reads the ZIP and recomputes hashes and the Ed25519 signature — it
does **not** execute the file's HTML or JavaScript:

```bash
pip install epi-recorder
epi verify case.epi                       # human-readable report
epi verify case.epi --json                # machine-readable
epi verify case.epi --policy strict       # FAIL on unknown sealer / any gap
epi verify case.epi --policy strict --witness-log received.jsonl   # + independent witness
```

`--policy strict` is the claim-ready mode: it FAILs unknown/unpinned sealers,
unsigned artifacts, integrity failures, truncated payloads, and incomplete
evidence. Rely on the **exit code** only with `--policy strict` (a WARN exits
`0`). Identity (KNOWN vs UNKNOWN) is separate from integrity — pin the sender's
public key out of band first (`epi keys trust …`, [IDENTITY-ONBOARDING.md](./IDENTITY-ONBOARDING.md)).
Full semantics: [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md). Auditor
walkthrough: [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md).

A hosted browser check is available at `https://epilabs.org/verify` for a
reviewer with no install, and it runs device-local (no upload on the default
path). It is a convenience — **the CLI is authoritative**, and the browser
check never ranks above it for the same bytes.

---

## 4. Never trust the in-file viewer's verdict — trust `epi verify`

This is the single most important rule for a receiver.

The "VERIFIED / PASS" colours you see when you double-click a `.epi` are
painted by HTML and JavaScript **that live inside the file itself**. An
attacker can craft a file whose viewer *says* "VERIFIED" regardless of the
truth. So:

- **The verdict chrome inside the file is not proof.** The colours are a
  convenience preview. `epi verify` (or the hosted verifier, where *you* chose
  the file) is the check.
- Genuine **4.6.3** files bind the outer viewer to the **signed**
  `file_manifest` entry (`viewer.html`), so editing the display layer makes
  `epi verify` FAIL. Pre-4.6.2 files stored only an unsigned copy in the
  envelope header (`reserved_tail[0:32]`); an attacker could edit the viewer and
  recompute that copy, and 4.6.2 still reported PASS. The 4.6.3 verifier checks
  the signed value for legacy files whose manifest lists `viewer.html` and
  reports when no signed binding exists.
- **Legacy** artifacts with an all-zero viewer hash **and no signed
  `viewer.html` manifest entry** do **not** seal the display layer — for those,
  the double-click UI is forgeable. Trust `epi verify`, not the colours. (See
  [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md), "Polyglot embedded viewer".)
- A wholly **fabricated** file is a different problem: anyone can build an
  HTML page that looks like an EPI viewer. It will not carry a valid signature
  from a key you pinned, which is why identity pinning (§3) matters.

Every sealed file ships a `VERIFY.txt` that says the same thing in plain text:
*"Trust `epi verify` … not the colors or labels painted by the double-click
embedded HTML viewer alone."*

---

## 5. What is **not** hardened yet (honest gaps)

Two receiver-side items are documented, not yet fixed. Both are tracked in
**[issue #153](https://github.com/mohdibrahimaiml/epi-recorder/issues/153)**:

1. **No Content-Security-Policy.** The viewer has no CSP `<meta>` tag. The scan
   in §2 shows the *shipped code* makes no network calls, but nothing
   *enforces* that in the browser. A CSP such as
   `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:`
   would make "no network" a browser guarantee and contain any future rendering
   bug. (It is not a complete XSS fix — `'unsafe-inline'` scripts are required
   because the viewer is inlined.) Until it ships, treat §2 as a property of the
   code, not a browser-enforced invariant.
2. **Viewer rendering has not had an adversarial security review.** The shipped
   viewer HTML-escapes recorded content in text positions and embeds sealed JSON
   script-safely, but no independent penetration test backs that. Open files from
   **untrusted** senders with the same caution you would give any HTML
   attachment: verify with the CLI first, or use the data-only form (§6).

See [THREAT_MODEL.md](./THREAT_MODEL.md) → "Receiver-side threats" for the full
receiver model (malicious file, viewer XSS, ZIP bomb, browser key storage).

---

## 6. Browser "Sign & seal" stores its key in the browser (know this)

The viewer can **sign and seal a review in the browser** (`Sign & seal`). Where
that signing key lives is important for a security reviewer:

- **Default path:** the viewer generates a 32-byte Ed25519 seed **in the
  browser** and stores it as plain-text hex in **`localStorage`** under the key
  `epi.viewer.signingSeed.v1`. It is never written into the `.epi` artifact.
- **Import path:** you may paste an **unencrypted** PKCS#8 private key (PEM from
  `epi keys generate`). Encrypted PEMs are rejected. The pasted key stays in
  browser memory.

**Risk.** `localStorage` is not encrypted. In Chromium-based browsers, pages
opened from `file://` share a single `localStorage` area, so **another local
HTML file you open in the same profile can read the seed** (Firefox instead
scopes `file://` storage per-directory, but does not encrypt it either). Malware
with access to the browser profile can read it directly regardless of browser. A
browser-generated or pasted signing identity is therefore **low-assurance**
compared with a CLI key.

**Recommendation.** For real evidence, seal with CLI keys — `epi keys generate`
stores them under `~/.epi/keys/` with filesystem permissions, and
`epi record` signs from there on pack. Treat browser Sign & seal as a convenience
for demos and first looks. Hardening the browser seed (non-extractable WebCrypto
keys, or session-only, or passphrase-wrapped) is tracked in
**[issue #153](https://github.com/mohdibrahimaiml/epi-recorder/issues/153)**.

> The private key never goes **into** the artifact: the signing code embeds only
> the **public** key, and automated tests scan artifact bytes for private-key
> material. The gap above is about where the key rests *in the browser*, not
> about leaking it into the file.

---

## 7. Data-only by default (no clickable HTML shell)

New evidence is **data-only by default**. `record()`, `epi demo`, `epi run` and
`epi record` seal a plain ZIP with **no** `viewer.html` member and **no** outer
polyglot HTML — typically ~17 KB for a short run, small enough to email. There is
no web page to render on double-click and no display layer to forge. `epi verify`
and `epi view` behave exactly as for the polyglot: verify proves the seal;
`epi view` regenerates the viewer locally and opens it.

Opt back into the self-opening polyglot shell (larger — it bundles the viewer)
with `--with-viewer` / `record(..., with_viewer=True)`.

To strip the outer HTML shell from an **existing** polyglot (e.g. one a vendor
sent you), convert the container:

```bash
# Pure ZIP container — drops the outer HTML shell (double-click opens an archive
# tool, not a browser). Still a valid, verifiable .epi.
epi migrate case.epi --out case-data.epi --legacy-zip
epi verify case-data.epi          # → same seal verdicts (identity is still unpinned)

# Or export the data in non-HTML shapes:
epi export agt case.epi --out case.agt.json      # AGT-style audit JSON
# Signed TRACE export requires a durable URI for the .epi transcript:
epi export trace case.epi --out case.trace.json \
  --transcript-uri https://evidence.example/case.epi
# Local demo only (no durable URI, unsigned):
epi export trace case.epi --out case.trace.json --no-sign
epi export-summary case.epi --text               # plain-text decision record
```

**Honest caveat.** `epi migrate --legacy-zip` copies the sealed payload as-is, so
the *outer* clickable shell goes away but any `viewer.html` that was already
**inside** the ZIP stays as a member (it is part of the signed payload and cannot
be removed without breaking the seal). It only runs if someone deliberately
extracts and opens it. To hand over evidence that never contained a viewer at
all, seal it that way — the new default — or use the JSON/text exports
(`epi export agt|trace`, `epi export-summary --text`); note those are **derived
views**, not the sealed original, so `epi verify` on the `.epi` remains the
authoritative check.

---

## 8. Bottom line for a security reviewer

- A `.epi` is **data + an offline viewer**, not a program. No native code, no
  installer, no macro.
- The shipped 4.6.3 viewer makes **zero external/network calls** (§2, with a
  reproduction script). Verification is **fully offline** (§3).
- **Do not trust the in-file verdict** — trust `epi verify`, and pin the
  sender's key (§3, §4).
- Open files from **untrusted** senders with normal HTML-attachment caution;
  there is no CSP yet and no third-party pen-test (§5, issue #153).
- Prefer **CLI keys** over browser Sign & seal; the browser seed rests in
  `localStorage` (§6, issue #153).
- Need a non-HTML handover? Send the **data-only** form (§7).
