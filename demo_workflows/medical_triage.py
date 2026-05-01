#!/usr/bin/env python3
"""
Realistic healthcare workflow: AI-Assisted Medical Triage
A nurse uses an AI triage system to prioritize patients.
HIPAA-sensitive data (names, SSNs, medical record numbers) should be redacted.
"""
from epi_recorder.api import EpiRecorderSession

# Simulated patient intake
PATIENT = {
    "mrn": "MRN-9923847",  # Medical record number
    "name": "Robert Chen",
    "dob": "1978-03-15",
    "ssn": "987-65-4321",  # Should be redacted
    "insurance_id": "INS-5544332211",
    "symptoms": ["chest_pain", "shortness_of_breath", "nausea"],
    "vitals": {"bp": "165/95", "hr": 110, "o2": 94, "temp": 99.2},
}

def main():
    with EpiRecorderSession(
        output_path="medical_triage.epi",
        workflow_name="emergency-triage-ER-2025-0115",
        goal="AI-assisted triage for chest pain presentation",
        notes="Potential cardiac event. Requires full audit trail for quality review.",
        tags=["healthcare", "triage", "cardiac", "hipaa-sensitive"],
        auto_sign=True,
    ) as epi:
        # Step 1: Patient intake
        epi.log_step("patient.intake", {
            "mrn": PATIENT["mrn"],
            "presenting_complaint": "chest_pain",
            "arrival_mode": "ambulance",
            "chief_complaint": "Chest pain radiating to left arm, 45 min duration",
        })

        # Step 2: Vitals (clinical data, not PII)
        epi.log_step("vitals.recorded", {
            "blood_pressure": PATIENT["vitals"]["bp"],
            "heart_rate": PATIENT["vitals"]["hr"],
            "oxygen_saturation": PATIENT["vitals"]["o2"],
            "temperature_f": PATIENT["vitals"]["temp"],
        })

        # Step 3: LLM triage assessment
        epi.log_step("llm.request", {
            "model": "medical-triage-v2",
            "prompt": f"Triage: 47yo male, chest pain + SOB + nausea. BP {PATIENT['vitals']['bp']}, HR {PATIENT['vitals']['hr']}, O2 {PATIENT['vitals']['o2']}. Assign ESI level.",
            "system_prompt": "You are an emergency department triage nurse. Assign ESI level 1-5. Be conservative.",
        })

        # Step 4: LLM response
        epi.log_step("llm.response", {
            "output": "ESI LEVEL 2. RATIONALE: Chest pain with cardiac risk factors, abnormal vitals (hypertensive, tachycardic). Requires ECG within 10 minutes and physician evaluation.",
            "model": "medical-triage-v2",
            "confidence": 0.91,
        })

        # Step 5: Policy check — high-acuity alert
        epi.log_step("policy.check", {
            "rule_id": "ESI_2_REQUIRES_PHYSICIAN_WITHIN_15_MIN",
            "esi_level": 2,
            "max_wait_minutes": 15,
            "status": "compliant",
            "physician_assigned": "dr.jones@hospital.org",
        })

        # Step 6: Physician decision
        epi.log_step("physician.decision", {
            "physician_id": "dr.jones@hospital.org",
            "decision": "ACTIVATE_CARDIAC_PROTOCOL",
            "orders": ["12_lead_ecg", "troponin_panel", "chest_xray", "aspirin_325mg"],
            "rationale": "Concur with AI triage. High probability ACS. Activating cath lab standby.",
        })

        # Step 7: Outcome
        epi.log_step("patient.outcome", {
            "diagnosis": "NSTEMI",
            "intervention": "cardiac_catheterization",
            "disposition": "admitted_ccu",
            "time_to_ecg_minutes": 4,
            "time_to_cath_minutes": 42,
        })

        print(f"Medical triage recorded: medical_triage.epi")


if __name__ == "__main__":
    main()
