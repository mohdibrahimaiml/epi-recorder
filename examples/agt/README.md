# AGT -> EPI Examples

This directory demonstrates importing Microsoft Agent Governance Toolkit (AGT)
evidence into EPI portable forensic artifacts.

## Quick start (no AGT SDK needed)

```bash
pip install epi-recorder
cd epi-recorder
epi import agt examples/agt/native-export/sample_export.json --out case.epi
epi verify case.epi
epi view case.epi
```

## Native AGT export demo (requires AGT SDK)

```bash
# Install AGT
pip install agent-governance-toolkit-core

# Generate evidence and import
python examples/agt/native-export/generate_evidence.py
epi import agt examples/agt/native-export/agt_export.json --out case.epi
epi verify case.epi
```

## What the native export contains

The script uses Microsoft's actual `AuditService` to log:
- **agent_action**: FICO credit check (score 712, DTI 28%)
- **agent_action**: GPT-4 decision letter generation
- **policy_decision: allow**: LENDING-POLICY-V2-ART3 passed
- **policy_decision: deny**: EUAI-ART9-RISK triggered ($75k exceeds $50k threshold)

The EPI adapter maps these to `tool.call` and `policy.check` step kinds,
extracts the matched rule from AGT's `data.policy_name`, and preserves all
raw AGT evidence (including the Merkle chain root) inside the .epi artifact.

## Other input formats

```bash
# AGT evidence directory
epi import agt examples/agt/evidence-dir --out case.epi

# AGT neutral bundle
epi import agt examples/agt/sample_bundle.json --out case.epi

# AGT import manifest
epi import agt examples/agt/manifest-input/agt_import_manifest.json --out case.epi
```

## Expected output

After import, `epi verify` shows:

```
Integrity:    Verified
Signature:    Valid
Forensic:     PASS
```

The extracted `review/` folder contains:
- `viewer.html` - browser-viewable forensic report
- `steps.jsonl` - mapped agent steps
- `artifacts/agt/` - raw AGT evidence preserved verbatim
