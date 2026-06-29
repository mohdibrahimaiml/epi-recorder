# How to Test EPI Autonomously (Normal User Guide)

Run everything yourself with two commands. No AI tokens needed.

## Step 1: Clone the repo

```bash
git clone https://github.com/mohdibrahimaiml/epi-recorder.git
cd epi-recorder
```

## Step 2: Install dependencies

```bash
pip install -e ".[gateway]"
```

## Step 3: Run the full smoke test

```bash
python test_epi_full.py
```

You should see:

```
==================================================
  EPI Full Smoke Test Suite
==================================================

>> Phase 1: Local Python Tests
  [OK] Portal tests (13)
  [OK] AIUC-1 tests (26)
  [OK] SCITT tests (18)

>> Phase 2: Live Website (epilabs.org)
  [OK] Landing page (/)
  [OK] Pricing page
  ...

==================================================
  Results: 16 passed, 0 failed
==================================================
  All tests passed!
```

## What the smoke test covers

| Phase | What it tests |
|-------|--------------|
| 1 | 57 Python unit tests (portal, AIUC-1, SCITT) |
| 2 | Live website pages and assets on epilabs.org |
| 3 | API endpoints: health, DID, trust registry, portal |
| 4 | SCITT service: public key fetch, invalid COSE rejection |
| 5 | CLI: `epi` command works, golden artifact verifies |

## Step 4: Manual spot-checks (optional but recommended)

### Verify the golden artifact yourself

```bash
epi verify epi-recordings/aiuc1_golden_submission.epi
```

Expected output includes:
- `DECISION: PASS`
- `Trust Level: MEDIUM` (upgraded from LOW due to SCITT receipt)
- `Transparency: VERIFIED (SCITT)`

### Verify SCITT receipt cryptographically

```bash
epi scitt verify epi-recordings/aiuc1_golden_submission.epi
```

Expected output includes:
- `SCITT statement valid`
- `SCITT receipt structurally valid`
- `SCITT receipt signature verified (Ed25519)`

### Check the live SCITT service

```bash
curl https://epilabs.org/scitt/keys
```

Should return a JSON with a 64-character hex `public_key`.

### Check the DID document

```bash
curl https://epilabs.org/.well-known/did.json | jq .id
```

Should output: `"did:web:epilabs.org"`

### Upload an artifact to the web portal

1. Open https://epilabs.org/portal in your browser
2. Drag and drop `epi-recordings/aiuc1_golden_submission.epi`
3. Check the report shows green checks for integrity, signature, and AIUC-1 mapping

---

**If any step fails**, check:
- Python 3.12+ is installed: `python --version`
- You're in the repo root directory
- Internet connection is active (for live website/API tests)
- The golden artifact file exists: `ls epi-recordings/aiuc1_golden_submission.epi`
