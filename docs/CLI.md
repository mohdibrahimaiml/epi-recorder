# EPI CLI Reference (v2.8.1)

**Version:** 2.8.1  
**Primary entrypoint:** `epi`

---

## Core Commands

| Command | Purpose |
| --- | --- |
| `epi run <script.py>` | Record a Python workflow and produce a `.epi` artifact. |
| `epi record --out <file.epi> -- <cmd...>` | Record an arbitrary command with an explicit output path. |
| `epi view <file.epi>` | Open an artifact in the embedded viewer flow. |
| `epi verify <file.epi>` | Verify artifact integrity and signature state. |
| `epi analyze <file.epi>` | Show fault-analysis output without opening the viewer. |
| `epi ls` | List local recordings. |
| `epi associate` | Register file association support. Best used as a repair or developer path on Windows. |
| `epi unassociate` | Remove file association support. |
| `epi doctor` | Run self-healing diagnostics. |
| `epi keys` | Manage signing keys. |
| `epi policy` | Create and validate `epi_policy.json` rule files. |
| `epi review <file.epi>` | Confirm or dismiss policy-grounded faults. |

---

## `epi run <script.py>`

The simplest way to use EPI.

```bash
epi run my_agent.py
```

Typical outcome:
- runs the script
- records the workflow
- seals a `.epi` artifact
- performs analysis before sealing

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

In `v2.8.1`, the analyzer enforces:
- `constraint_guard`
- `sequence_guard`
- `threshold_guard`
- `prohibition_guard`

```bash
epi policy init
epi policy validate
epi policy show
```

Practical rule:

- store `epi_policy.json` in the same working directory where you run `epi run` or `epi record`
- EPI loads it during packing
- the sealed artifact then contains `policy.json` and `analysis.json` when applicable

For the full workflow, see [`POLICY.md`](POLICY.md).

---

## `epi review <file.epi>`

Supports human review of policy-grounded faults. Reviewers can confirm, dismiss, or skip flagged issues. The result is appended to the artifact as `review.json` without replacing the original sealed evidence files.

```bash
epi review payment_run.epi
epi review show payment_run.epi
```

---

## Notes

- For normal Windows users, use the packaged installer for the best `.epi` opening experience.
- For developer installs from PyPI or source, `epi associate` and `epi doctor` are the main repair paths.
- Policy and analysis results are embedded into the artifact as `policy.json` and `analysis.json` when available.
