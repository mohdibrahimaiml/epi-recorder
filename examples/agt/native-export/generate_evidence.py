#!/usr/bin/env python3
"""
Generate native Microsoft AGT evidence and import it into EPI.

Demonstrates the end-to-end AGT -> EPI pipeline using Microsoft's
agent-governance-toolkit SDK (v4.1.0).

Prerequisites:
    pip install epi-recorder
    pip install agent-governance-toolkit-core

Then run:
    python examples/agt/native-export/generate_evidence.py
    epi import agt examples/agt/native-export/agt_export.json --out case.epi
    epi verify case.epi
    epi view case.epi
"""

import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="agentmesh-platform is deprecated")

from agentmesh.services.audit import AuditService

OUTPUT = Path(__file__).resolve().parent / "agt_export.json"


def main():
    audit = AuditService()

    audit.log_action(
        "did:web:loan-agent.acme-corp.com",
        "assess_credit_risk",
        resource="loan-app-LN-4512",
        data={"tool": "fico_credit_model_v3", "fico_score": 712, "dti_ratio": 28, "loan_amount": 75000},
    )
    audit.log_action(
        "did:web:loan-agent.acme-corp.com",
        "generate_decision_letter",
        resource="loan-app-LN-4512",
        data={"model": "gpt-4-turbo", "decision": "approved", "interest_rate": 6.75},
    )
    audit.log_policy_decision(
        "did:web:loan-agent.acme-corp.com", "assess_credit_risk",
        decision="allow", policy_name="LENDING-POLICY-V2-ART3",
        data={"subject_ref": "LN-4512", "reason": "FICO 712 >= 680"},
    )
    audit.log_policy_decision(
        "did:web:loan-agent.acme-corp.com", "approve_above_threshold",
        decision="deny", policy_name="EUAI-ART9-RISK",
        data={"subject_ref": "LN-4512", "violation": "high",
              "reason": "$75k exceeds $50k auto-approval limit"},
    )

    export = audit._log.export()
    OUTPUT.write_text(json.dumps(export, indent=2, default=str))

    print(f"Written: {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    print(f"  Entries: {export['entry_count']}")
    for e in export["entries"]:
        pd = e.get("policy_decision", "N/A")
        print(f"    [{e['event_type']}] {e['action']}  decision={pd}")
    print()
    print("Import with:")
    print(f"  epi import agt {OUTPUT} --out case.epi")
    print("  epi verify case.epi")


if __name__ == "__main__":
    main()
