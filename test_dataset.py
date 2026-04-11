"""
Comprehensive Test Dataset — 10 Synthea-style Patients
Each patient is designed to test specific pipeline features:

Patient 1: Maria Rodriguez    — Diabetes upgrade (E11.9→E11.65) + CKD + hyperlipidemia + anemia
Patient 2: James Thompson     — Heart failure + COPD (uncoded, medication evidence)
Patient 3: Sarah Chen         — Depression + hypothyroidism (uncoded, medication-only)
Patient 4: Robert Williams    — Multi-morbid: DM2 + CKD + CHF combo codes
Patient 5: Patricia Davis     — Negation test: "no diabetes", "denies CHF" should NOT be flagged
Patient 6: Michael Johnson    — Medication-only gaps: on metformin+statin but nothing coded
Patient 7: Linda Martinez     — Lab-only gaps: abnormal labs, no notes, no meds
Patient 8: David Anderson     — Section detection: conditions in HPI vs Assessment/Plan
Patient 9: Jennifer Wilson    — Screening mentions: "screening for depression" should NOT be flagged
Patient 10: William Taylor    — Complex: 5+ conditions, some coded, some not, specificity upgrades
"""
import base64
import logging
from typing import Dict, List

log = logging.getLogger("gapdetect.testdata")


def build_test_patients() -> Dict:
    """Returns complete test dataset for all 10 patients."""
    return {
        "patients": _build_patients(),
        "observations": _build_observations(),
        "conditions": _build_conditions(),
        "medications": _build_medications(),
        "documents": _build_documents(),
        "encounters": _build_encounters(),
    }


def get_patient_profile(patient_id: str, dataset: Dict = None) -> Dict:
    """Build a profile dict matching the FHIR adapter output format."""
    if dataset is None:
        dataset = build_test_patients()

    patient = dataset["patients"].get(patient_id)
    if not patient:
        return {"fhir_patient_id": patient_id, "error": "Not found"}

    obs = dataset["observations"].get(patient_id, [])
    conds = dataset["conditions"].get(patient_id, [])
    meds = dataset["medications"].get(patient_id, [])
    docs = dataset["documents"].get(patient_id, [])
    encs = dataset["encounters"].get(patient_id, [])

    # Decode notes
    notes = []
    for doc in docs:
        for content in doc.get("content", []):
            att = content.get("attachment", {})
            data = att.get("data", "")
            if data:
                text = base64.b64decode(data).decode("utf-8", errors="replace")
                notes.append({
                    "attachment_id": doc.get("id", ""),
                    "doc_type": doc.get("type", {}).get("text", "Progress Note"),
                    "doc_date": doc.get("date", "")[:10] if doc.get("date") else "",
                    "content_type": att.get("contentType", "text/plain"),
                    "text": text,
                })

    # Parse observations
    parsed_obs = []
    for o in obs:
        code = o.get("code", {})
        codings = code.get("coding", [{}])
        vq = o.get("valueQuantity", {})
        parsed_obs.append({
            "observation_id": o.get("id", ""),
            "loinc": codings[0].get("code", "") if codings else "",
            "name": codings[0].get("display", "") if codings else code.get("text", ""),
            "value": vq.get("value"),
            "unit": vq.get("unit", ""),
            "date": (o.get("effectiveDateTime", "") or "")[:10],
            "status": o.get("status", "final"),
            "ref_range_low": None,
            "ref_range_high": None,
            "interpretation": "",
        })

    # Parse conditions
    parsed_conds = []
    for c in conds:
        code = c.get("code", {})
        codings = code.get("coding", [{}])
        cs = c.get("clinicalStatus", {}).get("coding", [{}])
        parsed_conds.append({
            "condition_id": c.get("id", ""),
            "icd10_code": codings[0].get("code", "") if codings else "",
            "display": codings[0].get("display", "") if codings else code.get("text", ""),
            "clinical_status": cs[0].get("code", "") if cs else "active",
            "verification_status": "confirmed",
            "onset_date": "",
            "recorded_date": "",
        })

    # Parse medications
    parsed_meds = []
    for m in meds:
        mc = m.get("medicationCodeableConcept", {})
        mc_codings = mc.get("coding", [{}])
        dosage = m.get("dosageInstruction", [{}])
        parsed_meds.append({
            "medication_id": m.get("id", ""),
            "name": mc_codings[0].get("display", "") if mc_codings else mc.get("text", ""),
            "code": mc_codings[0].get("code", "") if mc_codings else "",
            "status": m.get("status", "active"),
            "dosage": dosage[0].get("text", "") if dosage else "",
            "date": (m.get("authoredOn", "") or "")[:10],
        })

    # Parse encounters
    parsed_encs = []
    for e in encs:
        period = e.get("period", {})
        enc_types = e.get("type", [{}])
        parsed_encs.append({
            "encounter_id": e.get("id", ""),
            "type": enc_types[0].get("text", "") if enc_types else "",
            "status": e.get("status", "finished"),
            "start_date": (period.get("start", "") or "")[:10],
            "end_date": (period.get("end", "") or "")[:10],
            "class": e.get("class", {}).get("code", "AMB"),
        })

    coded_set = {c["icd10_code"] for c in parsed_conds if c.get("icd10_code")}

    return {
        "fhir_patient_id": patient_id,
        "ensure_patient_id": patient_id,
        "demographics": _parse_demographics(patient),
        "clinical_notes": notes,
        "observations": parsed_obs,
        "medications": parsed_meds,
        "conditions": parsed_conds,
        "encounters": parsed_encs,
        "procedures": [],
        "claims_codes": coded_set,
    }


def _parse_demographics(pt: Dict) -> Dict:
    names = pt.get("name", [{}])
    n = names[0] if names else {}
    given = " ".join(n.get("given", []))
    family = n.get("family", "")
    from datetime import datetime, date
    dob = pt.get("birthDate", "")
    age = None
    if dob:
        try:
            d = datetime.strptime(dob[:10], "%Y-%m-%d").date()
            age = (date.today() - d).days // 365
        except: pass
    return {
        "patient_id": pt.get("id"), "found": True,
        "first_name": given, "last_name": family,
        "full_name": f"{given} {family}".strip(),
        "dob": dob, "age": age, "gender": pt.get("gender", ""),
        "ensure_patient_id": pt.get("id"),
    }


# ═══════════════════════════════════════
# PATIENT DEFINITIONS
# ═══════════════════════════════════════

def _build_patients() -> Dict:
    return {
        "pt-001": {"resourceType": "Patient", "id": "pt-001", "name": [{"given": ["Maria", "Elena"], "family": "Rodriguez"}], "gender": "female", "birthDate": "1958-03-14"},
        "pt-002": {"resourceType": "Patient", "id": "pt-002", "name": [{"given": ["James"], "family": "Thompson"}], "gender": "male", "birthDate": "1965-11-22"},
        "pt-003": {"resourceType": "Patient", "id": "pt-003", "name": [{"given": ["Sarah"], "family": "Chen"}], "gender": "female", "birthDate": "1972-07-08"},
        "pt-004": {"resourceType": "Patient", "id": "pt-004", "name": [{"given": ["Robert"], "family": "Williams"}], "gender": "male", "birthDate": "1955-01-30"},
        "pt-005": {"resourceType": "Patient", "id": "pt-005", "name": [{"given": ["Patricia"], "family": "Davis"}], "gender": "female", "birthDate": "1970-09-12"},
        "pt-006": {"resourceType": "Patient", "id": "pt-006", "name": [{"given": ["Michael"], "family": "Johnson"}], "gender": "male", "birthDate": "1962-04-18"},
        "pt-007": {"resourceType": "Patient", "id": "pt-007", "name": [{"given": ["Linda"], "family": "Martinez"}], "gender": "female", "birthDate": "1968-12-05"},
        "pt-008": {"resourceType": "Patient", "id": "pt-008", "name": [{"given": ["David"], "family": "Anderson"}], "gender": "male", "birthDate": "1960-06-22"},
        "pt-009": {"resourceType": "Patient", "id": "pt-009", "name": [{"given": ["Jennifer"], "family": "Wilson"}], "gender": "female", "birthDate": "1975-08-30"},
        "pt-010": {"resourceType": "Patient", "id": "pt-010", "name": [{"given": ["William"], "family": "Taylor"}], "gender": "male", "birthDate": "1952-02-14"},
    }


def _obs(oid, pid, loinc, name, value, unit, date="2026-01-15"):
    return {"resourceType": "Observation", "id": oid, "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc, "display": name}]},
            "subject": {"reference": f"Patient/{pid}"},
            "effectiveDateTime": date,
            "valueQuantity": {"value": value, "unit": unit}}


def _cond(cid, pid, icd10, display, status="active"):
    return {"resourceType": "Condition", "id": cid,
            "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": icd10, "display": display}]},
            "subject": {"reference": f"Patient/{pid}"},
            "clinicalStatus": {"coding": [{"code": status}]}}


def _med(mid, pid, name, status="active", date="2025-01-01"):
    return {"resourceType": "MedicationRequest", "id": mid, "status": status,
            "medicationCodeableConcept": {"coding": [{"display": name}]},
            "subject": {"reference": f"Patient/{pid}"}, "authoredOn": date}


def _doc(did, pid, text, date="2026-01-15"):
    return {"resourceType": "DocumentReference", "id": did, "status": "current", "date": date,
            "type": {"text": "Progress Note"}, "subject": {"reference": f"Patient/{pid}"},
            "content": [{"attachment": {"contentType": "text/plain",
                         "data": base64.b64encode(text.encode()).decode()}}]}


def _enc(eid, pid, date="2026-01-15"):
    return {"resourceType": "Encounter", "id": eid, "status": "finished",
            "class": {"code": "AMB"}, "type": [{"text": "Office Visit"}],
            "subject": {"reference": f"Patient/{pid}"},
            "period": {"start": date}}


def _build_observations() -> Dict:
    return {
        # Patient 1: Diabetes + CKD + hyperlipidemia + anemia
        "pt-001": [
            _obs("o1-1", "pt-001", "4548-4", "HbA1c", 8.4, "%"),
            _obs("o1-2", "pt-001", "33914-3", "eGFR", 48, "mL/min/1.73m2"),
            _obs("o1-3", "pt-001", "2089-1", "LDL", 198, "mg/dL"),
            _obs("o1-4", "pt-001", "718-7", "Hemoglobin", 11.2, "g/dL"),
            _obs("o1-5", "pt-001", "2571-8", "Triglycerides", 220, "mg/dL"),
            _obs("o1-6", "pt-001", "2160-0", "Creatinine", 1.8, "mg/dL"),
        ],
        # Patient 2: Heart failure labs
        "pt-002": [
            _obs("o2-1", "pt-002", "42637-9", "BNP", 580, "pg/mL"),
            _obs("o2-2", "pt-002", "4548-4", "HbA1c", 5.4, "%"),
        ],
        # Patient 3: Thyroid
        "pt-003": [
            _obs("o3-1", "pt-003", "3016-3", "TSH", 8.2, "mIU/L"),
        ],
        # Patient 4: Multi-morbid
        "pt-004": [
            _obs("o4-1", "pt-004", "4548-4", "HbA1c", 9.1, "%"),
            _obs("o4-2", "pt-004", "33914-3", "eGFR", 38, "mL/min/1.73m2"),
            _obs("o4-3", "pt-004", "42637-9", "BNP", 720, "pg/mL"),
            _obs("o4-4", "pt-004", "718-7", "Hemoglobin", 10.5, "g/dL"),
            _obs("o4-5", "pt-004", "2093-3", "Total Cholesterol", 265, "mg/dL"),
        ],
        # Patient 5: Normal labs (negation test)
        "pt-005": [
            _obs("o5-1", "pt-005", "4548-4", "HbA1c", 5.2, "%"),
            _obs("o5-2", "pt-005", "33914-3", "eGFR", 92, "mL/min/1.73m2"),
            _obs("o5-3", "pt-005", "718-7", "Hemoglobin", 14.1, "g/dL"),
        ],
        # Patient 6: No labs (medication-only)
        "pt-006": [],
        # Patient 7: Labs only, no notes or meds
        "pt-007": [
            _obs("o7-1", "pt-007", "4548-4", "HbA1c", 7.2, "%"),
            _obs("o7-2", "pt-007", "3016-3", "TSH", 12.5, "mIU/L"),
            _obs("o7-3", "pt-007", "2498-4", "Ferritin", 8, "ng/mL"),
            _obs("o7-4", "pt-007", "1989-3", "Vitamin D", 15, "ng/mL"),
            _obs("o7-5", "pt-007", "3084-1", "Uric Acid", 9.2, "mg/dL"),
        ],
        # Patient 8: Normal labs
        "pt-008": [
            _obs("o8-1", "pt-008", "4548-4", "HbA1c", 6.8, "%"),
            _obs("o8-2", "pt-008", "2089-1", "LDL", 165, "mg/dL"),
        ],
        # Patient 9: Normal
        "pt-009": [
            _obs("o9-1", "pt-009", "4548-4", "HbA1c", 5.1, "%"),
        ],
        # Patient 10: Complex
        "pt-010": [
            _obs("o10-1", "pt-010", "4548-4", "HbA1c", 8.8, "%"),
            _obs("o10-2", "pt-010", "33914-3", "eGFR", 42, "mL/min/1.73m2"),
            _obs("o10-3", "pt-010", "2089-1", "LDL", 210, "mg/dL"),
            _obs("o10-4", "pt-010", "3016-3", "TSH", 6.8, "mIU/L"),
            _obs("o10-5", "pt-010", "718-7", "Hemoglobin", 10.8, "g/dL"),
            _obs("o10-6", "pt-010", "42637-9", "BNP", 450, "pg/mL"),
            _obs("o10-7", "pt-010", "1742-6", "ALT", 72, "U/L"),
        ],
    }


def _build_conditions() -> Dict:
    return {
        # Patient 1: E11.9 coded (too vague) + I10
        "pt-001": [
            _cond("c1-1", "pt-001", "E11.9", "Type 2 DM unspecified"),
            _cond("c1-2", "pt-001", "I10", "Essential hypertension"),
        ],
        # Patient 2: Only I10 coded
        "pt-002": [_cond("c2-1", "pt-002", "I10", "Essential hypertension")],
        # Patient 3: Nothing coded
        "pt-003": [],
        # Patient 4: E11.9 + I10 + N18.3 (but missing combos and upgrades)
        "pt-004": [
            _cond("c4-1", "pt-004", "E11.9", "Type 2 DM unspecified"),
            _cond("c4-2", "pt-004", "I10", "Essential hypertension"),
            _cond("c4-3", "pt-004", "N18.3", "CKD Stage 3"),
        ],
        # Patient 5: Already has everything coded
        "pt-005": [
            _cond("c5-1", "pt-005", "E11.9", "Type 2 DM"),
            _cond("c5-2", "pt-005", "I10", "HTN"),
            _cond("c5-3", "pt-005", "E78.5", "Hyperlipidemia"),
        ],
        # Patient 6: NOTHING coded
        "pt-006": [],
        # Patient 7: NOTHING coded
        "pt-007": [],
        # Patient 8: Only E11.9
        "pt-008": [_cond("c8-1", "pt-008", "E11.9", "Type 2 DM")],
        # Patient 9: E78.5 coded
        "pt-009": [_cond("c9-1", "pt-009", "E78.5", "Hyperlipidemia")],
        # Patient 10: E11.9 + I10 only
        "pt-010": [
            _cond("c10-1", "pt-010", "E11.9", "Type 2 DM"),
            _cond("c10-2", "pt-010", "I10", "HTN"),
        ],
    }


def _build_medications() -> Dict:
    return {
        "pt-001": [_med("m1-1", "pt-001", "Metformin 1000mg"), _med("m1-2", "pt-001", "Lisinopril 20mg"), _med("m1-3", "pt-001", "Atorvastatin 40mg")],
        "pt-002": [_med("m2-1", "pt-002", "Furosemide 40mg"), _med("m2-2", "pt-002", "Carvedilol 12.5mg"), _med("m2-3", "pt-002", "Tiotropium 18mcg"), _med("m2-4", "pt-002", "Albuterol inhaler")],
        "pt-003": [_med("m3-1", "pt-003", "Sertraline 100mg"), _med("m3-2", "pt-003", "Levothyroxine 75mcg")],
        "pt-004": [_med("m4-1", "pt-004", "Insulin glargine"), _med("m4-2", "pt-004", "Metformin 1000mg"), _med("m4-3", "pt-004", "Furosemide 80mg"), _med("m4-4", "pt-004", "Carvedilol 25mg"), _med("m4-5", "pt-004", "Losartan 100mg"), _med("m4-6", "pt-004", "Atorvastatin 80mg")],
        "pt-005": [],  # No meds
        "pt-006": [_med("m6-1", "pt-006", "Metformin 500mg"), _med("m6-2", "pt-006", "Rosuvastatin 10mg"), _med("m6-3", "pt-006", "Amlodipine 5mg"), _med("m6-4", "pt-006", "Omeprazole 20mg"), _med("m6-5", "pt-006", "Sertraline 50mg")],
        "pt-007": [],  # No meds
        "pt-008": [_med("m8-1", "pt-008", "Metformin 1000mg"), _med("m8-2", "pt-008", "Atorvastatin 20mg")],
        "pt-009": [_med("m9-1", "pt-009", "Escitalopram 10mg")],
        "pt-010": [_med("m10-1", "pt-010", "Insulin lispro"), _med("m10-2", "pt-010", "Metformin 1000mg"), _med("m10-3", "pt-010", "Furosemide 40mg"), _med("m10-4", "pt-010", "Metoprolol 50mg"), _med("m10-5", "pt-010", "Losartan 50mg"), _med("m10-6", "pt-010", "Atorvastatin 80mg"), _med("m10-7", "pt-010", "Levothyroxine 100mcg")],
    }


def _build_documents() -> Dict:
    return {
        "pt-001": [_doc("d1", "pt-001", NOTE_PT1)],
        "pt-002": [_doc("d2", "pt-002", NOTE_PT2)],
        "pt-003": [_doc("d3", "pt-003", NOTE_PT3)],
        "pt-004": [_doc("d4", "pt-004", NOTE_PT4)],
        "pt-005": [_doc("d5", "pt-005", NOTE_PT5)],
        "pt-006": [],  # No notes
        "pt-007": [],  # No notes
        "pt-008": [_doc("d8", "pt-008", NOTE_PT8)],
        "pt-009": [_doc("d9", "pt-009", NOTE_PT9)],
        "pt-010": [_doc("d10", "pt-010", NOTE_PT10)],
    }


def _build_encounters() -> Dict:
    return {pid: [_enc(f"e-{pid}", pid)] for pid in _build_patients().keys()}


# ═══════════════════════════════════════
# CLINICAL NOTES
# ═══════════════════════════════════════

NOTE_PT1 = """PROGRESS NOTE — Maria Rodriguez — 2026-01-15

HISTORY OF PRESENT ILLNESS:
68-year-old Hispanic female with Type 2 diabetes presents for follow-up.
Reports blurred vision and increased thirst. Compliant with Metformin.
Bilateral foot numbness progressing over past 3 months.

ASSESSMENT AND PLAN:
1. Type 2 diabetes mellitus — UNCONTROLLED with hyperglycemia. HbA1c risen from 7.8% to 8.4%.
   Developing peripheral neuropathy. Add Empagliflozin 10mg for glycemic and renal protection.
2. Chronic kidney disease, Stage 3 — eGFR 48, declining. Likely diabetic nephropathy.
   Continue ACE inhibitor. Refer nephrology if continues declining.
3. Hypercholesterolemia — LDL 198 despite Atorvastatin 40mg. Increase to 80mg.
4. Anemia — Hemoglobin 11.2. Likely anemia of chronic kidney disease. Check iron studies.
5. Hypertension — BP 142/88. Continue Lisinopril. Consider adding Amlodipine.
"""

NOTE_PT2 = """PROGRESS NOTE — James Thompson — 2026-02-10

ASSESSMENT AND PLAN:
1. Heart failure with reduced ejection fraction — EF 35% on last echo.
   BNP 580. Dyspnea on exertion, 2-pillow orthopnea. Continue Furosemide and Carvedilol.
2. COPD — stable on Tiotropium and albuterol PRN. No exacerbation.
3. Hypertension — controlled. Continue monitoring.
"""

NOTE_PT3 = """ASSESSMENT AND PLAN:
1. Major depressive disorder — stable on Sertraline 100mg. PHQ-9 score 8, improved from 14.
2. Hypothyroidism — TSH 8.2, elevated. Increase Levothyroxine to 88mcg. Recheck in 6 weeks.
"""

NOTE_PT4 = """PROGRESS NOTE — Robert Williams — 2026-01-20

ASSESSMENT AND PLAN:
1. Type 2 diabetes mellitus — POORLY CONTROLLED. HbA1c 9.1%. On insulin glargine + metformin.
   Increasing insulin dose. Peripheral neuropathy bilateral feet. Diabetic nephropathy progressing.
2. Chronic kidney disease Stage 3b — eGFR 38. Worsening. Likely diabetic nephropathy.
   Continue Losartan for renal protection. Avoid nephrotoxic medications.
3. Heart failure with reduced ejection fraction — EF 30%. BNP 720.
   Significant fluid overload. Increase Furosemide to 80mg BID. Continue Carvedilol.
4. Anemia of chronic disease — Hgb 10.5. In setting of CKD + CHF. Check EPO level.
5. Hypercholesterolemia — Total cholesterol 265. On max dose Atorvastatin. Add Ezetimibe.
"""

NOTE_PT5 = """PROGRESS NOTE — Patricia Davis — 2026-01-25

HISTORY OF PRESENT ILLNESS:
56-year-old female presents for annual physical.
Family history of diabetes in mother and sister.

ASSESSMENT AND PLAN:
1. No evidence of diabetes — HbA1c 5.2%, normal. Family history noted.
   Patient denies any symptoms of diabetes. Continue monitoring annually.
2. No history of kidney disease — eGFR 92, normal.
3. Denies depression or anxiety. PHQ-9 score 2 (minimal).
4. Rule out hypothyroidism — patient reports fatigue. Check TSH.
5. No signs of heart failure or COPD.
"""

NOTE_PT8 = """PROGRESS NOTE — David Anderson — 2026-02-05

HISTORY OF PRESENT ILLNESS:
66-year-old male presents with fatigue and polyuria. Has diabetes on metformin.
Patient mentions his cholesterol has been high lately.
Grandmother had heart failure. Father had stroke.

PHYSICAL EXAM:
VS: BP 138/86. Well-appearing.

ASSESSMENT AND PLAN:
1. Type 2 diabetes mellitus — HbA1c 6.8%, borderline controlled.
   Continue Metformin. Reinforce diet and exercise.
2. Hyperlipidemia — LDL 165. On Atorvastatin 20mg. May need dose increase.
"""

NOTE_PT9 = """PROGRESS NOTE — Jennifer Wilson — 2026-02-08

ASSESSMENT AND PLAN:
1. Screening for depression — PHQ-9 administered as part of annual wellness visit.
   Score 4 (minimal). No treatment indicated at this time.
2. Screening for colon cancer — due for colonoscopy. Referral placed.
3. Possible anxiety — patient reports occasional worry about work stress.
   Not meeting criteria for GAD at this time. Reassess at next visit.
4. Hyperlipidemia — stable on current regimen.
"""

NOTE_PT10 = """PROGRESS NOTE — William Taylor — 2026-01-28

ASSESSMENT AND PLAN:
1. Type 2 diabetes mellitus — UNCONTROLLED. HbA1c 8.8%. On insulin lispro + metformin.
   Developing diabetic nephropathy (eGFR 42, declining). Diabetic peripheral neuropathy present.
   Adjust insulin regimen. Add Empagliflozin for renal protection.
2. Chronic kidney disease Stage 3b — eGFR 42. Related to diabetic nephropathy.
   Continue Losartan. Monitor closely.
3. Heart failure — BNP 450. NYHA Class II. Continue Furosemide + Metoprolol.
   Recent echo showed EF 40%.
4. Hypothyroidism — TSH 6.8. On Levothyroxine 100mcg. May need dose adjustment.
5. Hypercholesterolemia — LDL 210. On max Atorvastatin. Add Ezetimibe.
6. Anemia — Hgb 10.8. Multifactorial: CKD + chronic disease. Check iron/B12/folate.
7. Liver enzyme elevation — ALT 72. Monitor. Possible NAFLD given metabolic syndrome.
   Hepatitis panel negative.
8. Obstructive sleep apnea — on CPAP. Compliant per download.
"""
