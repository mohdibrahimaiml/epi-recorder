# @title Create the Underwriter Agent { display-mode: "form" }
from IPython.display import display, HTML

agent_code = '''
import time
import json
import os
from dataclasses import dataclass
from epi_recorder import record

# --- Check for API key ---
API_KEY = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
DEMO_MODE = API_KEY is None

if DEMO_MODE:
    print("[DEMO MODE] No API key found - using simulated AI responses")
    print("            (Add GOOGLE_API_KEY to Secrets for live Gemini calls)")
else:
    print("[LIVE MODE] Using real Gemini 2.0 Flash API")

# --- Data Models ---
@dataclass
class Applicant:
    name: str
    business_name: str
    business_type: str
    years_in_business: int
    credit_score: int
    annual_revenue: float
    requested_loan: float

@dataclass
class BankStatement:
    average_monthly_balance: float
    transaction_descriptions: list

# --- Mock Gemini for Demo Mode ---
# NOTE TO INVESTOR: This mock is used ONLY when no API key is present.
# It returns deterministic responses that mirror the exact JSON schema
# a real Gemini 2.0 Flash call would produce. To see real LLM calls,
# add your GOOGLE_API_KEY to Colab Secrets.
class MockGeminiModel:
    def generate_content(self, prompt):
        time.sleep(0.5)
        if "risk indicators" in prompt.lower():
            return MockResponse(json.dumps({
                "risk_level": "LOW",
                "concerns": [],
                "positive_signals": [
                    "Regular vendor payments indicate active business",
                    "GST compliance shows formal operations",
                    "Equipment loan EMI shows asset building"
                ]
            }))
        else:
            return MockResponse(json.dumps({
                "decision": "APPROVED",
                "confidence": 0.87,
                "reasoning": "Strong financial profile with 4 years in business, healthy credit score of 680, and loan-to-revenue ratio of 11.8% well below the 50% threshold. Transaction history shows consistent business activity with no red flags.",
                "risk_factors": ["Monitor cash flow during seasonal variations"]
            }))

class MockResponse:
    def __init__(self, text):
        self.text = text

# --- The Agent ---
class UnderwriterAgent:
    def __init__(self):
        if DEMO_MODE:
            self.model = MockGeminiModel()
        else:
            import google.generativeai as genai
            genai.configure(api_key=API_KEY)
            self.model = genai.GenerativeModel("gemini-2.0-flash")

        self.system_prompt = """You are a Fair Lending Compliance Officer AI.
Assess loans based ONLY on financial metrics and business fundamentals.
You MUST NOT consider gender, race, religion, or any protected class.
Provide structured risk assessments with clear reasoning."""

    def analyze_transactions(self, statements):
        print("  [AI] Analyzing transaction patterns...")
        prompt = """{system}

Analyze these bank transactions for risk indicators:
{txns}

Average monthly balance: ${balance:,.2f}

Respond in JSON: {{"risk_level": "LOW|MEDIUM|HIGH", "concerns": [], "positive_signals": []}}""".format(
            system=self.system_prompt,
            txns=json.dumps(statements.transaction_descriptions, indent=2),
            balance=statements.average_monthly_balance
        )

        response = self.model.generate_content(prompt)
        try:
            text = response.text
            if "```json" in text: text = text.split("```json")[1].split("```")[0]
            elif "```" in text: text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except:
            return {"risk_level": "MEDIUM", "concerns": ["Parse error"], "positive_signals": []}

    def make_decision(self, applicant, risk_analysis):
        print("  [AI] Making final underwriting decision...")
        prompt = """{system}

APPLICANT:
- Business: {biz} ({btype})
- Years in Business: {years}
- Credit Score: {credit}
- Annual Revenue: ${rev:,.2f}
- Requested Loan: ${loan:,.2f}

RISK ANALYSIS: {risk}

Respond in JSON: {{"decision": "APPROVED|REJECTED", "confidence": 0.0-1.0, "reasoning": "explanation", "risk_factors": []}}""".format(
            system=self.system_prompt,
            biz=applicant.business_name,
            btype=applicant.business_type,
            years=applicant.years_in_business,
            credit=applicant.credit_score,
            rev=applicant.annual_revenue,
            loan=applicant.requested_loan,
            risk=json.dumps(risk_analysis)
        )

        response = self.model.generate_content(prompt)
        try:
            text = response.text
            if "```json" in text: text = text.split("```json")[1].split("```")[0]
            elif "```" in text: text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except:
            return {"decision": "MANUAL_REVIEW", "confidence": 0.5, "reasoning": "AI error", "risk_factors": []}

    def process(self, applicant, statements):
        print("")
        print("=" * 60)
        print("PROCESSING: {}".format(applicant.business_name))
        print("Loan Request: ${:,.2f}".format(applicant.requested_loan))
        print("=" * 60)
        print("")

        status = "- OK" if applicant.credit_score >= 600 else "- FAIL"
        print("  [POLICY] Credit Score: {} {}".format(applicant.credit_score, status))
        if applicant.credit_score < 600:
            return {"decision": "REJECTED", "reasoning": "Credit score below 600"}

        risk = self.analyze_transactions(statements)
        print("  [OK] Risk Level: {}".format(risk.get("risk_level")))

        decision = self.make_decision(applicant, risk)
        print("")
        print("=" * 60)
        print("DECISION: {}".format(decision.get("decision")))
        print("Confidence: {:.0%}".format(decision.get("confidence", 0)))
        print("Reasoning: {}".format(decision.get("reasoning")))
        print("=" * 60)
        print("")
        return decision

# === MAIN EXECUTION WITH EPI RECORDING ===
if __name__ == "__main__":
    with record("loan_evidence.epi", workflow_name="Loan Underwriting", auto_sign=True) as epi:

        applicant = Applicant(
            name="Priya Sharma",
            business_name="Sharma Electronics Repair",
            business_type="Electronics Retail",
            years_in_business=4,
            credit_score=680,
            annual_revenue=850000,
            requested_loan=100000
        )

        statements = BankStatement(
            average_monthly_balance=45000,
            transaction_descriptions=[
                "VENDOR PAYMENT - SAMSUNG INDIA",
                "RENT - KORAMANGALA SHOP",
                "SALARY TRANSFER - STAFF",
                "GST CHALLAN PAYMENT",
                "AMAZON SELLER PAYOUT",
                "EMI - HDFC EQUIPMENT LOAN"
            ]
        )

        agent = UnderwriterAgent()
        result = agent.process(applicant, statements)
        epi.log_step("DECISION", result)

        print("")
        print("[FINAL DECISION]")
        print(json.dumps(result, indent=2))
'''

with open('underwriter_agent.py', 'w') as f:
    f.write(agent_code)

display(HTML('<h3 style="color: #10b981;">Created: underwriter_agent.py</h3>'))
display(HTML('<p style="color: #6b7280;">Demo mode: Works without API key | Live mode: Add GOOGLE_API_KEY</p>'))
