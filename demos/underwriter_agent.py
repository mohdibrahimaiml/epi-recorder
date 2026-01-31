"""
Autonomous Fintech Underwriter Agent
=====================================
A production-grade AI agent for small business loan decisions.
Uses Google Gemini for intelligent risk assessment.

This script demonstrates how EPI captures AI decision-making
for regulatory compliance (Fair Lending, ECOA).
"""

import time
import json
from dataclasses import dataclass, asdict
from typing import Literal
from datetime import datetime

# --- Data Models ---

@dataclass
class Applicant:
    """Loan applicant profile."""
    name: str
    business_name: str
    business_type: str
    years_in_business: int
    credit_score: int
    annual_revenue: float
    requested_loan: float
    # Note: No gender, race, or protected class - Fair Lending compliant
    
@dataclass
class BankStatement:
    """Simplified bank transaction summary."""
    average_monthly_balance: float
    transaction_descriptions: list[str]  # Messy text data for AI analysis

@dataclass
class UnderwritingDecision:
    """Final loan decision with full audit trail."""
    application_id: str
    decision: Literal["APPROVED", "REJECTED", "MANUAL_REVIEW"]
    confidence: float
    reasoning: str
    risk_factors: list[str]
    timestamp: str

# --- The Agent ---

class UnderwriterAgent:
    """
    AI-powered loan underwriting agent.
    Combines deterministic rules with Gemini reasoning.
    """
    
    def __init__(self):
        import google.generativeai as genai
        import os
        
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable required")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        
        # Fair Lending System Prompt (captured by EPI!)
        self.system_prompt = """You are a Fair Lending Compliance Officer AI.
Your role is to assess loan applications based ONLY on:
- Financial metrics (credit score, revenue, cash flow)
- Business fundamentals (years in operation, industry risk)
- Behavioral indicators in transaction history

You MUST NOT consider or infer:
- Gender, race, religion, national origin
- Marital status or familial status
- Any protected class under ECOA

Provide structured risk assessments with clear reasoning."""

    def check_kyc(self, applicant: Applicant) -> bool:
        """Deterministic KYC check (simulated)."""
        print(f"  [KYC] Verifying identity for {applicant.name}...")
        time.sleep(0.3)
        # In production: call identity verification API
        return True
    
    def check_credit_policy(self, applicant: Applicant) -> tuple[bool, str]:
        """Hard credit policy rules (deterministic)."""
        print(f"  [POLICY] Checking credit score: {applicant.credit_score}")
        time.sleep(0.2)
        
        if applicant.credit_score < 500:
            return False, "Credit score below minimum threshold (500)"
        if applicant.requested_loan > applicant.annual_revenue * 0.5:
            return False, "Loan amount exceeds 50% of annual revenue"
        return True, "Passed policy checks"
    
    def analyze_transactions(self, statements: BankStatement) -> dict:
        """
        AI-powered transaction analysis.
        Gemini identifies risk patterns in messy text data.
        """
        print("  [AI] Analyzing transaction patterns with Gemini...")
        
        prompt = f"""{self.system_prompt}

Analyze these bank transaction descriptions for risk indicators.
Look for: gambling, payday loans, legal troubles, irregular patterns.

Transaction samples:
{json.dumps(statements.transaction_descriptions, indent=2)}

Average monthly balance: ${statements.average_monthly_balance:,.2f}

Respond in JSON format:
{{"risk_level": "LOW|MEDIUM|HIGH", "concerns": ["list of concerns"], "positive_signals": ["list"]}}
"""
        
        response = self.model.generate_content(prompt)
        
        # Parse response (with fallback)
        try:
            # Extract JSON from response
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except:
            return {
                "risk_level": "MEDIUM",
                "concerns": ["Unable to parse AI response"],
                "positive_signals": []
            }
    
    def make_decision(self, applicant: Applicant, risk_analysis: dict) -> UnderwritingDecision:
        """
        Final underwriting decision using Gemini.
        Synthesizes all data into approved/rejected with reasoning.
        """
        print("  [AI] Making final underwriting decision...")
        
        prompt = f"""{self.system_prompt}

Make a loan underwriting decision based on:

APPLICANT:
- Business: {applicant.business_name} ({applicant.business_type})
- Years in Business: {applicant.years_in_business}
- Credit Score: {applicant.credit_score}
- Annual Revenue: ${applicant.annual_revenue:,.2f}
- Requested Loan: ${applicant.requested_loan:,.2f}
- Debt-to-Revenue Ratio: {(applicant.requested_loan / applicant.annual_revenue * 100):.1f}%

TRANSACTION RISK ANALYSIS:
{json.dumps(risk_analysis, indent=2)}

Respond in JSON:
{{"decision": "APPROVED|REJECTED|MANUAL_REVIEW", "confidence": 0.0-1.0, "reasoning": "2-3 sentence explanation", "risk_factors": ["list"]}}
"""
        
        response = self.model.generate_content(prompt)
        
        # Parse response
        try:
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            result = json.loads(text.strip())
        except:
            result = {
                "decision": "MANUAL_REVIEW",
                "confidence": 0.5,
                "reasoning": "AI response parsing failed - requires human review",
                "risk_factors": ["System error"]
            }
        
        return UnderwritingDecision(
            application_id=f"LOAN-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            decision=result.get("decision", "MANUAL_REVIEW"),
            confidence=result.get("confidence", 0.5),
            reasoning=result.get("reasoning", ""),
            risk_factors=result.get("risk_factors", []),
            timestamp=datetime.utcnow().isoformat()
        )
    
    def process_application(self, applicant: Applicant, statements: BankStatement) -> UnderwritingDecision:
        """Full underwriting workflow."""
        print(f"\n{'='*60}")
        print(f"PROCESSING LOAN APPLICATION")
        print(f"Applicant: {applicant.name} | Business: {applicant.business_name}")
        print(f"Requested: ${applicant.requested_loan:,.2f}")
        print(f"{'='*60}\n")
        
        # Step 1: KYC
        if not self.check_kyc(applicant):
            return UnderwritingDecision(
                application_id="FAILED-KYC",
                decision="REJECTED",
                confidence=1.0,
                reasoning="Identity verification failed",
                risk_factors=["KYC failure"],
                timestamp=datetime.utcnow().isoformat()
            )
        print("  [OK] KYC Verified\n")
        
        # Step 2: Hard Policy Check
        policy_ok, policy_reason = self.check_credit_policy(applicant)
        if not policy_ok:
            return UnderwritingDecision(
                application_id="FAILED-POLICY",
                decision="REJECTED",
                confidence=1.0,
                reasoning=policy_reason,
                risk_factors=["Policy violation"],
                timestamp=datetime.utcnow().isoformat()
            )
        print(f"  [OK] {policy_reason}\n")
        
        # Step 3: AI Transaction Analysis
        risk_analysis = self.analyze_transactions(statements)
        print(f"  [OK] Risk Level: {risk_analysis.get('risk_level', 'UNKNOWN')}\n")
        
        # Step 4: AI Final Decision
        decision = self.make_decision(applicant, risk_analysis)
        
        # Display Result
        print(f"\n{'='*60}")
        print(f"DECISION: {decision.decision}")
        print(f"Confidence: {decision.confidence:.0%}")
        print(f"Reasoning: {decision.reasoning}")
        print(f"Application ID: {decision.application_id}")
        print(f"{'='*60}\n")
        
        return decision


# --- Demo Execution ---

if __name__ == "__main__":
    # Sample application data
    applicant = Applicant(
        name="Priya Sharma",
        business_name="Sharma Electronics Repair",
        business_type="Electronics Retail & Repair",
        years_in_business=4,
        credit_score=680,
        annual_revenue=850000,
        requested_loan=100000
    )
    
    bank_statements = BankStatement(
        average_monthly_balance=45000,
        transaction_descriptions=[
            "VENDOR PAYMENT - SAMSUNG INDIA",
            "RENT - KORAMANGALA SHOP UNIT 4",
            "SALARY TRANSFER - STAFF AUG 2025",
            "UPI-CUSTOMER PAYMENT-MOBILE REPAIR",
            "GST CHALLAN PAYMENT Q2",
            "ELECTRICITY - BESCOM COMMERCIAL",
            "AMAZON SELLER PAYOUT",
            "SWIGGY PAYOUT - DELIVERY PARTNER",
            "CASH DEPOSIT - COUNTER SALES",
            "EMI - HDFC EQUIPMENT LOAN"
        ]
    )
    
    # Run the agent
    agent = UnderwriterAgent()
    decision = agent.process_application(applicant, bank_statements)
    
    # Output structured decision for EPI capture
    print("\n[STRUCTURED OUTPUT]")
    print(json.dumps(asdict(decision), indent=2))


