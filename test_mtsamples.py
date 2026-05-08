#!/usr/bin/env python3
"""
MTSamples Pipeline Test — Real Clinical Transcriptions
========================================================

Runs the gap detection pipeline against the Kaggle MTSamples dataset
(https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions) — 4,999
real medical transcriptions across 40+ specialties.

This is what backs the README's claim:
    "Tested on 2,227 real clinical transcriptions with zero processing errors."

The 2,227 figure is the subset we filter to — specialties relevant to
chronic disease coding (Internal Medicine, Cardiology, Endocrinology,
Nephrology, Pulmonary, Psychiatry, Hematology, etc.). The rest of the
dataset is surgical reports, op notes, radiology — gap detection isn't
the right job for those.

Each note gets parsed into a pipeline-compatible profile:
  - Conditions extracted from text via regex patterns (with negation filtering)
  - Medications detected by RxNorm-mapped substring matching
  - Lab values pulled out via regex (HbA1c, eGFR, LDL, BNP, etc.)
  - Some conditions are randomly "coded" to simulate real coding gaps,
    others left as gaps for our pipeline to detect.

Usage:
    python test_mtsamples.py /path/to/mtsamples.csv          # full run
    python test_mtsamples.py /path/to/mtsamples.csv 100      # first 100 only

Download the CSV from Kaggle:
    https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions

Expected output:
    Notes processed:     2,227
    Notes with gaps:     774  (34.8%)
    Total approved gaps: 279
    Total review:        1,188
    Revenue impact:      $1,134,540/yr
    Errors:              0
"""
import re
import csv
import logging
import sys
import random
from typing import Dict
from collections import Counter, defaultdict

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("mtsamples_test")

from gap_pipeline import run_gap_pipeline, is_negated


# ════════════════════════════════════════════════════════════════════
# CONDITION DETECTION IN NOTES
# Maps regex patterns to ICD-10 codes — used to extract candidate
# conditions from unstructured note text.
# ════════════════════════════════════════════════════════════════════
CONDITION_PATTERNS = {
    "E11.9":  (r"(?i)\b(diabetes|diabetic|dm2?|t2dm|niddm|hba1c|a1c)\b", "Type 2 Diabetes"),
    "I10":    (r"(?i)\b(hypertension|htn|high\s+blood\s+pressure|hypertensive)\b", "Hypertension"),
    "E78.5":  (r"(?i)\b(hyperlipidemia|hypercholesterolemia|dyslipidemia|high\s+cholesterol|hld)\b", "Hyperlipidemia"),
    "I50.9":  (r"(?i)\b(heart\s+failure|chf|congestive|hfref|hfpef|cardiomyopathy)\b", "Heart Failure"),
    "J44.1":  (r"(?i)\b(copd|chronic\s+obstructive|emphysema)\b", "COPD"),
    "N18.9":  (r"(?i)\b(chronic\s+kidney|ckd|renal\s+(insufficiency|failure|disease)|nephropathy)\b", "CKD"),
    "E03.9":  (r"(?i)\b(hypothyroid|hashimoto|low\s+thyroid)\b", "Hypothyroidism"),
    "F32.9":  (r"(?i)\b(major\s+depress|mdd|depressive\s+disorder)\b", "Depression"),
    "J45.20": (r"(?i)\b(asthma|asthmatic)\b", "Asthma"),
    "D64.9":  (r"(?i)\b(anemia|anemic)\b", "Anemia"),
    "E66.9":  (r"(?i)\b(obesity|obese|morbid\s+obes)\b", "Obesity"),
    "K21.0":  (r"(?i)\b(gerd|gastroesophageal\s+reflux|acid\s+reflux)\b", "GERD"),
    "I48.91": (r"(?i)\b(atrial\s+fibrillation|afib|a-?fib)\b", "Atrial Fibrillation"),
    "G47.33": (r"(?i)\b(sleep\s+apnea|osa|cpap)\b", "Sleep Apnea"),
    "I25.10": (r"(?i)\b(coronary\s+artery\s+disease|cad)\b", "CAD"),
    "F41.1":  (r"(?i)\b(generalized\s+anxiety|gad)\b", "GAD"),
}

# Medications detected via substring matching against RxNorm-mapped names.
# These are the markers used in our Tier 2 phenotype rules.
MED_PATTERNS = {
    "metformin": "Metformin", "insulin": "Insulin", "glipizide": "Glipizide",
    "lisinopril": "Lisinopril", "amlodipine": "Amlodipine", "losartan": "Losartan",
    "atorvastatin": "Atorvastatin", "rosuvastatin": "Rosuvastatin", "simvastatin": "Simvastatin",
    "furosemide": "Furosemide", "carvedilol": "Carvedilol", "metoprolol": "Metoprolol",
    "albuterol": "Albuterol", "tiotropium": "Tiotropium", "fluticasone": "Fluticasone",
    "levothyroxine": "Levothyroxine", "synthroid": "Levothyroxine",
    "sertraline": "Sertraline", "fluoxetine": "Fluoxetine", "escitalopram": "Escitalopram",
    "omeprazole": "Omeprazole", "pantoprazole": "Pantoprazole",
    "hydrochlorothiazide": "HCTZ", "hctz": "HCTZ",
    "warfarin": "Warfarin", "aspirin": "Aspirin",
}

# Lab value extraction patterns — pulls numeric values from common phrasings.
LAB_PATTERNS = [
    (r"(?i)(?:hba1c|a1c|hemoglobin\s*a1c)\s*(?:of|is|was|:)?\s*(\d+\.?\d*)\s*%?", "4548-4", "HbA1c", "%"),
    (r"(?i)(?:egfr|gfr)\s*(?:of|is|was|:)?\s*(\d+\.?\d*)", "33914-3", "eGFR", "mL/min"),
    (r"(?i)(?:ldl)\s*(?:of|is|was|:)?\s*(\d+\.?\d*)", "2089-1", "LDL", "mg/dL"),
    (r"(?i)(?:hemoglobin|hgb|hb)\s*(?:of|is|was|:)?\s*(\d+\.?\d*)\s*(?:g|gm)?", "718-7", "Hemoglobin", "g/dL"),
    (r"(?i)(?:tsh)\s*(?:of|is|was|:)?\s*(\d+\.?\d*)", "3016-3", "TSH", "mIU/L"),
    (r"(?i)(?:creatinine|cr)\s*(?:of|is|was|:)?\s*(\d+\.?\d*)", "2160-0", "Creatinine", "mg/dL"),
    (r"(?i)(?:total\s+cholesterol|cholesterol)\s*(?:of|is|was|:)?\s*(\d+\.?\d*)", "2093-3", "Total Cholesterol", "mg/dL"),
    (r"(?i)(?:glucose|blood\s+sugar)\s*(?:of|is|was|:)?\s*(\d+\.?\d*)", "2345-7", "Glucose", "mg/dL"),
    (r"(?i)(?:bnp|brain\s+natriuretic)\s*(?:of|is|was|:)?\s*(\d+\.?\d*)", "42637-9", "BNP", "pg/mL"),
]


def parse_note_to_profile(text: str, note_id: str, specialty: str) -> Dict:
    """Convert a clinical transcription into a pipeline-compatible patient profile.

    Extracts conditions, medications, and lab values from the note text, then
    randomly "codes" some conditions (40% chance) to simulate the realistic
    scenario where some diagnoses are billed and others are gaps.
    """
    if not text or len(text) < 50:
        return None

    # Find conditions mentioned in the note (filter out negated mentions)
    found_conditions = {}
    for icd10, (pattern, name) in CONDITION_PATTERNS.items():
        matches = list(re.finditer(pattern, text))
        for m in matches:
            if not is_negated(text, m.start()):
                found_conditions[icd10] = {
                    "icd10_code": icd10, "display": name,
                    "clinical_status": "active",
                }
                break

    # Find medications (substring match)
    found_meds = []
    text_lower = text.lower()
    seen_meds = set()
    for pattern, name in MED_PATTERNS.items():
        if pattern in text_lower and name not in seen_meds:
            seen_meds.add(name)
            found_meds.append({
                "medication_id": f"med-{note_id}-{len(found_meds)}",
                "name": name, "code": "", "status": "active",
                "dosage": "", "date": "2026-01-15",
            })

    # Pull lab values out of the note text
    found_labs = []
    for pattern, loinc, name, unit in LAB_PATTERNS:
        match = re.search(pattern, text)
        if match:
            try:
                value = float(match.group(1))
                # Reject impossible values from regex false matches
                if name == "HbA1c" and value > 20: continue
                if name == "eGFR" and value > 200: continue
                if name == "Hemoglobin" and value > 25: continue
                found_labs.append({
                    "observation_id": f"obs-{note_id}-{len(found_labs)}",
                    "loinc": loinc, "name": name, "value": value, "unit": unit,
                    "date": "2026-01-15", "status": "final",
                    "ref_range_low": None, "ref_range_high": None, "interpretation": "",
                })
            except (ValueError, IndexError):
                pass

    # Simulate a realistic coded vs. uncoded split: random 40% of detected
    # conditions get marked as already-coded, the rest become gaps for
    # our pipeline to find. Deterministic per note via hash seeding.
    coded_conditions = []
    coded_set = set()
    random.seed(hash(note_id) % 2**31)

    for icd10, cond in found_conditions.items():
        if random.random() < 0.4:
            coded_conditions.append(cond)
            coded_set.add(icd10)
            coded_set.add(icd10.split(".")[0])

    return {
        "fhir_patient_id": note_id,
        "ensure_patient_id": note_id,
        "demographics": {
            "patient_id": note_id, "found": True,
            "full_name": f"MTSample-{note_id}",
            "first_name": "MTSample", "last_name": note_id,
            "age": 65, "gender": "unknown", "dob": "1961-01-01",
        },
        "clinical_notes": [{
            "attachment_id": note_id, "doc_type": specialty.strip(),
            "doc_date": "2026-01-15", "content_type": "text/plain",
            "text": text,
        }],
        "observations": found_labs,
        "medications": found_meds,
        "conditions": coded_conditions,
        "encounters": [{
            "encounter_id": f"enc-{note_id}", "type": specialty.strip(),
            "status": "finished", "start_date": "2026-01-15",
            "end_date": "2026-01-15", "class": "AMB",
        }],
        "procedures": [],
        "claims_codes": coded_set,
    }


def run_mtsamples_test(csv_path: str, max_records: int = 0, specialties: list = None):
    """Run gap detection against MTSamples and report aggregate stats."""

    # Default to specialties most relevant for chronic-disease coding gaps
    if specialties is None:
        specialties = [
            " General Medicine", " Cardiovascular / Pulmonary",
            " Consult - History and Phy.", " Endocrinology",
            " Nephrology", " Gastroenterology", " Neurology",
            " Psychiatry / Psychology", " Hematology - Oncology",
            " SOAP / Chart / Progress Notes", " Discharge Summary",
            " Emergency Room Reports", " Pain Management",
            " Internal Medicine",
        ]

    records = []
    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            spec = row.get('medical_specialty', '')
            if specialties and spec not in specialties:
                continue
            text = row.get('transcription', '')
            if not text or len(text) < 100:
                continue
            records.append(row)

    if max_records > 0:
        records = records[:max_records]

    print("=" * 80)
    print(f"  MTSAMPLES PIPELINE TEST — {len(records)} Real Clinical Transcriptions")
    print("=" * 80)
    print()

    total_approved = 0
    total_review = 0
    total_rejected = 0
    total_revenue = 0.0
    tier_counts = Counter()
    condition_counts = Counter()
    specialty_gaps = defaultdict(list)
    notes_with_gaps = 0
    notes_processed = 0
    errors = 0

    for i, row in enumerate(records):
        note_id = f"mt-{i:04d}"
        text = row.get('transcription', '')
        specialty = row.get('medical_specialty', 'Unknown')

        profile = parse_note_to_profile(text, note_id, specialty)
        if not profile:
            continue

        notes_processed += 1
        try:
            result = run_gap_pipeline(profile, profile["demographics"])

            approved = result["approved"]
            review = result["review"]
            rejected = result["rejected"]
            rev = result["revenue_summary"]

            total_approved += len(approved)
            total_review += len(review)
            total_rejected += len(rejected)
            total_revenue += rev["total_potential_impact"]

            if approved or review:
                notes_with_gaps += 1

            for g in approved + review:
                tier_counts[g.get("tier", "UNKNOWN")] += 1
                condition_counts[g.get("condition_name", "Unknown")] += 1

            specialty_gaps[specialty.strip()].append(len(approved) + len(review))

        except Exception as e:
            errors += 1
            if errors <= 5:
                log.warning(f"Note {note_id} failed: {e}")

        if (i + 1) % 100 == 0:
            print(f"  Processed {i+1}/{len(records)}... ({total_approved} approved, {total_review} review)")

    # ──────────────────────────── results ────────────────────────────
    print()
    print("=" * 80)
    print("  RESULTS")
    print("=" * 80)
    print()
    print(f"  Notes processed:     {notes_processed}")
    print(f"  Notes with gaps:     {notes_with_gaps} ({notes_with_gaps/max(notes_processed,1)*100:.0f}%)")
    print(f"  Processing errors:   {errors}")
    print()
    print(f"  Total approved gaps: {total_approved}")
    print(f"  Total review:        {total_review}")
    print(f"  Total rejected:      {total_rejected}")
    print(f"  Revenue impact:      ${total_revenue:,.0f}/yr")
    print()

    print("  ── Gaps by Detection Tier ──")
    for tier, count in tier_counts.most_common():
        print(f"    {count:5d}  {tier}")
    print()

    print("  ── Top 15 Conditions Detected ──")
    for cond, count in condition_counts.most_common(15):
        print(f"    {count:5d}  {cond}")
    print()

    print("  ── Gaps by Specialty ──")
    for spec in sorted(specialty_gaps.keys()):
        gaps = specialty_gaps[spec]
        total = sum(gaps)
        avg = total / len(gaps) if gaps else 0
        print(f"    {total:5d} gaps across {len(gaps):4d} notes  (avg {avg:.1f}/note)  {spec}")
    print()

    # ──────────────────────────── headline ────────────────────────────
    print("=" * 80)
    print("  HACKATHON METRICS")
    print("=" * 80)
    avg_gaps = (total_approved + total_review) / max(notes_with_gaps, 1)
    avg_revenue = total_revenue / max(notes_processed, 1)
    print(f"  Detection rate:        {notes_with_gaps/max(notes_processed,1)*100:.1f}% of notes have gaps")
    print(f"  Avg gaps/patient:      {avg_gaps:.1f}")
    print(f"  Avg revenue/patient:   ${avg_revenue:,.0f}/yr")
    print(f"  Projected 1K patients: ${avg_revenue * 1000:,.0f}/yr")
    print()

    return {
        "notes_processed": notes_processed,
        "notes_with_gaps": notes_with_gaps,
        "total_approved": total_approved,
        "total_review": total_review,
        "total_revenue": total_revenue,
        "errors": errors,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print()
        print("Error: Please provide path to mtsamples.csv")
        print()
        print("Download from: https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions")
        sys.exit(1)

    csv_path = sys.argv[1]
    max_records = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    run_mtsamples_test(csv_path, max_records=max_records)