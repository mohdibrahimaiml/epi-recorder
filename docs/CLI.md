# EPI CLI Reference (v2.8.9)

**Version:** 2.8.9  
**Primary entrypoint:** `epi`

---

## Core Commands

| Command | Purpose |
| --- | --- |
| `epi run <script.py>` | Record a Python workflow that already emits EPI steps. |
| `epi record --out <file.epi> -- <cmd...>` | Record an arbitrary command with an explicit output path. |
| `epi view <file.epi>` | Open an artifact in the embedded viewer flow. |
| `epi verify <file.epi>` | Verify artifact integrity and signature state. |
| `epi analyze <file.epi>` | Show fault-analysis output without opening the viewer. |
| `epi ls` | List local recordings. |
| `epi associate` | Register file association support. Best used as a repair or developer path on Windows. |
| `epi unassociate` | Remove file association support. |
| `epi doctor` | Run self-healing diagnostics. |
| `epi keys` | Manage signing keys. |
| `epi policy` | Create, explain, and validate `epi_policy.json` rule files. |
| `epi review <file.epi>` | Confirm or dismiss policy-grounded faults. |

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

Opens a recording using the viewer flow.

```bash
epi view my_run.epi

# View by name from ./epi-recordings
epi view my_run
```

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

---

## `epi doctor`

Runs local diagnostics and repairs common setup issues.

```bash
epi doctor
```

---

## `epi policy`

Creates and validates `epi_policy.json` files that define acceptable agent behavior.

In `v2.8.9`, `epi policy init` is the guided front door for policy. It asks a small number of business-language questions and writes the machine-readable rulebook for you.

The analyzer enforces:
- `constraint_guard`
- `sequence_guard`
- `threshold_guard`
- `prohibition_guard`
- `approval_guard`
- `tool_permission_guard`

```bash
epi policy init
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

For the proposed enterprise direction after `v2.8.9`, see [`POLICY-V2-DESIGN.md`](POLICY-V2-DESIGN.md).

---

## `epi review <file.epi>`

Supports human review of policy-grounded faults. Reviewers can confirm, dismiss, or skip flagged issues. The result is appended to the artifact as `review.json` without replacing the original sealed evidence files.

```bash
epi review payment_run.epi
epi review payment_run.epi show
```

---

## Notes

- For normal Windows users, use the packaged installer for the best `.epi` opening experience.
- For developer installs from PyPI or source, `epi associate` registers a stable user launcher path and `epi doctor` reports drift when OS policy blocks registry repair.
- Policy and analysis results are embedded into the artifact as `policy.json` and `analysis.json` when available.
