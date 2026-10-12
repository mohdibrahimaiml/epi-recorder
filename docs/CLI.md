# EPI CLI Reference (v4.6.0)

**Version:** 4.6.0
**Primary entrypoint:** `epi`

---

## Start Here

**Docs map:** [README.md](./README.md) · **Pilot (archived):** [archive/PILOT.md](./archive/PILOT.md) · **Auditors:** [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md)

Start with `epi demo` if you want to capture one AI run from Python, open it in the browser, and verify the resulting `.epi` artifact in minutes. The first browser screen is case-first: it leads with decision, review state, trust, and the evidence trail instead of a setup dashboard.

For an enterprise customer pilot (org kit + auditor pack), use:

```bash
epi enterprise setup
epi enterprise pack your-run.epi
```

See [archive/ENTERPRISE-15-MINUTES.md](./archive/ENTERPRISE-15-MINUTES.md) (archived; may be out of date).

If you already have exported Microsoft Agent Governance Toolkit evidence, start with:

```bash
epi import agt examples/agt/sample_bundle.json --out sample.epi
epi verify sample.epi
epi view --extract review sample.epi
```

You can also point the same command at a raw AGT evidence directory or an EPI-owned AGT import manifest:

```bash
epi import agt examples/agt/evidence-dir --out sample.epi
epi import agt examples/agt/manifest-input/agt_import_manifest.json --out sample.epi
```

If you are not in the repo checkout, replace the sample path with your own exported AGT bundle, evidence directory, or import manifest.

If you prefer zero local setup, use the Colab notebook linked from [README.md](../README.md).

`epi view` is the canonical EPI case review experience. Older desktop viewer projects remain legacy/internal compatibility surfaces and are not the recommended front door.

---

## Core Commands

| Command | Purpose |
| --- | --- |
| `epi demo` | Start the sample refund workflow and open the case-first investigation flow in the browser. Recommended first run. |
| `epi enterprise setup` / `pack` / `capabilities` | Enterprise evidence kit (org trust scaffold + auditor pack). See [archive/ENTERPRISE-15-MINUTES.md](./archive/ENTERPRISE-15-MINUTES.md). |
| `epi import agt <input> --out <file.epi>` | Convert exported AGT evidence into a portable `.epi` case file from a bundle JSON, evidence directory, or AGT import manifest. |
| `epi run [script.py]` | Record a Python workflow that already emits EPI steps (prompts for a script if omitted). |
| `epi record --out <file.epi> -- <cmd...>` | Record an arbitrary command with an explicit output path. |
| `epi view <file.epi>` | Open a case file in the browser review view. |
| `epi verify <file.epi>` | Verify case file integrity, signature, identity pin and policy. Auditors: `--policy strict --witness-log received.jsonl`. |
| `epi share <file.epi>` | Upload a hosted browser link for a portable case file. |
| `epi migrate <file.epi> --out <new.epi>` | Convert between legacy ZIP and envelope `.epi` container formats. |
| `epi init --github-action` | Create a starter demo and optional CI evidence workflow. |
| `epi integrate <target>` | Generate safe examples for pytest, LangChain, LiteLLM, OpenTelemetry, or AGT. |
| `epi telemetry status|enable|disable|test` | Manage privacy-first opt-in telemetry and pilot signup. |
| `epi analyze <file.epi>` | Show fault-analysis output without opening the case view. |
| `epi ls` | List local recordings. |
| `epi associate` | Register file association support. Best used as a repair or developer path on Windows. |
| `epi unassociate` | Remove file association support. |
| `epi doctor` | Run self-healing diagnostics. |
| `epi keys generate` | Generate an Ed25519 signing key pair. |
| `epi keys list` | List signing key pairs. |
| `epi keys export [--format hex]` | Export a public key as base64 (default) or hex. |
| `epi keys trust <file> --name <name>` / `--from-did <did>` | Pin a public key (PEM, `did.json` or base64 file, or a did:web DID) in the local trust registry. |
| `epi keys revoke <name>` / `unrevoke <name>` | Revoke a pinned key, or undo the revocation. |
| `epi keys trust --from-did did:web:<domain>` | Resolve a vendor's did:web document once and pin its key. |
| `epi keys did --domain <domain>` | Write a `did.json` publishing this machine's key under your domain. |
| `epi policy` | Create, explain, and validate `epi_policy.json` rule files. |
| `epi witness status` / `flush` / `drop` | Vendor side: inspect, retry or remove seal reports queued for a customer witness endpoint. |
| `epi witness serve` | Customer side: run the witness receiver that records every seal report (`--out received.jsonl`). |
| `epi review <file.epi>` | Confirm or dismiss policy-grounded issues and save human review notes. |

### Advanced / operator commands

| Command | Purpose |
| --- | --- |
| `epi gateway serve` | Start the open-source AI capture gateway for low-friction developer adoption. |
| `epi gateway export` | Export one shared gateway-backed case to a portable `.epi` case file. |
| `epi export trace <file.epi>` | Emit a TRACE v0.2 log-import Trust Record bound to the `.epi` hash. Signing: `--key` → sealing key → `TRACE_PRIVATE_KEY_PEM` → ephemeral. Embedded `cnf.jwk` proves internal consistency, not a trusted issuer. `policy.bundle_hash` hashes `policy.json`, not Cedar (`enforcement_mode: declared`). `appraisal.status` is `none`. |
| `epi connect open` | Start the local browser review workspace and connector bridge together. |
| `epi connect serve` | Run only the local connector bridge for the browser Setup Wizard. |

---

## `epi import agt <input> --out <file.epi>`

Use this when you already have exported AGT evidence and want a normal `.epi` case file that works with `epi verify`, `epi view`, `epi review`, and `epi export-summary`.

```bash
epi import agt examples/agt/sample_bundle.json --out sample.epi
epi import agt examples/agt/evidence-dir --out sample.epi
epi import agt examples/agt/manifest-input/agt_import_manifest.json --out sample.epi
epi verify sample.epi
epi view --extract review sample.epi
```

If you are running from a bare install instead of this repo checkout, replace the sample path with your own exported AGT bundle, AGT evidence directory, or EPI-owned AGT import manifest.

Input modes:

- bundle JSON: the neutral aggregated AGT bundle contract
- evidence directory: AGT-style files such as `audit_logs.json`, `flight_recorder.json`, `compliance_report.json`, and `annex_iv.json`
- manifest JSON: an EPI-owned `agt_import_manifest.json` that maps custom filenames into the same bundle contract

Default behavior:

- preserves the raw AGT payloads under `artifacts/agt/`
- writes `artifacts/agt/mapping_report.json` so the transformation itself is auditable
- synthesizes `analysis.json` so imported artifacts can still participate in `epi review`
- signs the artifact when a default signing key exists

Important options:

- `--strict --dedupe fail` turns unknown event kinds, unclassified fields, and ambiguous dedupe cases into hard failures
- `--analysis none` omits `analysis.json` and keeps the choice visible in `mapping_report.json`
- `--no-attach-raw` skips storing the source AGT payloads under `artifacts/agt/`

What you should see in the resulting artifact:

- `steps.jsonl` - normalized execution trace
- `policy.json` and `policy_evaluation.json` - imported governance evidence
- `analysis.json` - synthesized findings when analysis is enabled
- `artifacts/agt/mapping_report.json` - transformation audit and provenance report

What you should see in the viewer:

- `Source system: AGT`
- `Import mode: EPI`
- `Overview`, `Evidence`, `Policy`, `Review`, `Mapping`, `Trust`, and `Attachments`
- a transformation audit that shows what EPI preserved, translated, derived, or synthesized

After the deterministic extract proof, you can still open the interactive browser flow with:

```bash
epi view sample.epi
```

For the public walkthrough, see [`AGT-IMPORT-QUICKSTART.md`](AGT-IMPORT-QUICKSTART.md).

---

## `epi init --github-action`

Creates a first-run demo script and can add a safe GitHub Actions workflow for EPI evidence.

```bash
epi init
epi init --github-action
epi init --github-action --force
```

Behavior:
- detects pytest projects and writes a workflow that runs `pytest --epi --epi-dir=evidence`
- skips an existing `.github/workflows/epi-audit.yml` unless `--force` is provided
- asks before adding the workflow in interactive mode when `--github-action` is not passed

---

## `epi integrate <target>`

Generates integration examples for existing projects without rewriting user agent code.

```bash
epi integrate pytest --dry-run
epi integrate pytest --apply
epi integrate langchain --write-examples
epi integrate litellm --write-examples
epi integrate opentelemetry --write-examples
epi integrate agt --write-examples
```

Supported targets:
- `pytest`
- `langchain`
- `litellm`
- `opentelemetry`
- `agt`

Default behavior:
- non-interactive mode is dry-run unless `--apply` or `--write-examples` is set
- interactive mode shows what would be written before creating examples or workflows
- generated files live under `.epi/examples/` unless the target is the pytest GitHub Actions workflow
- existing generated files are skipped unless `--force` is passed

---

## `epi telemetry status|enable|disable|test`

Manages privacy-first opt-in telemetry and the EPI Pilot signup.

```bash
epi telemetry status
epi telemetry enable
epi telemetry enable --join-pilot --email you@example.com --use-case compliance --consent-to-contact
epi telemetry enable --join-pilot --email you@example.com --use-case "agt integration" --consent-to-contact --link-telemetry
epi telemetry test
epi telemetry disable
```

Telemetry is off by default. EPI does not create an install ID until telemetry is enabled or the user explicitly links a pilot profile to telemetry.

Allowed telemetry metrics are non-content only: event name, timestamp, EPI version, Python version, OS, environment, integration type, command, success/failure, artifact bytes, artifact count, and CI flag.

EPI never sends prompts, outputs, file paths, repo names, hostnames, usernames, API keys, artifact content, or customer data. Pilot signup contact fields are stored separately and require explicit contact consent. Linking a pilot profile to telemetry also requires explicit consent.

After high-intent commands such as `epi init`, `epi integrate`, and successful `epi verify`, EPI may print a local-only opt-in reminder. The reminder does not create an install ID or send telemetry.

If a telemetry send fails after opt-in, EPI queues the sanitized event under `~/.epi/telemetry_queue.jsonl` and retries it on later telemetry sends. Pilot signup is the reachable-user path for dashboard access, compliance report exports, priority support, and roadmap input.

See [`TELEMETRY-PRIVACY.md`](TELEMETRY-PRIVACY.md).

---

## `epi run <script.py>`

Use this when you want EPI to run a Python script and capture whatever evidence is available.

```bash
epi run my_agent.py
```

Typical outcome:
- runs the script
- captures plain `print(...)` output as `stdout.print` steps
- records richer workflow evidence if EPI steps are actually emitted
- seals a `.epi` artifact
- performs analysis before sealing

Important:
- plain console capture is useful, but limited
- for guaranteed evidence capture, use `from epi_recorder import record` or a supported integration
- for a middle ground inside `epi run`, use `get_current_session().log_step(...)`
- for agent-shaped evidence inside `epi run`, use `get_current_session().agent_run(...)`
- if no execution steps are captured, `epi run` now exits non-zero and tells you how to fix the script

Think of the evidence quality like this:

- `print(...)` only -> basic console evidence
- `get_current_session().log_step(...)` -> structured custom workflow evidence
- `get_current_session().agent_run(...)` -> structured agent evidence with messages, tools, decisions, approvals, memory activity, and lineage
- `record(...)` / wrappers / integrations -> best path for policy, fault analysis, and review

---

## `epi view <file.epi>`

Opens a saved case file using the canonical browser review flow.

```bash
epi view my_run.epi
epi view --extract ./review my_run.epi

# View by name from ./epi-recordings
epi view my_run
```

`epi view` opens a generated browser review page for the case. The `.epi` file
itself remains a binary artifact container; browsers do not execute the
embedded `viewer.html` directly from inside the `.epi` file.

`epi view` exits `1` if the file was altered after sealing, so you never
review tampered contents by accident; run `epi verify` for the full report.

An `.epi` is an HTML+ZIP file, so plain `unzip` warns about "extra bytes at
beginning" (and exits non-zero) even on a good file. That is expected. Use
`epi view --extract DIR file.epi` or `python -m zipfile -e file.epi DIR` to
look inside.

`epi view --extract` now writes a self-contained `viewer.html` with the browser runtime inlined, including vendored JSZip, so the extracted review page has no external script dependencies and remains offline/air-gapped safe.

The viewer is case-first. Expect the loaded artifact to open into:

- `Overview` for decision, reason, review state, and trust state
- `Evidence` for the step trail, tool calls, and model output
- `Policy` and `Review` when those layers are present
- `Mapping` for imported evidence such as AGT transformations
- `Trust` for signature and integrity details

---

## `epi associate` / `epi unassociate`

Registers `.epi` files with the operating system so supported desktop environments can open them with EPI. On Windows, the packaged installer is the recommended path for reliable double-click behavior. `epi associate` remains useful as a repair or developer fallback.

```bash
epi associate
epi unassociate
```

---

## `epi verify <file.epi>`

Recalculates hashes, checks the Ed25519 signature and step chain, matches
the sealer against your pinned keys, and applies a policy. Works offline.

Options (from `epi verify --help`):

| Option | Meaning |
| --- | --- |
| `--json` | Output as JSON. |
| `--verbose`, `-v` | Verbose output. |
| `--report <path>` | Write a verification report to this file (e.g. `verification_report.txt`). |
| `--review` | Verify embedded human review ledger, signature, chain, and artifact binding. |
| `--strict` | Enforce STRICT policy (fails on any warning, unsigned, or forensic gaps). |
| `--policy permissive\|standard\|strict` | PERMISSIVE (integrity only), STANDARD (dev default — unpinned identity is WARN, not claim-ready), STRICT (enterprise/insurance — requires org-pinned sealer; use for claim acceptance). Default: `standard`. |
| `--aiuc1` | Include AIUC-1 trust domain mapping in the verification report. |
| `--tsa-root <path>` | Extra TSA trust root (PEM). Repeatable. Adds to the pinned roots for timestamp validation. |
| `--require-timestamp` | FAIL unless at least one seal-time RFC 3161 token validates. |
| `--web` | Open verification results in browser at verify.epilabs.org after CLI check. |
| `--qr` | Print a QR code that opens the artifact on verify.epilabs.org. |
| `--offline` | No network: skip DID resolution and remote fetches (local pins still apply). |
| `--witness-log <path>` | Customer witness log (`received.jsonl`) to check this file against. |

Exit code is `1` on FAIL and `0` on PASS **or WARN**. Scripts must rely on
the exit code **with `--policy strict`**: under the default `standard`
policy an unpinned sealer, a seal missing from the witness log, or
incomplete evidence (e.g. a `tool.call` with no `tool.response`, shown as
`Forensic: FAIL — ...`) is only a WARN and exits `0`. Under `--policy strict`
each of these FAILs; incomplete evidence reports
`Reason: Evidence incomplete (Strict Policy requires full telemetry coverage)`.

Recommended for auditors and customers ([AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md)):

```bash
epi verify case.epi --policy strict --witness-log received.jsonl
# add --require-timestamp only if the vendor seals with a reachable timestamp service
```

The first line of the report is the verdict, for example (trimmed):

```text
$ epi verify case-002.epi --policy strict --witness-log received.jsonl
╭──────────────────────── ✔ SEAL · IDENTITY PINNED EPI Verification Report ────────────────────────╮
│ DECISION: PASS                                                                                   │
│ Policy: strict                                                                                   │
│ Reason: All strict criteria met (Integrity, Identity, Completeness)                              │
│ IDENTITY (who sealed — required for claim trust)                                                 │
│   - Status:       KNOWN                                                                          │
│   - Name:         vendor                                                                         │
│ SEAL (Objective Proofs — not identity)                                                           │
│   - Integrity:    Verified                                                                       │
│   - Signature:    Valid                                                                          │
│   - Forensic:     PASS                                                                           │
│   - Witness:      WITNESSED (received 2026-10-12T09:34:55.487339+00:00)                          │
```

All verdict headlines and what they mean: [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md#reading-the-verdict).

After a successful verification, EPI now points to the two lowest-friction next steps:
- `epi share <file.epi>` for a hosted browser link
- `https://epilabs.org/verify` for client-side browser verification

---

## `epi share <file.epi>`

Uploads a validated `.epi` file to a configured hosted share service and prints a browser link.

```bash
epi share demo.epi
epi share demo.epi --expires 7
epi share demo.epi --json
epi share demo.epi --api-base-url http://localhost:8787
```

Behavior:
- validates the `.epi` locally before upload
- rejects files larger than 5 MB
- accepts valid signed artifacts and valid unsigned artifacts
- returns a hosted link shaped like `https://epilabs.org/cases/?id=...`

This is the fastest path when a teammate should be able to open the repro in a browser without installing EPI first.

If the default hosted backend is not available yet, point the command at your own gateway with `--api-base-url` or `EPI_SHARE_API_URL`.

---

## `epi doctor`

Runs local diagnostics and repairs common setup issues.

```bash
epi doctor
```

---

## `epi policy`

Creates and validates `epi_policy.json` files that define acceptable agent behavior.

In the current **v4.5.0** line, `epi policy init` is the guided front door for
policy. It asks a small number of business-language questions and writes the
machine-readable rulebook for you.
It now shares the same starter rule shapes as the browser Rules editor, and the custom starter path can be pinned with repeated `--starter-rule` options.
For teams that prefer the browser flow, `--open-editor` opens the same Rules editor with the policy preloaded from either `epi policy init` or `epi policy show`.

The analyzer enforces:
- `constraint_guard`
- `sequence_guard`
- `threshold_guard`
- `prohibition_guard`
- `approval_guard`
- `tool_permission_guard`

```bash
epi policy init
epi policy init --starter-rule approval_guard --starter-rule tool_permission_guard
epi policy init --starter-rule approval_guard --open-editor
epi policy show --open-editor
epi policy validate
epi policy validate customer_refund.epi
epi policy show
epi policy show --raw
```

`epi policy validate` now gives line-and-column JSON errors, field-level schema errors, and can validate embedded `policy.json` directly from a `.epi` artifact.

Practical rule:

- store `epi_policy.json` in the same working directory where you run `epi run` or `epi record`
- EPI loads it during packing
- the sealed artifact then contains `policy.json` and `analysis.json` when applicable
- EPI stores the company rulebook as `epi_policy.json`; most users should not edit JSON manually

For the full workflow, see [`POLICY.md`](POLICY.md).

---

## `epi connect open`

Starts the local browser review workspace and the local connector bridge together, then opens the browser for you.

```bash
epi connect open
epi connect open --no-browser
epi connect open --users-file ./config/gateway-users.example.json
```

This is the simplest local path if you do not want to think about ports, servers, or HTML files.
When `--users-file` is set, the browser app shows a small local sign-in form and keeps the session token only in the current tab.

---

## `epi gateway serve`

Starts the open-source EPI AI capture gateway.

```bash
pip install "epi-recorder[gateway]"
epi gateway serve
epi gateway serve --port 9000 --storage-dir ./gateway-vault
epi gateway serve --retention-mode redacted_hashes --proxy-failure-mode fail-closed
epi gateway serve --access-token change-me
epi gateway serve --users-file ./config/gateway-users.example.json
epi gateway serve --did did:web:vendor.com --witness-url https://customer.example/witness --witness-secret "$SECRET"
epi gateway export --case-id decision::refund-123 --out reviewed.epi --storage-dir ./gateway-vault
epi gateway export --case-id decision::refund-123 --out reviewed.epi --storage-dir ./gateway-vault --did did:web:vendor.com
```

This is the lowest-friction developer entrypoint if you want EPI to act more like infrastructure than a post-hoc viewer:

- developers can point traffic at one capture endpoint
- the gateway normalizes events into the shared open capture schema
- the gateway also exposes `/capture/llm` for provider-native OpenAI-compatible, Anthropic, Gemini, LiteLLM, and generic payloads
- the gateway exposes `/v1/chat/completions` for OpenAI-compatible clients and `/v1/messages` for Anthropic-compatible clients
- the gateway persists append-only capture batches locally
- teams can still export or build `.epi` proof artifacts later

The gateway is intentionally part of the open capture/spec layer. A future enterprise control plane should sit above it, not replace it.

Operator notes:
- `/health` is the liveness/runtime-state endpoint; it also reports `did` and `witness_configured` (never the witness URL or secret)
- identity and witness work as for `record()`: `--did` (or `EPI_DID`) puts the did:web identity in `manifest.governance["did"]` of every export, and `--witness-url` / `--witness-secret` (or `EPI_WITNESS_URL` / `EPI_WITNESS_SECRET`) report each exported file, hash-only, to the customer witness ([WITNESS.md](WITNESS.md)). Delivery is outbox-first and never fails an export; `epi gateway export` prints `DID: ...` and `Witness: delivered to <url>` or `Witness: QUEUED (<reason>) — run epi witness flush`. The serve banner shows the DID and witness URL, never the secret.
- `epi gateway export` refuses a `--storage-dir` with no `cases.sqlite3`, and warns when no signing key exists (`epi keys generate`)
- `/ready` is the supported readiness probe after replay
- `--retention-mode` controls whether provider request/response bodies are stored in redacted-hash form or full content
- `--proxy-failure-mode` controls whether successful upstream proxy calls still return when EPI capture fails
- `--access-token` protects `/api/*` reviewer routes with a shared bearer token
- `--users-file` enables local browser sign-in with simple `admin`, `reviewer`, and `auditor` roles from a JSON file
- if neither `--access-token` nor `--users-file` is set, the shared reviewer APIs stay open for single-node local use

---

## `epi connect serve`

Runs a localhost bridge that the browser Setup Wizard can use to check connector access and fetch one live source record into the starter-pack flow.

```bash
epi connect serve
epi connect serve --port 8766
epi connect serve --users-file ./config/gateway-users.example.json
```

Typical use:
- easiest path: run `epi connect open`
- advanced path: start the bridge in a terminal
- open the browser setup wizard
- keep the bridge URL at `http://127.0.0.1:8765` unless you changed the port
- click `Check local bridge`, then `Fetch live record`

The bridge stays local to the machine by default and is meant for self-hosted setup flows, not public exposure.

---

## `epi keys`

Manage Ed25519 signing keys and the local trust registry.

```bash
epi keys generate
epi keys generate --name team-key
epi keys list
epi keys export default
epi keys export default --format hex
epi keys trust team-key
epi keys trust /path/to/key.pub --name external-signer
epi keys trust --from-did did:web:vendor.com --name vendor
epi keys did --domain vendor.com [--path agents/claims] [--key default]
epi keys revoke team-key
epi keys unrevoke team-key
```

Actions:

- `generate` — Create a new Ed25519 key pair in `~/.epi/keys/` and print its fingerprint (`xxxx xxxx xxxx xxxx`).
- `list` — Show all signing key pairs and pinned keys, each with its fingerprint and (for pins) `trusted` or `revoked`.
- `export` — Print a public key. Use `--format hex` to get the raw 64-character hex string (useful for DID documents).
- `trust <file> --name <name>` — Pin a public key in `~/.epi/trusted_keys/` so `epi verify` recognizes it as a known identity. `<file>` can be a PEM `.pub` file, the vendor's `did.json`, or a file holding the base64 key line printed by `epi keys export`. Prints the fingerprint to confirm with the sender by phone. Only pin a key obtained from the sender out of band, never one taken from the file you are checking.
- `trust --from-did <did:web:...>` — Resolve the DID document once (network), pin its Ed25519 key, and print a fingerprint to confirm with the vendor by phone. Only `did:web:` DIDs are accepted. After any pin, files sealed by other keys report `NOT A KEY YOU TRUST`.
- `did --domain <domain>` — Vendor side: write `did.json` for this machine's key (`--key`, default `default`) into the current folder, and print where to host it (`https://<domain>/.well-known/did.json`, or `https://<domain>/<path>/did.json` with `--path`). Refuses to overwrite an existing `did.json` without `--overwrite`.
- `did --domain` also prints the key fingerprint.
- `revoke <name>` — Mark a pinned key as revoked. Revocation applies to the **key**: every pin holding that key shows `revoked` in `epi keys list`, and files it sealed FAIL with `Status: REVOKED`.
- `unrevoke <name>` — Undo `epi keys revoke <name>`.

```text
$ epi keys did --domain vendor.example.com
[OK] Wrote did.json for: did:web:vendor.example.com
  Host it at: https://vendor.example.com/.well-known/did.json
  Free hosting: GitHub Pages or Cloudflare Pages (any static host works).
Then seal with: record(..., did="did:web:vendor.example.com") (or EPI_DID), so verifiers bind your
key to your domain.

$ epi keys trust --from-did did:web:vendor.example.com --name vendor
[OK] Trusted key from did:web:vendor.example.com: ~/.epi/trusted_keys/vendor.pub
  Fingerprint (confirm with the vendor): <fingerprint>
Files sealed by any other key now report NOT A KEY YOU TRUST. For key rotation, pin each key in the
vendor did.json.
```

Offline alternative: get one of these from the vendor out of band and pin it with `epi keys trust <file> --name vendor`:

- their `did.json` file: `epi keys trust did.json --name vendor`
- the base64 key line from `epi keys export`, saved to a file: `epi keys trust vendor.b64 --name vendor`
- their PEM public key (`~/.epi/keys/default.pub` on their machine): `epi keys trust vendor.pub --name vendor`

```text
$ epi keys trust did.json --name vendor
[OK] Trusted key: ~/.epi/trusted_keys/vendor.pub
  Fingerprint: 5a32 47ae cc11 f185  (read it to the sender by phone; it must match theirs)
```

## `epi witness status|flush|drop|serve`

Vendor side of the customer witness ([WITNESS.md](./WITNESS.md)). With
`EPI_WITNESS_URL` (or `record(..., witness_url=...)`) set, every seal queues a
hash-only report in `~/.epi/witness_outbox.jsonl` and delivers it in the
background.

- `epi witness status` — List pending, delivered and failed witness entries.
- `epi witness flush` — Retry every undelivered witness entry. Exits 1 while
  anything is still pending.
  - `--secret <str>` — HMAC secret for delivery (default: `EPI_WITNESS_SECRET`).
  - `--timeout <int>` — Per-request timeout in seconds (default: 10).
- `epi witness drop <id>` — Remove one entry from the outbox (e.g. a seal
  queued for a wrong URL, which would otherwise stay pending forever). `<id>`
  is the full id or any unique prefix, such as the 8-character id `status`
  shows; an ambiguous prefix is refused. The sealed `.epi` file is unchanged;
  the receiver simply never gets that report.
  - `--all-failed --yes` — Drop every entry that still has pending URLs
    (without `--yes` it only lists them and exits 1).

```text
$ epi witness status
...
│ 4425f106 │ 2026-10-12T09:35:00 │ 844bedb5 │ 1       │ 0         │ http://127.0.0.1:8099/: HTTP   │
│          │                     │          │         │           │ Error 401: Unauthorized        │
2 entries, 1 URLs pending.

$ epi witness flush
Failed: http://127.0.0.1:8099/ (HTTP Error 401: Unauthorized)
  The receiver rejected the secret (HTTP 401). Use the same secret as the receiver: EPI_WITNESS_SECRET or --secret.
Still pending. Fix the URL/secret and flush again, or remove an entry with: epi witness drop <id>

$ EPI_WITNESS_SECRET=SHARED_SECRET epi witness flush
Delivered: http://127.0.0.1:8099/

$ epi witness drop 4425f106     # if the URL itself was wrong
Dropped 4425f106 (workflow 844bedb5, pending: http://wrong-host:8099/)
```

Customer side: `epi witness serve` runs the witness receiver that the
vendor's `EPI_WITNESS_URL` points at. It checks the `X-EPI-Signature` HMAC,
stamps `received_at` and appends each report to `--out`, the log you later
pass to `epi verify --witness-log`.

- `epi witness serve`
  - `--host <str>` — Interface to listen on (default: `127.0.0.1`). Use
    `0.0.0.0` only behind a TLS-terminating reverse proxy.
  - `--port <int>` — Port (default: 8099). A port in use gives a one-line error.
  - `--out <path>` — Append-only witness log (default: `received.jsonl`).
  - `--secret <str>` — Shared HMAC secret (default: `EPI_WITNESS_SECRET`).
    Required unless `--insecure-no-secret` (local trials only).

```text
$ EPI_WITNESS_SECRET=SHARED_SECRET epi witness serve --out received.jsonl
Witness receiver listening on 127.0.0.1:8099 (HMAC check on)
Give the vendor:  EPI_WITNESS_URL=http://127.0.0.1:8099/
                  EPI_WITNESS_SECRET=<the same secret this receiver uses>
Witness log:      /srv/witness/received.jsonl
Check a file:     epi verify run.epi --witness-log /srv/witness/received.jsonl
Press Ctrl-C to stop.
```

## `epi review <file.epi>`

Supports human review of policy-grounded faults. Reviewers can confirm, dismiss, or skip flagged issues. The result is appended to the case file as review notes without replacing the original sealed evidence files.

```bash
epi review payment_run.epi
epi review payment_run.epi --reviewer alice@example.com --key default
epi review payment_run.epi show
epi review payment_run.epi bind --reviewer alice@example.com
```

Options:

- `--reviewer`, `-r` — Reviewer identity (email or name).
- `--key`, `-k` — Name of the signing key to use for the review signature (default: `default`).

Subcommands:

- `show` — Display the existing review record, if present.
- `bind` — Promote the latest unbound review into a signed, artifact-bound review entry.

---

## epi annex

Generate and manage EU AI Act Annex IV compliance artifacts.

| Command | Description |
|---------|-------------|
| init | Create template JSON files for all 9 sections |
| validate | Validate section JSON against Pydantic schemas |
| status | Show per-section completion and approval status |
| compile | Generate compliance-summary.json |
| sign | Ed25519 sign a section (or all) |
| verify | Verify Ed25519 signatures |
| report | Generate browser-viewable HTML compliance report |

Full docs: [ANNEX-IV.md](ANNEX-IV.md)

## Notes

- For normal Windows users, use the packaged installer for the best `.epi` opening experience.
- For developer installs from PyPI or source, `epi associate` registers a stable user launcher path and `epi doctor` reports drift when OS policy blocks registry repair.
- Policy and analysis results are embedded into the artifact as `policy.json` and `analysis.json` when available.
- For the supported shared-review deployment shape, see [`SELF-HOSTED-RUNBOOK.md`](SELF-HOSTED-RUNBOOK.md).
