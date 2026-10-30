#!/usr/bin/env python3
"""
Generate realistic sector demo .epi artifacts with a live LLM (Groq) or mock fallback.

Requires:
  GROQ_API_KEY (optional; falls back to mock LLM if unset or unavailable)
  pip install langchain-groq langchain-core epi-recorder

Outputs (git-allowable under docs/assets/, site/assets/demo/, and examples/):
  1. demo-insurance-claim-adjudication.epi
  2. demo-finance-loan-underwriter.epi
  3. demo-healthcare-clinical-triage.epi
  4. demo-legal-contract-review.epi
  5. demo-banking-aml.epi
  6. demo-hiring-screening.epi
  7. demo-insurance-underwriting.epi
  8. demo-lending-affordability.epi

The .epi is the deliverable; no HTML export is written (see
docs/assets/SECTOR_DEMOS.md).

Usage:
  python scripts/generate_sector_demo_epis.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import zipfile
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "assets"
SITE_DEMO_DIR = ROOT / "site" / "assets" / "demo"
WEBSITE_DEMO_DIR = ROOT / "website" / "assets" / "demo"
EXAMPLES_DIR = ROOT / "examples"
DEMO_DIR = ROOT / "demo_workflows"


def _require_groq() -> str:
    key = (os.environ.get("GROQ_API_KEY") or "").strip()
    return key


def _llm_invoke(api_key: str, system: str, user: str, fallback_text: str) -> str:
    if not api_key:
        return fallback_text

    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser
        from langchain_groq import ChatGroq
        from epi_recorder.adapters.langchain import EpiCallbackHandler
        from epi_recorder.api import get_current_session

        session = get_current_session()
        handler = EpiCallbackHandler(session) if session else None
        llm = ChatGroq(
            model=os.environ.get("EPI_DEMO_GROQ_MODEL", "llama-3.1-8b-instant"),
            api_key=api_key,
            temperature=0.2,
        )
        prompt = ChatPromptTemplate.from_messages(
            [("system", system), ("human", "{input}")]
        )
        chain = prompt | llm | StrOutputParser()
        cfg = {"callbacks": [handler]} if handler else {}
        return chain.invoke({"input": user}, config=cfg)
    except Exception as e:
        print(f"  [LLM Fallback triggered due to error: {e}]", file=sys.stderr)
        return fallback_text


def _tool(epi, name: str, tool_input, output, *, ok: bool = True, error: str | None = None):
    cid = str(uuid4())
    epi.log(
        "tool.call",
        {"tool": name, "name": name, "tool_name": name, "input": tool_input, "call_id": cid},
    )
    if ok:
        epi.log(
            "tool.response",
            {"tool": name, "name": name, "tool_name": name, "output": output, "ok": True, "call_id": cid},
        )
    else:
        epi.log(
            "tool.response",
            {
                "tool": name,
                "name": name,
                "tool_name": name,
                "ok": False,
                "error": error or "tool failed",
                "call_id": cid,
            },
        )


def _leak_scan(path: Path) -> list[str]:
    from epi_core.container import EPIContainer
    import tempfile

    inner = Path(tempfile.mkdtemp()) / "inner.zip"
    EPIContainer.extract_inner_payload(path, inner)
    hits: list[str] = []
    with zipfile.ZipFile(inner) as zf:
        for name in zf.namelist():
            data = zf.read(name)
            if b"gsk_" in data or b"GROQ_API_KEY" in data:
                hits.append(name)
    return hits


def _seal_and_check(path: Path) -> None:
    hits = _leak_scan(path)
    if hits:
        raise RuntimeError(f"Secret material found in {path}: {hits}")
    print(f"  sealed {path.name}  size={path.stat().st_size}  CLEAN")


def _sign_demo_approval(
    path: Path,
    *,
    approval_id: str,
    action: str,
    reason: str,
) -> dict:
    """Sign the demo's human approval with a throwaway key, labelled DEMO KEY.

    A public sample cannot carry a real person's signature. This is a genuine
    Ed25519 signature by a key generated for this build, marked `demo_key` and
    named so nobody mistakes it for a real approver. Pin the printed fingerprint
    with `epi approvers add` to see it classified as `human_signed`.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from epi_core.keys import key_fingerprint
    from epi_core.review import ReviewRecord, add_review_to_artifact, make_approval_entry

    key = Ed25519PrivateKey.generate()
    pub_hex = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    fingerprint = key_fingerprint(pub_hex, grouped=False)

    record = ReviewRecord(
        reviewed_by="EPI Demo Approver",
        reviews=[
            make_approval_entry(
                approval_id=approval_id,
                decision="approve",
                action=action,
                reason=reason,
                approver_name="DEMO KEY - EPI Demo Approver (not a real person)",
                key_fingerprint_hex=fingerprint,
                demo_key=True,
            )
        ],
        reviewer_identity={
            "type": "name",
            "value": "EPI Demo Approver",
            "role": "Approver",
            "org": "EPI demo (synthetic)",
            "verified": False,
        },
    )
    stamp = add_review_to_artifact(path, record, private_key=key, timestamp=True) or {}

    stamp_status = stamp.get("status", "absent")
    stamp_time = stamp.get("gen_time") or "-"
    print(f"  approval DEMO KEY  fp={fingerprint}")
    print(f"  approval independent time: {stamp_status} {stamp_time} {stamp.get('tsa_url') or ''}")
    return {
        "fingerprint": fingerprint,
        "timestamp_status": stamp_status,
        "timestamp_gen_time": stamp_time,
        "timestamp_tsa": stamp.get("tsa_url") or "",
    }


# -----------------------------------------------------------------------------
# 1. Finance Loan Underwriter
# -----------------------------------------------------------------------------
def finance_loan(api_key: str, out: Path) -> None:
    from epi_recorder import record

    with record(
        out,
        goal="Underwrite consumer loan application APP-78421",
        workflow_name="Finance · Loan Underwriter Agent",
        tags=["demo", "finance", "loan", "underwriting"],
        notes="SIMULATED DEMO — Realistic demo: credit pull, income verify, policy rules, LLM decision.",
    ) as epi:
        shutil.copy2(ROOT / "demo_policies" / "finance_loan_policy.json", epi.temp_dir / "epi_policy.json")
        epi.log(
            "agent.run.start",
            {
                "agent_name": "LoanUnderwriterAgent",
                "domain": "finance",
                "user_input": "Underwrite personal loan for Jordan Lee, $22,000 @ 36 months",
                "goal": "Approve or deny with defensible evidence trail",
                "risk_class": "credit_decision",
            },
        )
        epi.log(
            "policy.check",
            {
                "constraint": "credit_score_minimum_check",
                "status": "passed",
                "policy_ref": "CREDIT-BOX-2026.03",
                "min_fico": 680,
                "applicant_fico": 714,
                "detail": "FICO score 714 satisfies credit box minimum requirement of 680.",
            },
        )
        _tool(
            epi,
            "crm.fetch_application",
            {"application_id": "APP-78421"},
            {
                "applicant": "Jordan Lee",
                "requested_amount_usd": 22000,
                "term_months": 36,
                "stated_income_usd": 78000,
                "employment": "W2 · software engineer · 2.4 years",
                "purpose": "debt consolidation",
            },
        )
        _tool(
            epi,
            "bureau.soft_pull_credit",
            {"applicant_id": "APP-78421", "bureau": "Equifax-soft"},
            {
                "fico": 714,
                "utilization": 0.31,
                "delinquencies_24m": 0,
                "inquiries_6m": 2,
                "open_trades": 7,
            },
        )
        _tool(
            epi,
            "payroll.verify_income",
            {"employer": "Northline Systems", "stated_income_usd": 78000},
            {"verified_income_usd": 76500, "method": "payroll_api", "confidence": 0.91},
        )
        _tool(
            epi,
            "policy.evaluate_credit_box",
            {
                "min_fico": 680,
                "dti_benchmark": 0.42,
                "max_amount_usd": 35000,
            },
            {
                "in_box": True,
                "estimated_dti": 0.29,
                "flags": [],
            },
        )
        fallback = "APPROVE. Applicant Jordan Lee meets credit box criteria (FICO 714, low DTI 29%). Risk class: Low."
        decision = _llm_invoke(
            api_key,
            "You are a cautious consumer-loan underwriter. Reply with APPROVE or DENY, "
            "a one-sentence reason, and a risk note. No PII beyond what is given. Be concise.",
            "Applicant Jordan Lee. Requested $22,000 / 36 mo debt consolidation. "
            "FICO 714, utilization 31%, DTI ~29%, verified income $76,500. "
            "In credit box. Decision?",
            fallback,
        )
        epi.log(
            "agent.decision",
            {
                "decision": "APPROVE" if "APPROVE" in decision.upper() else "DENY",
                "determination": "APPROVE" if "APPROVE" in decision.upper() else "DENY",
                "rationale": decision,
                "application_id": "APP-78421",
                "policy_version": "credit-box-2026.03",
            },
        )
        epi.log(
            "agent.approval.request",
            {
                "action": "issue_loan_commitment",
                "application_id": "APP-78421",
                "amount_usd": 22000,
            },
        )
        epi.log(
            "agent.approval.response",
            {
                "action": "issue_loan_commitment",
                "decision": "approved",
                "status": "approved",
                "approved": True,
                "reviewer": "Marcus Vance (Lead Loan Underwriter)",
            },
        )
        epi.log(
            "agent.run.end",
            {"status": "completed", "application_id": "APP-78421"},
        )
    _seal_and_check(out)


# -----------------------------------------------------------------------------
# 2. Healthcare Clinical Triage
# -----------------------------------------------------------------------------
def healthcare_triage(api_key: str, out: Path) -> None:
    from epi_recorder import record

    with record(
        out,
        goal="Triage virtual-care intake for adult with chest discomfort",
        workflow_name="Healthcare · Clinical Triage Agent",
        tags=["demo", "healthcare", "triage", "clinical"],
        notes="SIMULATED DEMO — Demo only — not medical advice. Escalation path logged as evidence.",
    ) as epi:
        shutil.copy2(ROOT / "demo_policies" / "healthcare_triage_policy.json", epi.temp_dir / "epi_policy.json")
        epi.log(
            "agent.run.start",
            {
                "agent_name": "ClinicalTriageAgent",
                "domain": "healthcare",
                "user_input": "Adult patient reports intermittent chest pressure for 2 hours",
                "goal": "Route to ED / urgent care / nurse line with documented red flags",
                "disclaimer": "not_a_diagnosis",
            },
        )
        epi.log(
            "policy.check",
            {
                "constraint": "clinical_triage_red_flag_check",
                "status": "flagged",
                "policy_ref": "TRIAGE-PROTO-CHEST-PAIN-v4",
                "symptom": "chest_pressure",
                "duration_hours": 2,
                "detail": "Chest pressure in patient with CV risk factors triggers mandatory emergency care routing.",
            },
        )
        _tool(
            epi,
            "ehr.fetch_intake",
            {"encounter_id": "ENC-90312"},
            {
                "chief_complaint": "intermittent chest pressure × 2h",
                "age": 54,
                "sex": "M",
                "history": ["hypertension", "hyperlipidemia"],
                "meds": ["lisinopril", "atorvastatin"],
            },
        )
        _tool(
            epi,
            "symptom.red_flag_screen",
            {
                "symptoms": ["chest_pressure", "mild_dyspnea_on_exertion"],
                "duration_hours": 2,
            },
            {
                "red_flags": ["possible_acs_symptoms"],
                "severity": "high",
                "recommended_disposition": "ED_now",
            },
        )
        _tool(
            epi,
            "protocol.lookup",
            {"protocol_id": "chest-pain-adult-v4"},
            {
                "name": "Adult chest pain triage",
                "action_if_acs_risk": "Advise emergency care; do not delay for televisit",
            },
        )
        fallback = "RECOMMENDATION: Seek immediate Emergency Department evaluation. Chest pain in patient with cardiovascular risk factors requires urgent in-person medical assessment. This is an automated triage recommendation, not a final medical diagnosis."
        advice = _llm_invoke(
            api_key,
            "You are a clinical triage assistant (not a doctor). Given tools already "
            "flagged high ACS risk, recommend disposition. Be clear, urgent, and "
            "include 'not a diagnosis' disclaimer. 3-5 sentences max.",
            "54M with HTN/HLD, 2h intermittent chest pressure, mild DOE. "
            "Red-flag screen: possible ACS, severity high, disposition ED_now. "
            "What should the virtual-care agent tell the patient?",
            fallback,
        )
        epi.log(
            "agent.decision",
            {
                "decision": "ED_now",
                "determination": "ED_now",
                "disposition": "ED_now",
                "message_to_patient": advice,
                "rationale": advice,
                "protocol_id": "chest-pain-adult-v4",
                "human_escalation_required": True,
            },
        )
        epi.log(
            "agent.approval.request",
            {
                "action": "release_triage_message",
                "reason": "High-risk disposition requires nurse confirmation before send",
            },
        )
        epi.log(
            "agent.approval.response",
            {
                "action": "release_triage_message",
                "decision": "approved",
                "status": "approved",
                "approved": True,
                "reviewer": "Dr. Elena Patel (Clinical Lead)",
            },
        )
        epi.log("agent.run.end", {"status": "completed", "encounter_id": "ENC-90312"})
    _seal_and_check(out)


# -----------------------------------------------------------------------------
# 3. Insurance Claim Adjudication
# -----------------------------------------------------------------------------
def insurance_claim(api_key: str, out: Path) -> None:
    from epi_recorder import record

    with record(
        out,
        goal="Adjudicate water-damage claim CLM-48219",
        workflow_name="Insurance · Claim Adjudication Agent",
        tags=["demo", "insurance", "claims", "adjudication"],
        notes="SIMULATED DEMO — Homeowners policy line-item audit against policy limits.",
    ) as epi:
        shutil.copy2(ROOT / "demo_policies" / "insurance_claim_policy.json", epi.temp_dir / "epi_policy.json")
        epi.log(
            "agent.run.start",
            {
                "agent_name": "ClaimsAdjudicationAgent",
                "domain": "insurance",
                "user_input": "Adjudicate claim CLM-48219: burst pipe under kitchen sink, $4,750 estimate",
                "policy_number": "HO3-884102",
            },
        )
        epi.log(
            "policy.check",
            {
                "constraint": "policy_coverage_limit_check",
                "status": "passed",
                "policy_ref": "HO3-884102-SEC1",
                "dwelling_limit_usd": 450000,
                "claim_amount_usd": 4750,
                "detail": "Claim estimate $4,750 is within $450,000 policy dwelling limit.",
            },
        )
        _tool(
            epi,
            "policy_db.get_coverages",
            {"policy_number": "HO3-884102"},
            {
                "dwelling_limit_usd": 450000,
                "water_discharge_endorsement": True,
                "deductible_usd": 500,
                "status": "active",
            },
        )
        _tool(
            epi,
            "adjuster.parse_estimate",
            {"estimate_id": "EST-1104"},
            {
                "contractor": "QuickDry Restoration",
                "line_items": [
                    {"desc": "Water extraction", "amount": 1200},
                    {"desc": "Drywall & vanity repair", "amount": 2800},
                    {"desc": "Plumbing repair", "amount": 750},
                ],
                "total_usd": 4750,
            },
        )
        _tool(
            epi,
            "fraud.anomaly_check",
            {"claim_id": "CLM-48219", "contractor": "QuickDry Restoration"},
            {"risk_score": 0.08, "flagged": False, "reason": "contractor verified, normal rates"},
        )
        fallback = "APPROVE CLAIM CLM-48219. Water line burst is covered under Policy HO3-884102. Recommended payout: $4,250 after $500 deductible."
        rationale = _llm_invoke(
            api_key,
            "You are a claims adjudication assistant. State APPROVE or DENY, payable amount "
            "(estimate minus deductible), and one short sentence explaining coverage. Concise.",
            "Claim CLM-48219, total $4,750. Covered water discharge, $500 deductible. "
            "Low fraud risk (0.08). What is the adjudication determination?",
            fallback,
        )
        epi.log(
            "agent.decision",
            {
                "decision": "APPROVE",
                "determination": "APPROVE",
                "gross_claim_usd": 4750,
                "deductible_usd": 500,
                "net_payable_usd": 4250,
                "rationale": rationale,
            },
        )
        epi.log(
            "agent.approval.request",
            {
                "action": "issue_payout_check",
                "approval_id": "payout-CLM-48219",
                "claim_id": "CLM-48219",
                "amount_usd": 4250,
            },
        )
        epi.log(
            "agent.approval.response",
            {
                "action": "issue_payout_check",
                "decision": "approved",
                "status": "approved",
                "approved": True,
                "reviewer": "David Ross (Senior Claims Adjuster)",
            },
        )
        epi.log("agent.run.end", {"status": "completed", "claim_id": "CLM-48219"})
    _seal_and_check(out)
    _sign_demo_approval(
        out,
        approval_id="payout-CLM-48219",
        action="issue_payout_check",
        reason="Coverage confirmed under HO3-884102; net payable $4,250 after the $500 deductible. "
        "Signed by a demo key generated for this sample build - not a real person.",
    )


# -----------------------------------------------------------------------------
# 4. Legal Contract Review
# -----------------------------------------------------------------------------
def legal_contract(api_key: str, out: Path) -> None:
    from epi_recorder import record

    with record(
        out,
        goal="Screen vendor MSA for unacceptable risk clauses",
        workflow_name="Legal · Contract Review Agent",
        tags=["demo", "legal", "contracts", "risk"],
        notes="SIMULATED DEMO — Compares vendor MSA against internal legal playbook guidelines.",
    ) as epi:
        shutil.copy2(ROOT / "demo_policies" / "legal_contract_policy.json", epi.temp_dir / "epi_policy.json")
        epi.log(
            "agent.run.start",
            {
                "agent_name": "ContractReviewAgent",
                "domain": "legal",
                "user_input": "Screen MSA-2026-441 against SaaS buyer playbook v7",
                "playbook_version": "saas-vendor-v7",
            },
        )
        epi.log(
            "policy.check",
            {
                "constraint": "legal_playbook_liability_cap_check",
                "status": "flagged",
                "policy_ref": "PLAYBOOK-SAAS-VENDOR-V7",
                "max_allowed_multiplier": "12mo fees",
                "contract_multiplier": "3x annual fees",
                "detail": "Vendor MSA specifies 3x annual fees liability cap, exceeding 12-month fee cap guideline.",
            },
        )
        _tool(
            epi,
            "doc.extract_clauses",
            {"doc_id": "MSA-2026-441"},
            {
                "governing_law": "Delaware",
                "limitation_of_liability": "3x annual fees",
                "indemnity": "Mutual IP indemnity",
                "auto_renew": "60-day notice required",
                "data_processing": "GDPR SCCs included",
            },
        )
        _tool(
            epi,
            "playbook.compare",
            {"playbook_id": "saas-vendor-v7"},
            {
                "findings": [
                    {
                        "clause": "limitation_of_liability",
                        "status": "flagged",
                        "issue": "Playbook requires 12mo fees cap; contract specifies 3x annual fees.",
                    },
                    {
                        "clause": "auto_renew",
                        "status": "passed",
                        "issue": "60-day notice satisfies 30-day minimum rule.",
                    },
                ]
            },
        )
        fallback = "RECOMMENDATION: Negotiate before sign. Key findings: Liability cap 3x annual fees (playbook prefers 12mo); mutual IP indemnity acceptable. Note: This analysis does not constitute formal legal advice."
        memo = _llm_invoke(
            api_key,
            "You are a commercial contracts assistant (not a lawyer). Summarize material "
            "risks vs playbook and give negotiation asks. Use short bullets. Include "
            "'not legal advice' once.",
            "MSA-2026-441 vs saas-vendor-v7. Findings: liability cap 3x annual fees (playbook "
            "wants 12mo); auto-renew with notice; mutual IP indemnity. "
            "Draft counsel-ready memo bullets.",
            fallback,
        )
        epi.log(
            "agent.decision",
            {
                "decision": "negotiate_before_sign",
                "recommendation": "negotiate_before_sign",
                "memo": memo,
                "rationale": memo,
                "blocking_issues": 1,
                "doc_id": "MSA-2026-441",
            },
        )
        epi.log(
            "agent.approval.request",
            {
                "action": "send_redline_package",
                "doc_id": "MSA-2026-441",
                "to_role": "general_counsel",
            },
        )
        epi.log(
            "agent.approval.response",
            {
                "action": "send_redline_package",
                "decision": "approved",
                "status": "approved",
                "approved": True,
                "reviewer": "Rachel Sterling (General Counsel)",
            },
        )
        epi.log("agent.run.end", {"status": "completed", "doc_id": "MSA-2026-441"})
    _seal_and_check(out)


# -----------------------------------------------------------------------------
# 5. Banking AML (Anti-Money Laundering)
# -----------------------------------------------------------------------------
def banking_aml(api_key: str, out: Path) -> None:
    from epi_recorder import record

    with record(
        out,
        goal="Screen wire transfer TX-99120 for AML and BSA compliance threshold",
        workflow_name="Banking · AML Transaction Monitoring Agent",
        tags=["demo", "banking", "aml", "bsa", "compliance"],
        notes="SIMULATED DEMO — International wire transfer above $10,000 threshold check.",
    ) as epi:
        shutil.copy2(ROOT / "demo_policies" / "banking_aml_policy.json", epi.temp_dir / "epi_policy.json")
        epi.log(
            "agent.run.start",
            {
                "agent_name": "AMLTransactionAgent",
                "domain": "banking",
                "user_input": "Screen international wire transfer TX-99120 ($45,000 USD to offshore commercial account)",
                "transaction_id": "TX-99120",
            },
        )
        epi.log(
            "policy.check",
            {
                "constraint": "aml_threshold_check",
                "status": "flagged",
                "threshold_usd": 10000,
                "transaction_amount_usd": 45000,
                "policy_ref": "BSA-AML-31CFR-1010",
                "detail": "Transaction amount $45,000 exceeds mandatory $10,000 reporting & review threshold.",
            },
        )
        _tool(
            epi,
            "sanctions.ofac_screen",
            {"entity_name": "Pacific Trade Logistics LLC", "country": "SG"},
            {"matched": False, "ofac_score": 0.0, "pep_match": False},
        )
        _tool(
            epi,
            "aml.transaction_pattern_check",
            {"account_id": "ACC-88102", "window_days": 30},
            {"velocity": "normal", "historical_monthly_avg_usd": 12000, "surge_factor": 3.75},
        )
        fallback = "FLAG FOR AML HUMAN REVIEW. Transaction TX-99120 ($45,000 international transfer) exceeds mandatory $10,000 BSA/AML threshold. Recommend compliance officer SAR evaluation."
        decision_memo = _llm_invoke(
            api_key,
            "You are a bank AML compliance monitoring assistant. State whether the transfer "
            "is APPROVED or FLAGGED FOR REVIEW, give a one-sentence rationale referencing "
            "the $10,000 threshold, and specify compliance disposition. Concise.",
            "Wire TX-99120 ($45,000 USD). OFAC clear. Monthly average $12,000 (3.75x surge). "
            "AML threshold check flagged (> $10k). What is the compliance determination?",
            fallback,
        )
        epi.log(
            "agent.decision",
            {
                "decision": "flag_for_compliance_officer",
                "recommendation": "flag_for_compliance_officer",
                "transaction_id": "TX-99120",
                "amount_usd": 45000,
                "memo": decision_memo,
                "rationale": decision_memo,
                "requires_sar_eval": True,
            },
        )
        epi.log(
            "agent.approval.request",
            {
                "action": "release_wire_hold",
                "transaction_id": "TX-99120",
                "amount_usd": 45000,
            },
        )
        epi.log(
            "agent.approval.response",
            {
                "action": "release_wire_hold",
                "decision": "approved",
                "status": "approved",
                "approved": True,
                "reviewer": "Sarah Jenkins (AML Compliance Officer)",
            },
        )
        epi.log("agent.run.end", {"status": "completed", "transaction_id": "TX-99120"})
    _seal_and_check(out)


# -----------------------------------------------------------------------------
# 6. Hiring Candidate Screening
# -----------------------------------------------------------------------------
def hiring_screening(api_key: str, out: Path) -> None:
    from epi_recorder import record

    with record(
        out,
        goal="Screen candidate application C-88194 for Senior Staff Software Engineer",
        workflow_name="Hiring · Candidate Screening Agent",
        tags=["demo", "hiring", "screening", "fairness", "hr"],
        notes="SIMULATED DEMO — Enforces strict protected-class non-discrimination policy rules.",
    ) as epi:
        shutil.copy2(ROOT / "demo_policies" / "hiring_screening_policy.json", epi.temp_dir / "epi_policy.json")
        epi.log(
            "agent.run.start",
            {
                "agent_name": "CandidateScreeningAgent",
                "domain": "hiring",
                "user_input": "Evaluate candidate C-88194 resume against Senior Staff Software Engineer role requirements",
                "candidate_id": "C-88194",
                "role_id": "REQ-STAFF-042",
            },
        )
        epi.log(
            "policy.check",
            {
                "constraint": "fair_hiring_no_protected_class",
                "status": "passed",
                "policy_ref": "EEOC-41CFR-60",
                "attributes_stripped": ["age", "gender", "ethnicity", "graduation_year", "zip_code"],
                "detail": "All demographic & protected-class attributes sanitized prior to evaluation.",
            },
        )
        _tool(
            epi,
            "skills.extract_technical_stack",
            {"candidate_id": "C-88194"},
            {
                "core_languages": ["Python", "Go", "Rust"],
                "frameworks": ["Distributed Systems", "Kubernetes", "gRPC"],
                "relevant_experience_years": 8.5,
                "verified_projects": 4,
            },
        )
        _tool(
            epi,
            "benchmark.role_fit_score",
            {"role_id": "REQ-STAFF-042", "candidate_skills": ["Python", "Go", "Kubernetes"]},
            {
                "technical_score": 0.91,
                "system_design_score": 0.88,
                "minimum_qualifying_score": 0.75,
                "meets_benchmark": True,
            },
        )
        fallback = "PASS TO TECHNICAL INTERVIEW. Candidate C-88194 meets technical requirements (8.5 yrs exp, Python/Go/Kubernetes). Fair hiring non-discrimination policy rule verified."
        summary = _llm_invoke(
            api_key,
            "You are an HR technical screening assistant. Provide a concise 2-sentence "
            "evaluation recommendation (PASS TO INTERVIEW or REJECT) based purely on technical "
            "qualifications and experience.",
            "Candidate C-88194 for Senior Staff Engineer. 8.5 years exp in Python, Go, "
            "Kubernetes. Technical fit score 0.91 (benchmark 0.75). Non-discrimination "
            "policy passed. What is the screening recommendation?",
            fallback,
        )
        epi.log(
            "agent.decision",
            {
                "decision": "advance_to_technical_interview",
                "recommendation": "advance_to_technical_interview",
                "candidate_id": "C-88194",
                "technical_fit_score": 0.91,
                "evaluation_summary": summary,
                "rationale": summary,
            },
        )
        epi.log(
            "agent.approval.request",
            {
                "action": "schedule_technical_interview",
                "candidate_id": "C-88194",
                "role_id": "REQ-STAFF-042",
            },
        )
        epi.log(
            "agent.approval.response",
            {
                "action": "schedule_technical_interview",
                "decision": "approved",
                "status": "approved",
                "approved": True,
                "reviewer": "Claire Vance (Lead HR Recruiter)",
            },
        )
        epi.log("agent.run.end", {"status": "completed", "candidate_id": "C-88194"})
    _seal_and_check(out)


# -----------------------------------------------------------------------------
# 7. Insurance Underwriting Pricing
# -----------------------------------------------------------------------------
def insurance_underwriting(api_key: str, out: Path) -> None:
    from epi_recorder import record

    with record(
        out,
        goal="Underwrite commercial property insurance quote PROP-3391",
        workflow_name="Insurance · Property Underwriting Agent",
        tags=["demo", "insurance", "underwriting", "property"],
        notes="SIMULATED DEMO — Enforces mandatory senior underwriter review above risk threshold.",
    ) as epi:
        shutil.copy2(ROOT / "demo_policies" / "insurance_underwriting_policy.json", epi.temp_dir / "epi_policy.json")
        epi.log(
            "agent.run.start",
            {
                "agent_name": "PropertyUnderwritingAgent",
                "domain": "insurance",
                "user_input": "Quote commercial property coverage for 100 Industrial Parkway ($2.5M replacement cost)",
                "quote_id": "PROP-3391",
            },
        )
        epi.log(
            "policy.check",
            {
                "constraint": "high_risk_pricing_human_review",
                "status": "flagged",
                "policy_ref": "UW-RULE-2026-HIGH-RISK",
                "max_auto_bind_limit_usd": 1000000,
                "requested_limit_usd": 2500000,
                "detail": "Requested property limit ($2,500,000) exceeds $1,000,000 automated binding limit.",
            },
        )
        _tool(
            epi,
            "geo.flood_and_wind_risk",
            {"address": "100 Industrial Parkway", "county": "Harris"},
            {
                "flood_zone": "AE (100-year flood plain)",
                "windstorm_tier": 2,
                "risk_score": 0.72,
            },
        )
        _tool(
            epi,
            "actuary.calculate_premium",
            {"valuation_usd": 2500000, "risk_score": 0.72},
            {
                "base_annual_premium_usd": 32000,
                "flood_surcharge_usd": 14400,
                "total_annual_quote_usd": 46400,
            },
        )
        fallback = "REFER TO SENIOR UNDERWRITER. Quote PROP-3391 ($46,400/yr for $2.5M valuation in Flood Zone AE) exceeds automated binding threshold. Underwriter approval mandatory."
        rationale = _llm_invoke(
            api_key,
            "You are a commercial property underwriter assistant. State whether the quote is "
            "AUTO-BOUND or REFERRED TO UNDERWRITER, give a 1-sentence risk rationale referencing "
            "Flood Zone AE and the $2.5M valuation. Concise.",
            "Quote PROP-3391 ($2.5M property, Flood Zone AE, $46,400 annual premium). "
            "Automated binding limit is $1.0M. Policy check flagged high risk. Determination?",
            fallback,
        )
        epi.log(
            "agent.decision",
            {
                "decision": "referred_to_senior_underwriter",
                "determination": "referred_to_senior_underwriter",
                "quote_id": "PROP-3391",
                "total_annual_premium_usd": 46400,
                "rationale": rationale,
            },
        )
        epi.log(
            "agent.approval.request",
            {
                "action": "bind_commercial_policy",
                "quote_id": "PROP-3391",
                "amount_usd": 46400,
            },
        )
        epi.log(
            "agent.approval.response",
            {
                "action": "bind_commercial_policy",
                "decision": "approved",
                "status": "approved",
                "approved": True,
                "reviewer": "Arthur Pendelton (Chief Property Underwriter)",
            },
        )
        epi.log("agent.run.end", {"status": "completed", "quote_id": "PROP-3391"})
    _seal_and_check(out)


# -----------------------------------------------------------------------------
# 8. Lending Affordability
# -----------------------------------------------------------------------------
def lending_affordability(api_key: str, out: Path) -> None:
    from epi_recorder import record

    with record(
        out,
        goal="Evaluate mortgage refinance application MORT-55102 for borrower affordability",
        workflow_name="Lending · Mortgage Affordability Agent",
        tags=["demo", "lending", "mortgage", "affordability"],
        notes="SIMULATED DEMO — Documented DTI affordability constraint evaluation.",
    ) as epi:
        shutil.copy2(ROOT / "demo_policies" / "lending_affordability_policy.json", epi.temp_dir / "epi_policy.json")
        epi.log(
            "agent.run.start",
            {
                "agent_name": "MortgageAffordabilityAgent",
                "domain": "lending",
                "user_input": "Assess affordability for mortgage refinance request MORT-55102 ($350,000 principal)",
                "application_id": "MORT-55102",
            },
        )
        epi.log(
            "policy.check",
            {
                "constraint": "debt_to_income_affordability_check",
                "status": "passed",
                "policy_ref": "CFPB-ATR-QM-RULE",
                "max_allowed_dti": 0.43,
                "calculated_dti": 0.32,
                "detail": "Calculated DTI ratio of 32.0% satisfies QM statutory affordability cap of 43.0%.",
            },
        )
        _tool(
            epi,
            "tax.verify_gross_income",
            {"application_id": "MORT-55102"},
            {
                "gross_monthly_income_usd": 11500,
                "verification_documents": ["W2-2025", "1099-2025"],
                "verified": True,
            },
        )
        _tool(
            epi,
            "liabilities.calculate_monthly_debt",
            {"applicant_id": "APP-MORT-55102"},
            {
                "proposed_housing_payment_usd": 2400,
                "auto_loans_usd": 450,
                "student_loans_usd": 300,
                "total_monthly_obligations_usd": 3150,
                "dti_ratio": 0.32,
            },
        )
        fallback = "APPROVE WITH AFFORDABILITY CERTIFICATE. Mortgage refinance MORT-55102 meets ATR/QM statutory affordability rules (32% DTI vs max 43%). Affordability certificate generated."
        rationale = _llm_invoke(
            api_key,
            "You are a mortgage affordability assessment assistant. State APPROVE or DENY, "
            "provide the DTI ratio, and include a 1-sentence affordability confirmation. Concise.",
            "Refinance MORT-55102 ($350,000 principal). Verified gross monthly income $11,500. "
            "Total monthly debt obligations $3,150 (DTI 32.0%). CFPB QM threshold is 43.0%. Determination?",
            fallback,
        )
        epi.log(
            "agent.decision",
            {
                "decision": "APPROVE",
                "determination": "APPROVE",
                "application_id": "MORT-55102",
                "dti_ratio": 0.32,
                "affordability_certified": True,
                "rationale": rationale,
            },
        )
        epi.log(
            "agent.approval.request",
            {
                "action": "issue_qm_affordability_certificate",
                "application_id": "MORT-55102",
                "calculated_dti": 0.32,
            },
        )
        epi.log(
            "agent.approval.response",
            {
                "action": "issue_qm_affordability_certificate",
                "decision": "approved",
                "status": "approved",
                "approved": True,
                "reviewer": "Eleanor Vance (Mortgage Compliance Officer)",
            },
        )
        epi.log("agent.run.end", {"status": "completed", "application_id": "MORT-55102"})
    _seal_and_check(out)


# -----------------------------------------------------------------------------
# Main Execution Pipeline
# -----------------------------------------------------------------------------
def main() -> int:
    api_key = _require_groq()
    if api_key:
        print("Using Groq API key for LLM decision generation.")
    else:
        print("GROQ_API_KEY not set — using realistic mock LLM fallback text.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DEMO_DIR.mkdir(parents=True, exist_ok=True)
    WEBSITE_DEMO_DIR.mkdir(parents=True, exist_ok=True)
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    jobs = [
        ("demo-finance-loan-underwriter.epi", finance_loan),
        ("demo-healthcare-clinical-triage.epi", healthcare_triage),
        ("demo-insurance-claim-adjudication.epi", insurance_claim),
        ("demo-legal-contract-review.epi", legal_contract),
        ("demo-banking-aml.epi", banking_aml),
        ("demo-hiring-screening.epi", hiring_screening),
        ("demo-insurance-underwriting.epi", insurance_underwriting),
        ("demo-lending-affordability.epi", lending_affordability),
    ]

    results: list[Path] = []
    import subprocess

    for name, fn in jobs:
        target = OUT_DIR / name
        print(f"\n=== {name} ===")
        abs_target = target.resolve()
        fn(api_key, abs_target)

        # Sync across target directories
        alt = ROOT / "epi-recordings" / name
        if not abs_target.exists() and alt.exists():
            shutil.copy2(alt, abs_target)

        if abs_target.exists():
            shutil.copy2(abs_target, SITE_DEMO_DIR / name)
            shutil.copy2(abs_target, WEBSITE_DEMO_DIR / name)
            shutil.copy2(abs_target, EXAMPLES_DIR / name)
            shutil.copy2(abs_target, DEMO_DIR / name)

            # No HTML export: the exported pages were stale copies of the viewer
            # and nothing links to them. The .epi is the evidence — open it with
            # `epi view`, or drop it on https://epilabs.org/verify.
            results.append(abs_target)
        else:
            print(f"  WARN: missing output for {name}", file=sys.stderr)

    print("\n=== INTEGRITY & LEAK AUDIT ===")
    from epi_core.container import EPIContainer

    for path in results:
        ok, mismatches = EPIContainer.verify_integrity(path)
        steps = EPIContainer.read_steps(path)
        kinds = {}
        for s in steps:
            k = s.get("kind") or "?"
            kinds[k] = kinds.get(k, 0) + 1
        print(f"{path.name}: integrity={ok} steps={len(steps)} kinds={kinds}")

    print("\nDone. Generated artifacts:")
    for p in results:
        print(" ", p)
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
