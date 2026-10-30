# You received a `.epi` file — start here

One page, no jargon, for whoever has to act on the file. Written for an
auditor, a reviewer, a claims handler, or a colleague — not for the person who
recorded it.

Product version 4.7.0. Related: [USER-GUIDE.md](./USER-GUIDE.md) (full manual),
[FILE-SAFETY.md](./FILE-SAFETY.md) (is it safe to open?),
[KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md) (what it does not prove).

---

## 1. What this file is

A sealed record of one automated run: what the agent was asked, what it did,
which rule it checked, and what it decided — packaged so that nobody can change
it afterwards without breaking the seal.

It is **evidence**, not a program. There is no installer, no macro and no
executable inside it.

## 2. Which shape you have

| | Data-only (the default) | Self-opening (`--with-viewer`) |
|---|---|---|
| Size | ~10–20 KB | ~400 KB+ |
| Double-click | **does nothing** — it is a ZIP | opens in a browser |
| To read it | `epi view case.epi` | double-click, or `epi view` |
| Safe through email filters | usually yes | often blocked (HTML attachment) |

Not sure? `epi verify case.epi` tells you, and so does the file size.

## 3. The four commands that matter

```bash
epi verify case.epi                 # 1. is the seal intact, and who signed it?
epi view case.epi                   # 2. read it in a browser, offline
epi keys trust <sender-key-or-did> --name <sender>   # 3. pin the sender once
epi verify case.epi --policy strict # 4. the claim-ready check (exit code 1 = do not rely)
```

If `epi` is not installed: `pip install epi-recorder` (Python 3.11+), or run
`python -m epi_cli verify case.epi`. With no Python at all, ask the sender for
the standalone `epi-verify` binary — one file, nothing to install
([STANDALONE-VERIFIER.md](./STANDALONE-VERIFIER.md)).

## 4. Reading the result

| You see | What it means | What to do |
|---|---|---|
| `PASS` / `SEAL · IDENTITY PINNED` | Bytes intact, sealed by a key **you** pinned | Rely on it |
| `WARN` / `UNVERIFIED IDENTITY` | Bytes intact, but nothing proves who sealed it yet | Pin the sender's key, then re-run |
| `FAIL` / `NOT A KEY YOU TRUST` | Intact, but signed by a key you have not accepted | Confirm the sender's key before relying on it |
| `FAIL` / `SEAL FAIL` | The file changed after sealing | Do not rely on it; ask for a fresh one |
| `Timestamp: none` | No trusted time was attached | The date is the sender's claim, not proof |

`WARN` exits `0`; `FAIL` exits `1`. Rely on the exit code only with
`--policy strict`.

## 5. Pinning the sender (the only hard step)

The seal proves the bytes. It does **not** prove who made them until you pin
their key, and the key must come from the sender — never from the file you are
checking, because an attacker's file carries the attacker's key.

```bash
epi keys trust --from-did did:web:vendor.com --name vendor          # vendor publishes a DID
epi keys trust vendor.pub --name vendor                             # vendor sent a key file
epi keys trust case.epi --name vendor --fingerprint "6090 c0d9 4782 bb06"
```

The third form is only allowed with `--fingerprint`: the value the sender reads
to you **by phone or another channel** — not the fingerprint printed on the
file. The command refuses if they differ.

## 6. What it proves — and what it does not

**Proves:** the recorded steps, policy result and manifest have not been altered
since sealing, and the signature matches the key that sealed them.

**Does not prove:** that every real-world action was captured (in-process
recording is self-reported — use the gateway for proxy-level capture), that the
signer is who they claim until you pin them, or that any regulation is
satisfied. It is evidence input for an auditor or underwriter, not a certificate.

## 7. If something goes wrong

| Symptom | Fix |
|---|---|
| `epi: command not found` | Install in the same environment, or use `python -m epi_cli` |
| Double-click does nothing | Expected for data-only; use `epi view`, or `epi associate` once |
| `epi view` opens nothing | Copy the printed `http://127.0.0.1:…` URL into your browser |
| File blocked by email | Ask the sender for the data-only form (`epi migrate case.epi --out case-data.epi --legacy-zip`) |
| Leaked content concern | Redaction is on by default, but review `steps.jsonl` before forwarding |

Questions about **the run** go to the sender. Questions about **the seal** go to
`epi verify --verbose`, or open an issue at
<https://github.com/mohdibrahimaiml/epi-recorder/issues>.
