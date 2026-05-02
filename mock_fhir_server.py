"""
Mock FHIR Server — Synthea-style test data
Runs locally for testing the MCP pipeline without a real FHIR server.
3 realistic patients with conditions, labs, meds, notes, encounters.
"""
import json
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("mock-fhir")

mock_fhir = FastAPI(title="Mock FHIR R4 Server (Synthea Test Data)")

# ══════════════════════════════════════════════════════════
# SYNTHEA-STYLE TEST PATIENTS
# ══════════════════════════════════════════════════════════

PATIENTS = {
    "synth-001": {
        "resourceType": "Patient",
        "id": "synth-001",
        "name": [{"use": "official", "given": ["Maria", "Elena"], "family": "Rodriguez"}],
        "gender": "female",
        "birthDate": "1958-03-14",
        "address": [{"city": "Austin", "state": "TX", "postalCode": "78701"}],
        "extension": [
            {"url": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race",
             "extension": [{"url": "text", "valueString": "White"}]},
            {"url": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity",
             "extension": [{"url": "text", "valueString": "Hispanic or Latino"}]},
        ],
    },
    "synth-002": {
        "resourceType": "Patient",
        "id": "synth-002",
        "name": [{"use": "official", "given": ["James"], "family": "Thompson"}],
        "gender": "male",
        "birthDate": "1965-11-22",
        "address": [{"city": "Houston", "state": "TX", "postalCode": "77001"}],
    },
    "synth-003": {
        "resourceType": "Patient",
        "id": "synth-003",
        "name": [{"use": "official", "given": ["Sarah", "Lynn"], "family": "Chen"}],
        "gender": "female",
        "birthDate": "1972-07-08",
        "address": [{"city": "Dallas", "state": "TX", "postalCode": "75201"}],
    },
}

# Maria Rodriguez: Diabetes documented in notes but only coded as E11.9 (unspecified)
# Gap: E11.65 (with hyperglycemia) — HbA1c is 8.4%
# Gap: E78.0 (hypercholesterolemia) — LDL 198
# Gap: N18.3 (CKD Stage 3) — eGFR 48
OBSERVATIONS_001 = [
    {"resourceType": "Observation", "id": "obs-001-1", "status": "final",
     "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4", "display": "Hemoglobin A1c"}], "text": "HbA1c"},
     "subject": {"reference": "Patient/synth-001"},
     "effectiveDateTime": "2026-01-15",
     "valueQuantity": {"value": 8.4, "unit": "%"},
     "interpretation": [{"coding": [{"code": "H"}]}],
     "referenceRange": [{"low": {"value": 4.0}, "high": {"value": 5.6}}]},
    {"resourceType": "Observation", "id": "obs-001-2", "status": "final",
     "code": {"coding": [{"system": "http://loinc.org", "code": "33914-3", "display": "eGFR"}], "text": "eGFR"},
     "subject": {"reference": "Patient/synth-001"},
     "effectiveDateTime": "2026-01-15",
     "valueQuantity": {"value": 48, "unit": "mL/min/1.73m2"},
     "referenceRange": [{"low": {"value": 60}}]},
    {"resourceType": "Observation", "id": "obs-001-3", "status": "final",
     "code": {"coding": [{"system": "http://loinc.org", "code": "2089-1", "display": "LDL Cholesterol"}], "text": "LDL"},
     "subject": {"reference": "Patient/synth-001"},
     "effectiveDateTime": "2026-01-15",
     "valueQuantity": {"value": 198, "unit": "mg/dL"},
     "referenceRange": [{"high": {"value": 100}}]},
    {"resourceType": "Observation", "id": "obs-001-4", "status": "final",
     "code": {"coding": [{"system": "http://loinc.org", "code": "1742-6", "display": "ALT"}], "text": "ALT"},
     "subject": {"reference": "Patient/synth-001"},
     "effectiveDateTime": "2026-01-15",
     "valueQuantity": {"value": 32, "unit": "U/L"},
     "referenceRange": [{"low": {"value": 7}, "high": {"value": 56}}]},
    {"resourceType": "Observation", "id": "obs-001-5", "status": "final",
     "code": {"coding": [{"system": "http://loinc.org", "code": "718-7", "display": "Hemoglobin"}], "text": "Hemoglobin"},
     "subject": {"reference": "Patient/synth-001"},
     "effectiveDateTime": "2026-01-15",
     "valueQuantity": {"value": 11.2, "unit": "g/dL"},
     "referenceRange": [{"low": {"value": 12.0}, "high": {"value": 16.0}}]},
    {"resourceType": "Observation", "id": "obs-001-6", "status": "final",
     "code": {"coding": [{"system": "http://loinc.org", "code": "2571-8", "display": "Triglycerides"}], "text": "Triglycerides"},
     "subject": {"reference": "Patient/synth-001"},
     "effectiveDateTime": "2026-01-15",
     "valueQuantity": {"value": 220, "unit": "mg/dL"},
     "referenceRange": [{"high": {"value": 150}}]},
]

CONDITIONS_001 = [
    {"resourceType": "Condition", "id": "cond-001-1",
     "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "E11.9", "display": "Type 2 diabetes mellitus without complications"}], "text": "Diabetes"},
     "subject": {"reference": "Patient/synth-001"},
     "clinicalStatus": {"coding": [{"code": "active"}]},
     "verificationStatus": {"coding": [{"code": "confirmed"}]},
     "onsetDateTime": "2018-06-01"},
    {"resourceType": "Condition", "id": "cond-001-2",
     "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "I10", "display": "Essential hypertension"}]},
     "subject": {"reference": "Patient/synth-001"},
     "clinicalStatus": {"coding": [{"code": "active"}]},
     "verificationStatus": {"coding": [{"code": "confirmed"}]}},
]

MEDICATIONS_001 = [
    {"resourceType": "MedicationRequest", "id": "med-001-1", "status": "active",
     "medicationCodeableConcept": {"coding": [{"display": "Metformin 1000mg", "code": "6809"}], "text": "Metformin"},
     "subject": {"reference": "Patient/synth-001"},
     "dosageInstruction": [{"text": "Take 1 tablet twice daily with meals"}],
     "authoredOn": "2024-01-10"},
    {"resourceType": "MedicationRequest", "id": "med-001-2", "status": "active",
     "medicationCodeableConcept": {"coding": [{"display": "Lisinopril 20mg", "code": "29046"}]},
     "subject": {"reference": "Patient/synth-001"},
     "dosageInstruction": [{"text": "Take 1 tablet daily"}],
     "authoredOn": "2023-05-15"},
    {"resourceType": "MedicationRequest", "id": "med-001-3", "status": "active",
     "medicationCodeableConcept": {"coding": [{"display": "Atorvastatin 40mg", "code": "83367"}]},
     "subject": {"reference": "Patient/synth-001"},
     "dosageInstruction": [{"text": "Take 1 tablet at bedtime"}],
     "authoredOn": "2023-05-15"},
]

import base64
NOTE_TEXT_001 = """
PROGRESS NOTE — Maria Rodriguez
Date: 2026-01-15 | Provider: Dr. Sarah Kim, MD

CHIEF COMPLAINT:
Follow-up for diabetes management and routine labs review.

HISTORY OF PRESENT ILLNESS:
68-year-old Hispanic female presents for follow-up of Type 2 diabetes mellitus.
Patient reports occasional blurred vision and increased thirst over the past month.
She has been compliant with Metformin 1000mg BID. Reports no hypoglycemic episodes.
She also notes bilateral foot numbness that has been progressing.

REVIEW OF SYSTEMS:
Positive for increased thirst, blurred vision, bilateral foot numbness.
Negative for chest pain, shortness of breath.

MEDICATIONS:
1. Metformin 1000mg PO BID
2. Lisinopril 20mg PO daily
3. Atorvastatin 40mg PO QHS

PHYSICAL EXAM:
VS: BP 142/88, HR 76, Temp 98.6F, Wt 198 lbs, BMI 34.2
General: Well-appearing, in no acute distress.
Extremities: Bilateral pedal edema 1+. Decreased monofilament sensation bilateral feet.

LABS REVIEWED:
HbA1c: 8.4% (previous 7.8% six months ago — worsening control)
eGFR: 48 mL/min (previously 55 — declining renal function)
LDL: 198 mg/dL (significantly elevated despite statin therapy)
Hemoglobin: 11.2 g/dL (mild anemia, likely anemia of chronic kidney disease)
Triglycerides: 220 mg/dL (elevated)

ASSESSMENT AND PLAN:
1. Type 2 diabetes mellitus — UNCONTROLLED with hyperglycemia. HbA1c has risen
   from 7.8% to 8.4%. Patient developing peripheral neuropathy symptoms.
   Will add Empagliflozin 10mg daily for additional glycemic control and
   renal protection. Refer to diabetic educator.

2. Chronic kidney disease, Stage 3 — eGFR 48, down from 55. Likely diabetic
   nephropathy given longstanding DM2. Continue ACE inhibitor. Recheck in 3 months.
   Avoid NSAIDs. Will refer to nephrology if eGFR continues to decline.

3. Hypercholesterolemia — LDL 198 despite Atorvastatin 40mg. Will increase to 80mg.
   Counsel on dietary modifications. Consider adding Ezetimibe if not at goal
   in 3 months.

4. Anemia — Hemoglobin 11.2. In setting of CKD Stage 3, likely anemia of
   chronic kidney disease. Check iron studies, reticulocyte count, B12/folate.

5. Hypertension — BP 142/88, not at goal. Continue Lisinopril. Consider adding
   Amlodipine if not controlled at next visit.

FOLLOW UP: 3 months for repeat labs and medication review.

Electronically signed by: Dr. Sarah Kim, MD — 2026-01-15 14:32
"""

DOCUMENTS_001 = [
    {"resourceType": "DocumentReference", "id": "doc-001-1",
     "status": "current", "date": "2026-01-15",
     "type": {"coding": [{"display": "Progress Note"}], "text": "Progress Note"},
     "subject": {"reference": "Patient/synth-001"},
     "content": [{"attachment": {
         "contentType": "text/plain",
         "data": base64.b64encode(NOTE_TEXT_001.encode()).decode()
     }}]},
]

ENCOUNTERS_001 = [
    {"resourceType": "Encounter", "id": "enc-001-1", "status": "finished",
     "class": {"code": "AMB"}, "type": [{"text": "Office Visit"}],
     "subject": {"reference": "Patient/synth-001"},
     "period": {"start": "2026-01-15", "end": "2026-01-15"}},
]

# James Thompson: Heart failure documented in notes, not coded. COPD on meds but not coded.
OBSERVATIONS_002 = [
    {"resourceType": "Observation", "id": "obs-002-1", "status": "final",
     "code": {"coding": [{"system": "http://loinc.org", "code": "42637-9", "display": "BNP"}]},
     "subject": {"reference": "Patient/synth-002"},
     "effectiveDateTime": "2026-02-10",
     "valueQuantity": {"value": 580, "unit": "pg/mL"}},
    {"resourceType": "Observation", "id": "obs-002-2", "status": "final",
     "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4", "display": "HbA1c"}]},
     "subject": {"reference": "Patient/synth-002"},
     "effectiveDateTime": "2026-02-10",
     "valueQuantity": {"value": 5.4, "unit": "%"}},
]

CONDITIONS_002 = [
    {"resourceType": "Condition", "id": "cond-002-1",
     "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "I10", "display": "Essential hypertension"}]},
     "subject": {"reference": "Patient/synth-002"},
     "clinicalStatus": {"coding": [{"code": "active"}]}},
]

MEDICATIONS_002 = [
    {"resourceType": "MedicationRequest", "id": "med-002-1", "status": "active",
     "medicationCodeableConcept": {"coding": [{"display": "Furosemide 40mg"}]},
     "subject": {"reference": "Patient/synth-002"},
     "dosageInstruction": [{"text": "Take 1 tablet daily"}], "authoredOn": "2025-08-01"},
    {"resourceType": "MedicationRequest", "id": "med-002-2", "status": "active",
     "medicationCodeableConcept": {"coding": [{"display": "Carvedilol 12.5mg"}]},
     "subject": {"reference": "Patient/synth-002"},
     "dosageInstruction": [{"text": "Take 1 tablet twice daily"}], "authoredOn": "2025-08-01"},
    {"resourceType": "MedicationRequest", "id": "med-002-3", "status": "active",
     "medicationCodeableConcept": {"coding": [{"display": "Tiotropium 18mcg"}]},
     "subject": {"reference": "Patient/synth-002"},
     "dosageInstruction": [{"text": "Inhale 1 capsule daily"}], "authoredOn": "2024-03-01"},
    {"resourceType": "MedicationRequest", "id": "med-002-4", "status": "active",
     "medicationCodeableConcept": {"coding": [{"display": "Albuterol inhaler"}]},
     "subject": {"reference": "Patient/synth-002"},
     "dosageInstruction": [{"text": "2 puffs every 4 hours as needed"}], "authoredOn": "2024-03-01"},
]

NOTE_TEXT_002 = """
PROGRESS NOTE — James Thompson
Date: 2026-02-10

ASSESSMENT AND PLAN:
1. Heart failure with reduced ejection fraction — EF 35% on last echo.
   BNP elevated at 580. Patient reports dyspnea on exertion, 2-pillow orthopnea.
   Continue Furosemide and Carvedilol. Will optimize medical therapy.

2. COPD — stable on Tiotropium and albuterol PRN. No recent exacerbation.
   Continue current regimen. PFTs due for annual review.

3. Hypertension — controlled on current regimen. Continue monitoring.
"""

DOCUMENTS_002 = [
    {"resourceType": "DocumentReference", "id": "doc-002-1", "status": "current", "date": "2026-02-10",
     "type": {"text": "Progress Note"}, "subject": {"reference": "Patient/synth-002"},
     "content": [{"attachment": {"contentType": "text/plain",
         "data": base64.b64encode(NOTE_TEXT_002.encode()).decode()}}]},
]

ENCOUNTERS_002 = [
    {"resourceType": "Encounter", "id": "enc-002-1", "status": "finished",
     "class": {"code": "AMB"}, "type": [{"text": "Follow-up Visit"}],
     "subject": {"reference": "Patient/synth-002"},
     "period": {"start": "2026-02-10"}},
]

# Sarah Chen: Depression on meds, hypothyroid on levothyroxine, neither coded
CONDITIONS_003 = []  # Nothing coded — all gaps
MEDICATIONS_003 = [
    {"resourceType": "MedicationRequest", "id": "med-003-1", "status": "active",
     "medicationCodeableConcept": {"coding": [{"display": "Sertraline 100mg"}]},
     "subject": {"reference": "Patient/synth-003"}, "authoredOn": "2025-06-01"},
    {"resourceType": "MedicationRequest", "id": "med-003-2", "status": "active",
     "medicationCodeableConcept": {"coding": [{"display": "Levothyroxine 75mcg"}]},
     "subject": {"reference": "Patient/synth-003"}, "authoredOn": "2024-01-15"},
]
OBSERVATIONS_003 = [
    {"resourceType": "Observation", "id": "obs-003-1", "status": "final",
     "code": {"coding": [{"system": "http://loinc.org", "code": "3016-3", "display": "TSH"}]},
     "subject": {"reference": "Patient/synth-003"},
     "effectiveDateTime": "2026-01-20",
     "valueQuantity": {"value": 8.2, "unit": "mIU/L"}},
]
NOTE_TEXT_003 = """
ASSESSMENT AND PLAN:
1. Major depressive disorder — stable on Sertraline 100mg. PHQ-9 score 8 today,
   improved from 14. Continue current dose. Follow up in 3 months.
2. Hypothyroidism — TSH 8.2, elevated. Increase Levothyroxine to 88mcg.
   Recheck TSH in 6 weeks.
"""
DOCUMENTS_003 = [
    {"resourceType": "DocumentReference", "id": "doc-003-1", "status": "current", "date": "2026-01-20",
     "type": {"text": "Progress Note"}, "subject": {"reference": "Patient/synth-003"},
     "content": [{"attachment": {"contentType": "text/plain",
         "data": base64.b64encode(NOTE_TEXT_003.encode()).decode()}}]},
]
ENCOUNTERS_003 = [
    {"resourceType": "Encounter", "id": "enc-003-1", "status": "finished",
     "class": {"code": "AMB"}, "type": [{"text": "Office Visit"}],
     "subject": {"reference": "Patient/synth-003"},
     "period": {"start": "2026-01-20"}},
]

# ══════════════════════════════════════════════════════════
# DATA REGISTRY
# ══════════════════════════════════════════════════════════
DATA = {
    "Patient": PATIENTS,
    "Observation": {
        "synth-001": OBSERVATIONS_001,
        "synth-002": OBSERVATIONS_002,
        "synth-003": OBSERVATIONS_003,
    },
    "Condition": {
        "synth-001": CONDITIONS_001,
        "synth-002": CONDITIONS_002,
        "synth-003": CONDITIONS_003,
    },
    "MedicationRequest": {
        "synth-001": MEDICATIONS_001,
        "synth-002": MEDICATIONS_002,
        "synth-003": MEDICATIONS_003,
    },
    "DocumentReference": {
        "synth-001": DOCUMENTS_001,
        "synth-002": DOCUMENTS_002,
        "synth-003": DOCUMENTS_003,
    },
    "Encounter": {
        "synth-001": ENCOUNTERS_001,
        "synth-002": ENCOUNTERS_002,
        "synth-003": ENCOUNTERS_003,
    },
    "Procedure": {},
}


# ══════════════════════════════════════════════════════════
# FHIR REST ENDPOINTS
# ══════════════════════════════════════════════════════════

@mock_fhir.get("/metadata")
async def capability_statement():
    return {"resourceType": "CapabilityStatement", "status": "active", "fhirVersion": "4.0.1"}


@mock_fhir.get("/{resource_type}/{resource_id}")
async def read_resource(resource_type: str, resource_id: str):
    if resource_type == "Patient":
        pt = PATIENTS.get(resource_id)
        if pt:
            return pt
    return JSONResponse(status_code=404, content={"error": "Not found"})


@mock_fhir.get("/{resource_type}")
async def search_resource(resource_type: str, request: Request):
    params = dict(request.query_params)
    patient_id = params.get("patient", params.get("subject", ""))

    if resource_type == "Patient":
        count = int(params.get("_count", "100"))
        entries = [{"resource": p} for p in list(PATIENTS.values())[:count]]
        return {"resourceType": "Bundle", "type": "searchset", "entry": entries}

    resource_data = DATA.get(resource_type, {})
    entries_list = resource_data.get(patient_id, [])
    entries = [{"resource": r} for r in entries_list]
    return {"resourceType": "Bundle", "type": "searchset", "entry": entries}


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8080))
    print(f"Mock FHIR R4 Server starting on {port}")
    print("Patients: synth-001 (Maria Rodriguez), synth-002 (James Thompson), synth-003 (Sarah Chen)")
    uvicorn.run(mock_fhir, host="0.0.0.0", port=port)
