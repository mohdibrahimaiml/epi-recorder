# Prompt: Autonomous EPI Verification Agent

Copy and paste this entire block into any AI assistant (Kimi, Claude, GPT, etc.). It will run all tests without further input.

---

```
You are an autonomous software verification agent. Your task is to comprehensively test the EPI (Episodic Process Integrity) project and report whether everything is working correctly.

## CONTEXT

EPI is an open-source protocol for cryptographically recording and verifying AI system behavior. It consists of:
- A Python package (`epi-recorder`) with CLI tools
- A FastAPI verify portal served at https://epilabs.org
- A SCITT (Supply Chain Integrity, Transparency and Trust) transparency service
- AIUC-1 compliance mapping across 6 trust domains

Repository: https://github.com/mohdibrahimaiml/epi-recorder
Live site: https://epilabs.org

## YOUR TASK

Run ALL of the following tests and produce a structured report. Do not ask the user for clarification. Execute everything autonomously.

### Phase 1: Environment Setup
1. Check if the current directory is the epi-recorder repo. If not, clone it from https://github.com/mohdibrahimaiml/epi-recorder.git
2. Verify Python 3.12+ is available
3. Verify dependencies are installed (pip install -e ".[gateway]" if needed)

### Phase 2: Local Unit Tests
Run these pytest suites and report pass/fail counts:
- tests/test_verify_portal.py (13 tests)
- tests/test_aiuc1_mapping.py (26 tests)
- tests/test_scitt.py (18 tests)

### Phase 3: Live Website Verification
Use curl or HTTP requests to verify these return HTTP 200:
- https://epilabs.org/ (landing page)
- https://epilabs.org/pricing.html
- https://epilabs.org/technology.html
- https://epilabs.org/css/style.css
- https://epilabs.org/assets/logo.png

### Phase 4: API Endpoint Verification
Verify these endpoints return correct data:
- GET https://epilabs.org/health → should contain {"status":"ok"}
- GET https://epilabs.org/.well-known/did.json → should contain "did:web:epilabs.org"
- GET https://epilabs.org/.well-known/epi-trust-registry.json → should contain "scitt_services"
- GET https://epilabs.org/portal → should return HTML with HTTP 200

### Phase 5: SCITT Transparency Service
- GET https://epilabs.org/scitt/keys → should return JSON with "public_key" field (64 hex chars)
- POST https://epilabs.org/scitt/register with invalid COSE payload → should return 400 (not 503)

### Phase 6: CLI Smoke Tests
- Run: `epi --version` or `python -m epi_cli --version` → should succeed
- Run: `epi verify epi-recordings/aiuc1_golden_submission.epi --json` → should succeed
- Run: `epi scitt verify epi-recordings/aiuc1_golden_submission.epi` → should show "SCITT receipt signature verified"

### Phase 7: Golden Artifact Deep Check
Verify the golden artifact contains:
- A valid manifest with Ed25519 signature
- SCITT statement (artifacts/scitt/statement.cbor)
- SCITT receipt (artifacts/scitt/receipt.cbor)
- AIUC-1 mapping in the verification report

## OUTPUT FORMAT

Produce a report in this exact format:

```
# EPI Verification Report
**Date:** [current date]
**Agent:** [your name]
**Repository:** [repo path or URL]

## Summary
- Total checks: [N]
- Passed: [N]
- Failed: [N]
- Status: [PASS / PARTIAL / FAIL]

## Phase 1: Environment
| Check | Result |
|-------|--------|
| Repo available | ✅/❌ |
| Python 3.12+ | ✅/❌ |
| Dependencies installed | ✅/❌ |

## Phase 2: Local Tests
| Test Suite | Count | Passed | Failed |
|------------|-------|--------|--------|
| Portal tests | 13 | N | N |
| AIUC-1 tests | 26 | N | N |
| SCITT tests | 18 | N | N |

## Phase 3: Live Website
| Page | Status | HTTP Code |
|------|--------|-----------|
| / | ✅/❌ | [code] |
| ... | ... | ... |

## Phase 4: API Endpoints
| Endpoint | Status | Notes |
|----------|--------|-------|
| /health | ✅/❌ | ... |
| ... | ... | ... |

## Phase 5: SCITT Service
| Check | Status | Notes |
|-------|--------|-------|
| /keys returns public_key | ✅/❌ | ... |
| /register rejects bad COSE | ✅/❌ | ... |

## Phase 6: CLI
| Command | Status | Notes |
|---------|--------|-------|
| epi --version | ✅/❌ | ... |
| epi verify golden artifact | ✅/❌ | ... |
| epi scitt verify golden artifact | ✅/❌ | ... |

## Phase 7: Golden Artifact
| Check | Status |
|-------|--------|
| Manifest signed | ✅/❌ |
| SCITT statement present | ✅/❌ |
| SCITT receipt present | ✅/❌ |
| AIUC-1 mapping present | ✅/❌ |

## Issues Found
[List any failures with specific error messages]

## Recommendations
[If any checks failed, suggest fixes]
```

## RULES
1. Do NOT ask the user questions. Execute autonomously.
2. If a command fails, capture the error message and continue with remaining tests.
3. Use the local repo if already cloned; clone only if necessary.
4. For HTTP tests, use curl, wget, or Python urllib — whatever is available.
5. Report honestly. If something fails, say it failed and include the error.
```

---

## How to use this prompt

1. **With Kimi Code CLI**: Paste the entire prompt block above. Kimi will execute all tests automatically.

2. **With Claude/GPT web**: Paste the prompt. The AI will guide you through running commands (web AIs can't execute shell commands directly, but they will give you the exact commands to copy-paste).

3. **With a local agent**: If you have a local AI agent with tool access, this prompt tells it exactly what files to read, what commands to run, and what format to report in.
