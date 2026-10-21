# EPI Usage Guide

**Version:** 4.6.2  
**Start here for “what / where / how”:** [USER-GUIDE.md](./USER-GUIDE.md).  
This page is the short command cheat sheet. Root [README.md](../README.md) is the 60-second copy-paste.

---

## Quick start

### 1. Install

```bash
pip install epi-recorder
epi --version
```

Confirm the printed version is **4.6.2** (or newer). If PyPI lags the git tag, install from the tagged commit.

### 2. Keys (optional first run)

Signing keys are created as needed. To inspect:

```bash
epi keys list
epi keys generate --name default   # if you want an explicit key
# A reviewer pins YOUR public key (the .pub / did.json you sent), not the .epi:
#   epi keys trust sender.pub --name acme
```

Private keys live under `~/.epi/keys/` — **never commit them**.

### 3. Record (recommended APIs)

**A. Demo (no LLM API key):**

```bash
epi demo --no-browser
epi verify epi-recordings/demo_refund.epi
```

**B. Python `record()` (matches root README):**

```python
from epi_recorder import record, get_current_session

with record("demo.epi", goal="show the golden path"):
    s = get_current_session()
    s.log("tool.call", tool="lookup", id="A-1")
    s.log("decision", action="approve", reason="within limit")
```

```bash
epi verify demo.epi
epi view demo.epi
```

**C. CLI wrap a script:**

```bash
epi record --out refund.epi -- python process_refund.py
```

### 4. Verify

```bash
epi verify refund.epi
```

Typical **first-run** result (local sealer key on this machine):

- **Integrity:** Verified  
- **Signature:** Valid  
- **Identity:** often **LOCAL** or **UNKNOWN / NOT_PINNED** until org trust pin  
- **Decision:** under STANDARD, unpinned/LOCAL → **WARN · UNVERIFIED IDENTITY** (valid seal ≠ claim-ready). Under STRICT, unpinned → **FAIL**.

Scripts must rely on the exit code only with `--policy strict`: `epi verify` exits `0` on WARN.

Seal vs identity: integrity/signature answer “is the artifact internally consistent under some key?”; identity answers “do we recognize the sealer?” Anyone can rebuild the chain and re-sign.

```bash
# Customers, insurers, banks, auditors — always:
epi verify refund.epi --policy strict --witness-log received.jsonl
# (add --require-timestamp only if the vendor seals with a reachable timestamp
#  service; leave out --witness-log if no witness receiver is run)
# Dev skim (WARN if identity not org-pinned):
epi verify refund.epi --json
```

### 5. Browser verify

- **Private (no upload):** https://epilabs.org/verify/  
- **Full report (upload):** https://epilabs.org/verify/?mode=server  

Details: [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md).

---

## Advanced: `EpiRecorderSession`

Lower-level session API (still supported):

```python
from epi_recorder.api import EpiRecorderSession

with EpiRecorderSession(output_path="refund.epi", goal="Process refund REF-100") as epi:
    epi.log_step("llm.request", {"model": "gpt-4", "prompt": "Should we approve?"})
    epi.log_step("llm.response", {"output": "Yes, under $500 threshold."})
```

Prefer `record()` / wrappers for new code (see root README and [FRAMEWORK-INTEGRATIONS-5-MINUTES.md](./FRAMEWORK-INTEGRATIONS-5-MINUTES.md)).

---

## Verification results

### Exit codes

| Exit code | Meaning |
|-----------|---------|
| `0` | Policy decision pass (or non-failing outcome per policy) |
| non-zero | Fail under the selected policy (tamper, bad signature, strict identity, etc.) |

Always read integrity and signature lines separately from identity.

### JSON report (shape)

```json
{
  "facts": {
    "integrity_ok": true,
    "signature_valid": true,
    "has_signature": true,
    "mismatches": {}
  },
  "identity": {
    "status": "LOCAL",
    "name": "default",
    "detail": "…"
  },
  "decision": {
    "status": "PASS",
    "policy": "standard",
    "reason": "…"
  }
}
```

Field meanings:

- **`facts.integrity_ok`** — member hashes match; file not modified after seal  
- **`facts.signature_valid`** — Ed25519 over sealed content  
- **`identity.status`** — KNOWN / LOCAL / UNKNOWN / revoked-style states  
- **`decision`** — policy outcome (standard vs strict, etc.)

---

## Share with a customer (EPI Cloud)

Optional. Verification does not need an account.

```bash
epi cloud login
epi demo
```

Create a customer-scoped trust link on `https://cloud.epilabs.org`. Details: [CLOUD.md](./CLOUD.md).

## Enterprise kit (local files)

```bash
epi enterprise setup
epi enterprise pack your-run.epi
```

---

## Related

| Doc | Topic |
|-----|--------|
| [POLICY.md](./POLICY.md) | Policy schema and `epi policy init` |
| [CLI.md](./CLI.md) | Full command reference, including `epi cloud` |
| [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md) | Product boundaries |
| [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md) | Exact meaning of a verify result |
| [EPI_MASTER_DOCUMENTATION.md](./EPI_MASTER_DOCUMENTATION.md) | Bank / procurement briefing |
