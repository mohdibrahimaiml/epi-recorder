# EPI CLI Reference (v3.0.2)

**Version:** 3.0.2
**Primary entrypoint:** `epi`

---

## Start Here

Start with `epi demo`. It is the primary developer front door if you want to capture one AI run, open it in the browser, and verify the resulting `.epi` artifact in minutes.

If you prefer zero local setup, use the Colab notebook linked from [README.md](../README.md).

`epi view` is the canonical EPI case review experience. Older desktop viewer projects remain legacy/internal compatibility surfaces and are not the recommended front door.

---

## Core Commands

| Command | Purpose |
| --- | --- |
| `epi demo` | Start the sample refund workflow and the full repro loop in the browser. Recommended first run. |
| `epi run <script.py>` | Record a Python workflow that already emits EPI steps. |
| `epi record --out <file.epi> -- <cmd...>` | Record an arbitrary command with an explicit output path. |
| `epi view <file.epi>` | Open a case file in the browser review view. |
| `epi verify <file.epi>` | Verify case file integrity and signature state. |
| `epi share <file.epi>` | Upload a hosted browser link for a portable case file. |
| `epi analyze <file.epi>` | Show fault-analysis output without opening the case view. |
| `epi ls` | List local recordings. |
| `epi associate` | Register file association support. Best used as a repair or developer path on Windows. |
| `epi unassociate` | Remove file association support. |
| `epi doctor` | Run self-healing diagnostics. |
| `epi keys` | Manage signing keys. |
| `epi policy` | Create, explain, and validate `epi_policy.json` rule files. |
| `epi review <file.epi>` | Confirm or dismiss policy-grounded issues and save human review notes. |

### Advanced / operator commands

| Command | Purpose |
| --- | --- |
| `epi gateway serve` | Start the open-source AI capture gateway for low-friction developer adoption. |
| `epi gateway export` | Export one shared gateway-backed case to a portable `.epi` case file. |
| `epi connect open` | Start the local browser review workspace and connector bridge together. |
| `epi connect serve` | Run only the local connector bridge for the browser Setup Wizard. |

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

`epi view --extract` now writes a self-contained `viewer.html` with the browser runtime inlined, including vendored JSZip, so the extracted review page has no external script dependencies and remains offline/air-gapped safe.

---

## `epi associate` / `epi unassociate`

Registers `.epi` files with the operating system so supported desktop environments can open them with EPI. On Windows, the packaged installer is the recommended path for reliable double-click behavior. `epi associate` remains useful as a repair or developer fallback.

```bash
epi associate
epi unassociate
```

---

## `epi verify <file.epi>`

Recalculates hashes and checks the Ed25519 signature.

Options:
- `--verbose` shows detailed verification checks
- `--json` prints machine-readable output

```bash
epi verify demo.epi
[OK] Integrity: OK (Entire Archive)
[OK] Signature: Valid (Identity Embedded)
[OK] Checks: 24/24 passed
```

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

In `v3.0.2`, `epi policy init` is the guided front door for policy. It asks a small number of business-language questions and writes the machine-readable rulebook for you.
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

For the proposed enterprise direction after `v3.0.2`, see [`POLICY-V2-DESIGN.md`](POLICY-V2-DESIGN.md).

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
pip install epi-recorder
epi gateway serve
epi gateway serve --port 9000 --storage-dir ./gateway-vault
epi gateway serve --retention-mode redacted_hashes --proxy-failure-mode fail-closed
epi gateway serve --access-token change-me
epi gateway serve --users-file ./config/gateway-users.example.json
epi gateway export --case-id decision::refund-123 --out reviewed.epi --storage-dir ./gateway-vault
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
- `/health` is the liveness/runtime-state endpoint
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

## `epi review <file.epi>`

Supports human review of policy-grounded faults. Reviewers can confirm, dismiss, or skip flagged issues. The result is appended to the case file as review notes without replacing the original sealed evidence files.

```bash
epi review payment_run.epi
epi review payment_run.epi show
```

---

## Notes

- For normal Windows users, use the packaged installer for the best `.epi` opening experience.
- For developer installs from PyPI or source, `epi associate` registers a stable user launcher path and `epi doctor` reports drift when OS policy blocks registry repair.
- Policy and analysis results are embedded into the artifact as `policy.json` and `analysis.json` when available.
- For the open-capture / enterprise-control-plane split, see [`OPEN-CORE-ARCHITECTURE.md`](OPEN-CORE-ARCHITECTURE.md).
