<div align="center">
  <img src="https://raw.githubusercontent.com/mohdibrahimaiml/epi-recorder/main/docs/assets/logo.png" alt="EPI Logo" width="180"/>

# EPI (Evidence Packaged Infrastructure) — Evidence for AI agents

### Record. Seal. Verify offline. The answer is a **file**.

[![PyPI](https://img.shields.io/pypi/v/epi-recorder?color=blue&label=PyPI)](https://pypi.org/project/epi-recorder/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![Version v4.6.2](https://img.shields.io/badge/version-v4.6.2-purple)](https://github.com/mohdibrahimaiml/epi-recorder/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/mohdibrahimaiml/epi-recorder/blob/main/LICENSE)
[![Release Gate](https://github.com/mohdibrahimaiml/epi-recorder/actions/workflows/release-gate.yml/badge.svg?branch=main)](https://github.com/mohdibrahimaiml/epi-recorder/actions/workflows/release-gate.yml)

```bash
pip install epi-recorder
epi demo --no-browser    # record → seal → verify (no API key)
```

[60-second path](#60-second-path) ·
[What a .epi is](#what-a-epi-file-is) ·
[CLI](#cli) ·
[How to use it](docs/USER-GUIDE.md) ·
[Docs](#docs) ·
[Standards](#standards--compliance)

How it works: [ARCHITECTURE.md](ARCHITECTURE.md) — packages, integrity model, and where to read next. Docs map: [docs/README.md](docs/README.md).

</div>

---

> When someone asks what your agent did six months ago,  
> the answer should be a **`.epi` file** — not a dashboard login and a shrug.

`epi-recorder` turns an AI agent's run into **evidence a third party can verify.** Not a log you have to trust, but a portable, signed artifact that leaves your platform and declares exactly what it captured — verifiable offline with open tooling.
No account and no EPI server: verification is fully offline. When sealing, EPI asks public
RFC 3161 timestamp services for a trusted time (only a hash is sent; switch off with `EPI_NOTARIZE=0`
or use your own with `EPI_TSA_URLS`).

<div align="center">
  <p><strong>Open a sealed <code>.epi</code> offline</strong> — <code>epi view run.epi</code></p>
  <img
    src="https://raw.githubusercontent.com/mohdibrahimaiml/epi-recorder/main/docs/assets/epi-file-viewer-full.png"
    alt="EPI offline viewer showing a sealed .epi evidence file — timeline, integrity, and decision context"
    width="900"
  />
  <p><em>Forensic case view of a sealed run. Sample artifact: <a href="https://github.com/mohdibrahimaiml/epi-recorder/blob/main/docs/assets/readme-demo.epi"><code>docs/assets/readme-demo.epi</code></a></em></p>
</div>

---

## 60-second path

Works **without** any LLM API key:

```python
# demo.py
from epi_recorder import record, get_current_session

with record("demo.epi", goal="show the golden path"):
    s = get_current_session()
    s.log("tool.call", tool="lookup", id="A-1")
    s.log("tool.response", ok=True, balance=250)
    s.log("decision", action="approve", reason="within limit")
```

```bash
python demo.py
epi verify demo.epi
epi-register demo.epi
epi view demo.epi
```

`record("demo.epi")` writes **`epi-recordings/demo.epi`**: a bare file name goes
into `./epi-recordings/`. A path with a folder, such as `./demo.epi` or
`out/demo.epi`, is written exactly there. Run the commands above from the same
folder as `demo.py`; `epi verify demo.epi` finds the file in `./epi-recordings/`.

Running `python demo.py` again never replaces earlier evidence: the second run
seals to `epi-recordings/demo-2.epi` (then `demo-3.epi`, …) and says so. Set
`EPI_OVERWRITE=1` to replace `demo.epi` in place instead.

```text
$ python demo.py
[EPI] 3 steps → epi-recordings/demo.epi  Signed ✓
```

| Step | Command | What you get |
|------|---------|----------------|
| **Record + seal** | `python demo.py` | Signed `epi-recordings/demo.epi` (secrets redacted by default) |
| **Verify** | `epi verify demo.epi` | Integrity + signature checks offline |
| **Register** | `epi-register demo.epi` | Without `--service`: a **local, self-issued** SCITT receipt embedded in the `.epi` (not an independent ledger entry) |
| **View** | `epi view demo.epi` | Self-contained browser viewer (screenshot above) |

Typical first-run verify:

| Check | Result |
|-------|--------|
| Integrity (SHA-256) | Valid |
| Signature (Ed25519) | Valid |
| Identity | Often LOCAL / UNKNOWN until you pin trust |
| Secrets | Redacted by default (`redact=True`) |

> **First-run WARN / LOCAL identity is normal** — seal integrity and signature can still pass.  
> Identity is separate from seal. A customer pins the sender's key, obtained out of band, with
> `epi keys trust <sender-key-file> --name <name>` (the sender's `.pub`, `did.json` or saved
> `epi keys export` line — never the `.epi` you are checking) or
> `epi keys trust --from-did did:web:vendor.com --name <name>`.  
> Policy / “did the run break our rules?” is separate again: `epi analyze` — see [docs/POLICY.md](docs/POLICY.md).

`epi-register` is a standalone alias for `epi scitt register` (same options, same result).
Without `--service <url>` it creates a LOCAL self-issued receipt signed by your own key, not an
entry in an independent transparency ledger; pass `--service` for that.

That’s the product. Everything below is optional depth.

---

## With OpenAI

```python
from openai import OpenAI
from epi_recorder import record, wrap_openai

client = wrap_openai(OpenAI())  # needs OPENAI_API_KEY

with record("agent.epi", goal="Answer a user question"):
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}],
    )
```

```bash
python agent.py
epi verify agent.epi
epi view agent.epi
```

API keys in prompts/headers are **redacted automatically** before they land in the file.

---

## What a `.epi` file is

Every `.epi` uses the **Envelope v2** container format — a **polyglot HTML+ZIP**
binary that opens natively in any browser and can be extracted programmatically.

```text
demo.epi
├── manifest.json     # Ed25519 signature + SHA-256 file hashes
├── steps.jsonl       # Timeline (hash-linked steps)
├── environment.json  # Runtime snapshot (sensitive env redacted)
├── analysis.json     # Fault / policy analysis (when generated at seal)
├── viewer.html       # Offline forensic UI
└── VERIFY.txt        # Plain-text auditor instructions
```

| Guarantee | How |
|-----------|-----|
| **Integrity** | SHA-256 over every sealed member |
| **Authenticity** | Ed25519 signature on the manifest |
| **Chain** | Each step’s `prev_hash` links the timeline |
| **Privacy** | Default secret redaction (API keys, tokens, PII) |

Samples: [docs/assets/SAMPLES.md](docs/assets/SAMPLES.md) · try `docs/assets/readme-demo.epi`.

---

## Integrations

| Stack | How |
|-------|-----|
| OpenAI | `wrap_openai(OpenAI())` |
| Anthropic | `wrap_anthropic(Anthropic())` |
| LangChain | `EpiCallbackHandler(session)` inside `with record(...) as session` |
| LiteLLM | `EPICallback` |
| pytest | `pytest --epi` |
| Microsoft AGT | `epi import agt <file>` |
| TRACE Trust Record | `epi export trace <file.epi>` — log-import Level 0; see caveats below |

```python
# LangChain (canonical adapter)
from langchain_openai import ChatOpenAI
from epi_recorder import record
from epi_recorder.adapters.langchain import EpiCallbackHandler

with record("run.epi") as session:
    handler = EpiCallbackHandler(session)
    llm = ChatOpenAI(model="gpt-4o-mini", callbacks=[handler])
    llm.invoke("…")
```

```bash
# pytest — attach evidence to failing tests
pytest --epi
```

`pytest --epi` writes one `.epi` per **failing** test to `./test-evidence/`
(`--epi-dir DIR` to change it, `--epi-on-pass` to keep passing tests too).
Files are named after the test (`test_x.py_test_bad.epi`); unlike `record()`,
a re-run replaces the file for the same test in place.

### TRACE export (honest claims)

```bash
epi export trace run.epi --out run.trace.json --transcript-uri https://host/run.epi
```

Signing key order: `--key` → private key that sealed the `.epi` → `TRACE_PRIVATE_KEY_PEM` → ephemeral (warning). `allow_embedded_key=True` when verifying only proves **internal consistency** of the record against its own `cnf.jwk`. It does **not** prove the record came from a trusted issuer. What we claim: the JSON is self-consistent and bound to the key that signed it (the sealing key when that key is available).

`policy.bundle_hash` in TRACE is specified as a Cedar policy hash. We hash `policy.json` (the sealed EPI policy document), not a Cedar bundle. `policy.enforcement_mode` is `"declared"` — we did not run a Cedar engine. `appraisal.status` is `"none"`.

More: [docs/FRAMEWORK-INTEGRATIONS-5-MINUTES.md](docs/FRAMEWORK-INTEGRATIONS-5-MINUTES.md)

---

## CLI

| Command | Purpose |
|---------|---------|
| `epi demo` | Guided demo: record → seal → verify |
| `epi verify <file.epi>` | Offline integrity + signature check; customers and auditors run `epi verify FILE --policy strict --witness-log received.jsonl` (rely on the exit code only with `--policy strict`; WARN exits 0) |
| `epi-register <file.epi>` | Alias of `epi scitt register`: embed a SCITT receipt (local self-issued unless `--service <url>`) |
| `epi view <file.epi>` | Open offline viewer (screenshot above) |
| `epi analyze <file.epi>` | Fault / policy summary from sealed analysis |
| `epi policy init` | Create `epi_policy.json` rulebook |
| `epi run [script.py]` | Record a Python workflow that already emits EPI steps (prompts for a script if omitted) |
| `epi keys generate` / `list` / `trust` / `revoke` / `unrevoke` | Signing keys and pinned (trusted) keys; `generate` and `list` print fingerprints |
| `epi enterprise setup` / `pack` | Org kit + auditor pack |
| `epi scitt register <file.epi>` | SCITT receipt; `--service <url>` for an independent transparency service |
| `epi import agt <path>` | Import Microsoft AGT evidence |
| `epi export trace <file.epi>` | TRACE v0.2 log-import record (self-consistency, not issuer attestation) |

Policy + fault analyzer guide: [docs/POLICY.md](docs/POLICY.md)

## EPI Cloud (share a run with a customer)

Sealed runs stay offline by default. To share one with a customer (a bank
reviewer, an auditor), push it to EPI Cloud and send them a trust link they
open in a browser — nothing to install on their side.

Install inside a virtual environment, so EPI's libraries stay separate from
your other tools:

```bash
python -m venv epienv
epienv\Scripts\activate
pip install epi-recorder
epi --version
```

(`source epienv/bin/activate` on macOS/Linux. If Windows says `epi` is
"not on PATH" after install, the program landed in a folder Windows doesn't
search: activate the environment first and install/run in that same window,
or run `python -m epi_cli` instead of `epi`.)

Then, in order:

1. `epi cloud login` — the terminal shows a short code. Type it at
   cloud.epilabs.org/auth/device and pick the customer this computer
   records for. Nothing secret to copy.
2. `epi demo` — records, seals and uploads a sample run for that customer.
3. On cloud.epilabs.org, create a share link for the customer and send it
   to them. They verify the run in their browser, or offline with
   `epi verify`.

Free plan: 1 customer. A second customer needs an upgrade (Plans page).

---

## Security defaults

- **Redaction is on** (`redact=True`). Keys/tokens/PII become placeholders.
- Prefer **not** using `redact=False` in production (it warns).
- Verification is **local** — no network required for integrity/signature.
- First-run identity WARN / LOCAL is expected until you trust a key.
- **Seal ≠ identity ≠ policy.** Verify proves the file; analyze grades the run against rules/heuristics.

---

## Docs

| Topic | Link |
|-------|------|
| **How to use it** (what / where / how) | [docs/USER-GUIDE.md](docs/USER-GUIDE.md) |
| **Docs map** (recorder · Cloud · website) | [docs/README.md](docs/README.md) |
| **Bank / auditor briefing** | [docs/EPI_MASTER_DOCUMENTATION.md](docs/EPI_MASTER_DOCUMENTATION.md) |
| **What verify means** | [docs/VERIFICATION_CONTRACT.md](docs/VERIFICATION_CONTRACT.md) |
| **Known limitations** (read before a security review) | [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) |
| Architecture | [ARCHITECTURE.md](ARCHITECTURE.md) |
| CLI (`epi cloud` included) | [docs/CLI.md](docs/CLI.md) |
| EPI Cloud | [docs/CLOUD.md](docs/CLOUD.md) |
| Website source | [docs/WEBSITE.md](docs/WEBSITE.md) |
| Auditors guide | [docs/AUDITORS-GUIDE.md](docs/AUDITORS-GUIDE.md) |

Start at [docs/README.md](docs/README.md). Do not treat old search hits or forks as current.

---

## Standards & compliance

EPI produces **evidence files** that help with audit trails. It is **not a compliance guarantee**
and **does not provide legal advice**. Whether evidence satisfies a specific regulatory threshold
is for the auditor or notified body to determine.

| Topic | Docs |
|-------|------|
| EU AI Act Annex IV (tooling, not a certificate) | [docs/ANNEX-IV.md](docs/ANNEX-IV.md) |
| AIUC-1 domains | [docs/standards/aiuc-1-evidence.md](docs/standards/aiuc-1-evidence.md) |
| SCITT | [docs/standards/scitt-predicate.md](docs/standards/scitt-predicate.md) |

```bash
epi verify agent.epi --aiuc1   # evidence grouped by AIUC-1 domain (not a certification)
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `epi: command not found` | Same venv as `pip install`, or `python -m epi_cli` |
| First verify WARN / LOCAL identity | Normal if seal OK — the receiver pins the sender's key from the sender (`epi keys trust <sender-key-file> --name <name>` or `--from-did <did>`), never from the file being checked |
| `Integrity: FAILED` | File changed after seal — re-record |
| `epi analyze` says heuristic only | Add `epi_policy.json` via `epi policy init`, re-run from that folder |
| Share / portal fails | Hosted needs backend; local record/verify never depends on it |

**Trust-model note:** Integrity checks whether the sealed record was altered since sealing — not that every real-world action was captured.

---

## Project layout (contributors)

**Core** (actively developed, covered by the release gate):

| Path | Role |
|------|------|
| `epi_recorder/` | Python SDK (`record`, wrappers) |
| `epi_core/` | Container, crypto, redaction, verify, fault analyzer |
| `epi_cli/` | `epi` command (including `epi cloud`) |
| `epi_gateway/` | Self-hosted capture/review runtime (`epi gateway serve`) |
| `cloud/` | EPI Cloud Worker (`cloud.epilabs.org`) |
| `web_viewer/` | Canonical browser UI (source for `epi view` and the embedded viewer) |
| `epi_viewer_static/` | Browser crypto baked into every sealed file at pack time |
| `pytest_epi/` | Pytest plugin |
| `website/` | Public site source of truth (`epilabs.org`) |
| `scripts/` | Build, sync, release and verification helper scripts |
| `docs/` | Start at [docs/README.md](docs/README.md) |
| `tests/` | ~190 test files, including the `test_core_loop_golden.py` regression path |

**Experimental** (frozen — works as documented, bug fixes allowed, no new features until a paying user asks; not on the critical path):

| Path | Note |
|------|------|
| `epi_mcp/` | ChatGPT/Claude connector (hosted HTTP still on Render) |
| `verify_portal/` | Legacy hosted share/verify API. Login is EPI Cloud, not this service. |
| `epi_recorder/integrations/trace_exporter.py` | TRACE export |
| `epi_recorder/integrations/agt*` | Microsoft AGT import/export |
| `epi_guardrails/` | Guardrails |
| remote SCITT service | Local SCITT receipt is core; the hosted service is not |

Website edits: only under `website/`. `npm run build` copies it to `site/` for Cloudflare Pages; `python scripts/sync_website.py` mirrors it to `verify_portal/static/` and `epi-official/`. Details: [docs/WEBSITE.md](docs/WEBSITE.md), [ARCHITECTURE.md](ARCHITECTURE.md).

---

## License

MIT — see [LICENSE](LICENSE).

**Site:** [epilabs.org](https://epilabs.org) · **Issues:** [GitHub Issues](https://github.com/mohdibrahimaiml/epi-recorder/issues)
