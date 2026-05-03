#!/usr/bin/env python3
"""
Scenario 03 — Medical Triage: Full Cardiac Protocol
Emergency nurse uses AI triage for a chest pain patient.
ESI Level 2 assigned → physician decision logged → cardiac protocol activated.
Expected result: PASS, R004 satisfied (physician step present after ESI-2 triage).
"""
from pathlib import Path
from epi_recorder.api import EpiRecorderSession

OUTPUT = Path(__file__).parent / "output" / "03_medical_triage.epi"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

def main():
    with EpiRecorderSession(
        output_path=str(OUTPUT),
        workflow_name="triage-ER-2026-0502-T041",
        goal="AI-assisted emergency triage for acute chest pain presentation",
        notes="47-year-old male, ambulance arrival. Potential NSTEMI. Full audit trail for QA review.",
        tags=["healthcare", "triage", "cardiac", "esi-2", "simulation"],
        metrics={"esi_level": 2, "time_to_ecg_min": 4, "time_to_physician_min": 8},
        auto_sign=True,
    ) as epi:

        epi.log_step("patient.intake", {
            "mrn": "MRN-2026-88341",
            "age": 47,
            "sex": "male",
            "arrival_mode": "ambulance",
            "chief_complaint": "Chest pain radiating to left arm, 50 minutes duration",
            "onset": "sudden",
        })

        epi.log_step("vitals.recorded", {
            "blood_pressure": "168/96",
            "heart_rate": 112,
            "oxygen_saturation": 93,
            "respiratory_rate": 22,
            "temperature_f": 99.1,
            "pain_scale": 8,
        })

        epi.log_step("llm.request", {
            "model": "medical-triage-v3",
            "messages": [
                {"role": "system", "content": "You are an emergency triage nurse. Assign ESI level 1-5 and provide rationale. Be conservative — err on side of higher acuity."},
                {"role": "user",   "content": "Patient: 47M, chest pain + left arm radiation + nausea, 50min. BP 168/96, HR 112, O2 93%, RR 22. No known cardiac history."},
            ],
        })

        epi.log_step("llm.response", {
            "model": "medical-triage-v3",
            "output": "ESI LEVEL: 2 — HIGH ACUITY. Rationale: Classic ACS presentation. Abnormal vitals (HTN, tachycardia, hypoxia). Requires ECG within 10 minutes, physician evaluation within 15 minutes, IV access, continuous cardiac monitoring. Activate chest pain protocol.",
            "confidence": 0.94,
            "tokens_used": 187,
        })

        epi.log_step("policy.check", {
            "rule_id": "R004",
            "esi_level": 2,
            "requires_physician": True,
            "physician_assigned": "dr.patel@citygeneral.org",
            "status": "compliant",
            "max_wait_minutes": 15,
        })

        epi.log_step("physician.decision", {
            "physician_id": "dr.patel@citygeneral.org",
            "decision": "ACTIVATE_CARDIAC_PROTOCOL",
            "orders": ["12_lead_ecg", "troponin_panel", "chest_xray", "aspirin_325mg", "heparin_iv", "cath_lab_standby"],
            "clinical_impression": "High probability NSTEMI. Activating cath lab. Cardiology consult placed.",
            "timestamp": "2026-05-02T08:14:00Z",
        })

        epi.log_step("patient.outcome", {
            "final_diagnosis": "NSTEMI",
            "intervention": "cardiac_catheterization",
            "disposition": "admitted_cardiac_icu",
            "time_to_ecg_minutes": 4,
            "time_to_physician_minutes": 8,
            "time_to_cath_minutes": 38,
            "outcome": "stable_post_intervention",
        })

    print(f"[03] Medical triage recorded -> {OUTPUT}")

if __name__ == "__main__":
    main()
