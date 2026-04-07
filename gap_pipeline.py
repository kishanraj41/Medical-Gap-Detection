"""
Gap Detection Pipeline — Lightweight version for MCP deployment
Runs core agents from v20 but adapted for CPU deployment.
Heavy models (ClinicalBERT, LLaMA) are optional — falls back to rule-based.
"""
import re
import logging
import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime

log = logging.getLogger("gapdetect.pipeline")

# ══════════════════════════════════════════════════════════
# LOINC → ICD-10 THRESHOLD MAPPINGS (from v20 Agent 10)
# ══════════════════════════════════════════════════════════

LOINC_ICD10_MAP = {
    # HbA1c → Diabetes
    "4548-4": {"name": "HbA1c", "thresholds": [
        {"op": ">=", "value": 6.5, "icd10": "E11.65", "condition": "Type 2 diabetes with hyperglycemia"},
        {"op": ">=", "value": 5.7, "icd10": "R73.03", "condition": "Prediabetes"},
    ]},
    # eGFR → CKD
    "33914-3": {"name": "eGFR", "thresholds": [
        {"op": "<", "value": 15, "icd10": "N18.5", "condition": "CKD Stage 5"},
        {"op": "<", "value": 30, "icd10": "N18.4", "condition": "CKD Stage 4"},
        {"op": "<", "value": 45, "icd10": "N18.3", "condition": "CKD Stage 3b"},
        {"op": "<", "value": 60, "icd10": "N18.3", "condition": "CKD Stage 3"},
    ]},
    # ALT → Liver
    "1742-6": {"name": "ALT", "thresholds": [
        {"op": ">", "value": 56, "icd10": "K76.89", "condition": "Liver disease, other specified"},
    ]},
    # Total Cholesterol
    "2093-3": {"name": "Total Cholesterol", "thresholds": [
        {"op": ">=", "value": 240, "icd10": "E78.0", "condition": "Pure hypercholesterolemia"},
    ]},
    # LDL
    "2089-1": {"name": "LDL", "thresholds": [
        {"op": ">=", "value": 190, "icd10": "E78.0", "condition": "Pure hypercholesterolemia"},
    ]},
    # Vitamin D
    "1989-3": {"name": "Vitamin D", "thresholds": [
        {"op": "<", "value": 20, "icd10": "E55.9", "condition": "Vitamin D deficiency"},
    ]},
    # TSH → Thyroid
    "3016-3": {"name": "TSH", "thresholds": [
        {"op": ">", "value": 4.5, "icd10": "E03.9", "condition": "Hypothyroidism, unspecified"},
        {"op": "<", "value": 0.4, "icd10": "E05.90", "condition": "Thyrotoxicosis, unspecified"},
    ]},
    # Hemoglobin → Anemia
    "718-7": {"name": "Hemoglobin", "thresholds": [
        {"op": "<", "value": 12.0, "icd10": "D64.9", "condition": "Anemia, unspecified"},
    ]},
    # Triglycerides
    "2571-8": {"name": "Triglycerides", "thresholds": [
        {"op": ">=", "value": 500, "icd10": "E78.1", "condition": "Pure hypertriglyceridemia"},
        {"op": ">=", "value": 150, "icd10": "E78.5", "condition": "Hyperlipidemia, unspecified"},
    ]},
    # BNP → Heart failure
    "42637-9": {"name": "BNP", "thresholds": [
        {"op": ">", "value": 400, "icd10": "I50.9", "condition": "Heart failure, unspecified"},
    ]},
}

# ══════════════════════════════════════════════════════════
# PHENOTYPE RULES (from v20 Agent 11 — PheKB/CCW)
# ══════════════════════════════════════════════════════════

PHENOTYPE_RULES = {
    "diabetes_t2": {
        "condition": "Type 2 Diabetes Mellitus",
        "icd10": "E11.9",
        "medication_markers": ["metformin", "glipizide", "glyburide", "insulin", "sitagliptin", "empagliflozin", "dulaglutide", "semaglutide"],
        "lab_markers": {"4548-4": {"op": ">=", "value": 6.5}},
        "note_patterns": [r"(?i)diabetes\s*(mellitus)?(\s*type\s*2)?", r"(?i)\bT2DM\b", r"(?i)\bDM2\b", r"(?i)uncontrolled\s+diabetes"],
    },
    "ckd": {
        "condition": "Chronic Kidney Disease",
        "icd10": "N18.9",
        "medication_markers": ["lisinopril", "losartan", "amlodipine"],
        "lab_markers": {"33914-3": {"op": "<", "value": 60}},
        "note_patterns": [r"(?i)chronic\s+kidney\s+disease", r"(?i)\bCKD\b", r"(?i)renal\s+(insufficiency|failure)"],
    },
    "copd": {
        "condition": "COPD",
        "icd10": "J44.1",
        "medication_markers": ["albuterol", "tiotropium", "fluticasone", "budesonide", "ipratropium"],
        "lab_markers": {},
        "note_patterns": [r"(?i)\bCOPD\b", r"(?i)chronic\s+obstructive", r"(?i)emphysema"],
    },
    "heart_failure": {
        "condition": "Heart Failure",
        "icd10": "I50.9",
        "medication_markers": ["furosemide", "carvedilol", "metoprolol", "lisinopril", "spironolactone", "sacubitril"],
        "lab_markers": {"42637-9": {"op": ">", "value": 400}},
        "note_patterns": [r"(?i)heart\s+failure", r"(?i)\bCHF\b", r"(?i)\bHFrEF\b", r"(?i)\bHFpEF\b"],
    },
    "hypertension": {
        "condition": "Essential Hypertension",
        "icd10": "I10",
        "medication_markers": ["lisinopril", "amlodipine", "losartan", "hydrochlorothiazide", "metoprolol", "valsartan"],
        "lab_markers": {},
        "note_patterns": [r"(?i)hypertension", r"(?i)\bHTN\b", r"(?i)high\s+blood\s+pressure", r"(?i)elevated\s+BP"],
    },
    "hyperlipidemia": {
        "condition": "Hyperlipidemia",
        "icd10": "E78.5",
        "medication_markers": ["atorvastatin", "rosuvastatin", "simvastatin", "pravastatin", "ezetimibe"],
        "lab_markers": {"2093-3": {"op": ">=", "value": 240}},
        "note_patterns": [r"(?i)hyperlipidemia", r"(?i)hypercholesterolemia", r"(?i)dyslipidemia", r"(?i)high\s+cholesterol"],
    },
    "depression": {
        "condition": "Major Depressive Disorder",
        "icd10": "F32.9",
        "medication_markers": ["sertraline", "fluoxetine", "escitalopram", "citalopram", "duloxetine", "venlafaxine", "bupropion"],
        "lab_markers": {},
        "note_patterns": [r"(?i)major\s+depress", r"(?i)\bMDD\b", r"(?i)depressive\s+disorder"],
    },
    "hypothyroid": {
        "condition": "Hypothyroidism",
        "icd10": "E03.9",
        "medication_markers": ["levothyroxine", "synthroid", "armour thyroid"],
        "lab_markers": {"3016-3": {"op": ">", "value": 4.5}},
        "note_patterns": [r"(?i)hypothyroid", r"(?i)underactive\s+thyroid"],
    },
}

# ══════════════════════════════════════════════════════════
# NEGATION PATTERNS
# ══════════════════════════════════════════════════════════

NEGATION_CUES = [
    r"(?i)\bno\s+(evidence|history|sign|diagnosis)\s+of\b",
    r"(?i)\bdenies\b", r"(?i)\bdenied\b",
    r"(?i)\brule(s)?\s+out\b", r"(?i)\br/o\b",
    r"(?i)\bnot\s+(diagnosed|found|present|seen)\b",
    r"(?i)\bwithout\s+(evidence|sign)\b",
    r"(?i)\bnegative\s+for\b",
    r"(?i)\babsence\s+of\b",
    r"(?i)\bno\s+\w+\s+(identified|detected|noted)\b",
    r"(?i)\bfamily\s+history\s+of\b",
]

SCREENING_PATTERNS = [
    r"(?i)\bscreening?\b", r"(?i)\breferred?\s+for\b",
    r"(?i)\breferral\s+to\b", r"(?i)\brule\s+out\b",
    r"(?i)\bpossible\b", r"(?i)\bsuspect(ed)?\b",
]


def is_negated(text: str, entity_pos: int, window: int = 80) -> bool:
    """Check if entity at position is negated within a window."""
    start = max(0, entity_pos - window)
    context = text[start:entity_pos + window].lower()
    for pattern in NEGATION_CUES:
        if re.search(pattern, context):
            return True
    return False


def is_screening(text: str, entity_pos: int, window: int = 60) -> bool:
    """Check if entity mention is a screening/referral context."""
    start = max(0, entity_pos - window)
    context = text[start:entity_pos + window].lower()
    for pattern in SCREENING_PATTERNS:
        if re.search(pattern, context):
            return True
    return False


# ══════════════════════════════════════════════════════════
# SECTION DETECTION (from v20 Agent 5)
# ══════════════════════════════════════════════════════════

SECTION_MARKERS = {
    "assessment_plan": [
        r"(?im)^[\s]*(?:assessment\s*(?:and|&|/)\s*plan|a\s*/\s*p|impression\s*(?:and|&|/)\s*plan|"
        r"assessment\s*:|impression\s*:|diagnosis\s*:|diagnoses\s*:|problem\s*list|active\s*problems)",
    ],
    "hpi": [r"(?im)^[\s]*(?:history\s*of\s*present|HPI|chief\s*complaint|CC:)"],
    "medications": [r"(?im)^[\s]*(?:medication|current\s*med|med\s*list|rx:)"],
    "labs": [r"(?im)^[\s]*(?:lab|laboratory|result|diagnostic)"],
    "exam": [r"(?im)^[\s]*(?:physical\s*exam|PE:|review\s*of\s*systems|ROS:)"],
}


def detect_section(text: str, pos: int) -> str:
    """Determine which clinical section a position falls in."""
    best_section = "unknown"
    best_pos = -1
    for section, patterns in SECTION_MARKERS.items():
        for pat in patterns:
            for m in re.finditer(pat, text):
                if m.start() <= pos and m.start() > best_pos:
                    best_section = section
                    best_pos = m.start()
    return best_section


# ══════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════

def run_gap_pipeline(profile: Dict, demographics: Dict) -> Dict:
    """Run the full gap detection pipeline.
    Returns: {"approved": [...], "review": [...], "rejected": [...]}
    """
    patient_id = profile.get("fhir_patient_id", "")
    log.info(f"Pipeline start for patient {patient_id}")

    coded_conditions = set()
    for c in profile.get("conditions", []):
        code = c.get("icd10_code", "")
        if code:
            coded_conditions.add(code)
            # Also add the parent code (e.g., E11 for E11.65)
            if "." in code:
                coded_conditions.add(code.split(".")[0])

    # Also count claims codes
    claims_codes = profile.get("claims_codes", set())
    if isinstance(claims_codes, list):
        claims_codes = set(claims_codes)
    all_coded = coded_conditions | claims_codes

    candidates = []

    # ── TIER 1: Structured Lab Analysis ──
    tier1_gaps = _tier1_lab_detection(profile.get("observations", []), all_coded)
    candidates.extend(tier1_gaps)
    log.info(f"TIER 1: {len(tier1_gaps)} lab-based candidates")

    # ── TIER 2: Phenotype Rule Matching ──
    tier2_gaps = _tier2_phenotype_detection(profile, all_coded)
    candidates.extend(tier2_gaps)
    log.info(f"TIER 2: {len(tier2_gaps)} phenotype-based candidates")

    # ── TIER 3: Clinical Note NER (pattern-based for CPU deployment) ──
    tier3_gaps = _tier3_note_detection(profile.get("clinical_notes", []), all_coded)
    candidates.extend(tier3_gaps)
    log.info(f"TIER 3: {len(tier3_gaps)} note-based candidates")

    # ── Deduplication ──
    deduped = _deduplicate(candidates)
    log.info(f"After dedup: {len(deduped)} unique candidates")

    # ── MEAT Validation ──
    for gap in deduped:
        gap["meat_evidence"] = _assess_meat(gap, profile)

    # ── Decision ──
    approved = []
    review = []
    rejected = []

    for gap in deduped:
        meat = gap.get("meat_evidence", {})
        meat_count = sum(1 for v in meat.values() if v)
        evidence_count = gap.get("evidence_count", 1)

        if meat_count >= 2 and evidence_count >= 2:
            gap["decision"] = "MISSING OPPORTUNITY"
            gap["confidence_score"] = min(0.95, 0.6 + (meat_count * 0.1) + (evidence_count * 0.05))
            approved.append(gap)
        elif meat_count >= 1 or evidence_count >= 2:
            gap["decision"] = "REVIEW CANDIDATE"
            gap["confidence_score"] = min(0.80, 0.4 + (meat_count * 0.1) + (evidence_count * 0.05))
            review.append(gap)
        else:
            gap["decision"] = "REJECT"
            gap["confidence_score"] = 0.2
            rejected.append(gap)

    log.info(f"Pipeline complete: {len(approved)} approved, {len(review)} review, {len(rejected)} rejected")

    return {
        "approved": approved,
        "review": review,
        "rejected": rejected,
    }


def _tier1_lab_detection(observations: List[Dict], coded: set) -> List[Dict]:
    """TIER 1: Detect gaps from abnormal lab values using LOINC thresholds."""
    gaps = []
    for obs in observations:
        loinc = obs.get("loinc", "")
        value = obs.get("value")
        if not loinc or value is None:
            continue
        try:
            value = float(value)
        except (ValueError, TypeError):
            continue

        mapping = LOINC_ICD10_MAP.get(loinc)
        if not mapping:
            continue

        for threshold in mapping["thresholds"]:
            op = threshold["op"]
            thresh_val = threshold["value"]
            match = False
            if op == ">=" and value >= thresh_val:
                match = True
            elif op == ">" and value > thresh_val:
                match = True
            elif op == "<=" and value <= thresh_val:
                match = True
            elif op == "<" and value < thresh_val:
                match = True

            if match:
                icd10 = threshold["icd10"]
                # Check if already coded (including parent code)
                parent = icd10.split(".")[0] if "." in icd10 else icd10
                if icd10 not in coded and parent not in coded:
                    gaps.append({
                        "tier": "TIER_1_STRUCTURED",
                        "icd10_code": icd10,
                        "condition_name": threshold["condition"],
                        "evidence_sources": [f"Lab: {mapping['name']} = {value} {obs.get('unit', '')} ({op} {thresh_val})"],
                        "evidence_count": 1,
                        "lab_name": mapping["name"],
                        "lab_value": value,
                        "lab_loinc": loinc,
                        "lab_date": obs.get("date", ""),
                    })
                break  # Only match the first (most severe) threshold
    return gaps


def _tier2_phenotype_detection(profile: Dict, coded: set) -> List[Dict]:
    """TIER 2: Detect gaps using PheKB-style phenotype rules (meds + labs + notes)."""
    gaps = []
    med_names = [m.get("name", "").lower() for m in profile.get("medications", []) if m.get("status") in ("active", "")]
    all_notes = " ".join(n.get("text", "") for n in profile.get("clinical_notes", []))
    observations = {o.get("loinc", ""): o for o in profile.get("observations", [])}

    for rule_id, rule in PHENOTYPE_RULES.items():
        icd10 = rule["icd10"]
        parent = icd10.split(".")[0] if "." in icd10 else icd10

        # Skip if already coded
        already_coded = False
        for c in coded:
            if c.startswith(parent) or c == icd10:
                already_coded = True
                break
        if already_coded:
            continue

        evidence = []

        # Check medications
        for med_marker in rule["medication_markers"]:
            for med_name in med_names:
                if med_marker.lower() in med_name:
                    evidence.append(f"Medication: {med_name} (marker for {rule['condition']})")
                    break

        # Check labs
        for loinc_code, threshold in rule.get("lab_markers", {}).items():
            obs = observations.get(loinc_code)
            if obs and obs.get("value") is not None:
                try:
                    val = float(obs["value"])
                    op = threshold["op"]
                    thresh = threshold["value"]
                    if (op == ">=" and val >= thresh) or (op == ">" and val > thresh) or \
                       (op == "<=" and val <= thresh) or (op == "<" and val < thresh):
                        evidence.append(f"Lab: {obs.get('name', loinc_code)} = {val} ({op} {thresh})")
                except (ValueError, TypeError):
                    pass

        # Check note patterns
        for pattern in rule.get("note_patterns", []):
            match = re.search(pattern, all_notes)
            if match:
                pos = match.start()
                # Check negation
                if not is_negated(all_notes, pos) and not is_screening(all_notes, pos):
                    section = detect_section(all_notes, pos)
                    if section in ("assessment_plan", "unknown"):
                        # Extract evidence window
                        start = max(0, pos - 100)
                        end = min(len(all_notes), pos + 200)
                        snippet = all_notes[start:end].strip()
                        evidence.append(f"Clinical note [{section}]: ...{snippet}...")
                        break

        if len(evidence) >= 2:
            gaps.append({
                "tier": "TIER_2_PHENOTYPE",
                "icd10_code": icd10,
                "condition_name": rule["condition"],
                "evidence_sources": evidence,
                "evidence_count": len(evidence),
                "phenotype_rule": rule_id,
            })

    return gaps


def _tier3_note_detection(notes: List[Dict], coded: set) -> List[Dict]:
    """TIER 3: Pattern-based NER on clinical notes (CPU-friendly)."""
    gaps = []
    seen_codes = set()

    # Additional patterns not covered by phenotype rules
    extra_patterns = {
        "E66.01": {"name": "Morbid obesity", "patterns": [r"(?i)morbid\s+obes", r"(?i)\bBMI\s*(>|over)\s*40\b"]},
        "G47.33": {"name": "Obstructive sleep apnea", "patterns": [r"(?i)obstructive\s+sleep\s+apnea", r"(?i)\bOSA\b"]},
        "M81.0": {"name": "Osteoporosis", "patterns": [r"(?i)osteoporosis"]},
        "G43.909": {"name": "Migraine", "patterns": [r"(?i)\bmigraine\b"]},
        "K21.0": {"name": "GERD with esophagitis", "patterns": [r"(?i)\bGERD\b", r"(?i)gastroesophageal\s+reflux"]},
        "F41.1": {"name": "Generalized anxiety disorder", "patterns": [r"(?i)generalized\s+anxiety", r"(?i)\bGAD\b"]},
        "J45.20": {"name": "Mild intermittent asthma", "patterns": [r"(?i)\basthma\b"]},
    }

    all_text = " ".join(n.get("text", "") for n in notes)

    for icd10, info in extra_patterns.items():
        parent = icd10.split(".")[0]
        if icd10 in coded or parent in coded or icd10 in seen_codes:
            continue

        for pattern in info["patterns"]:
            match = re.search(pattern, all_text)
            if match:
                pos = match.start()
                if not is_negated(all_text, pos) and not is_screening(all_text, pos):
                    section = detect_section(all_text, pos)
                    if section in ("assessment_plan", "unknown"):
                        start = max(0, pos - 80)
                        end = min(len(all_text), pos + 150)
                        snippet = all_text[start:end].strip()
                        gaps.append({
                            "tier": "TIER_3_NOTE_NER",
                            "icd10_code": icd10,
                            "condition_name": info["name"],
                            "evidence_sources": [f"Clinical note [{section}]: ...{snippet}..."],
                            "evidence_count": 1,
                            "section": section,
                        })
                        seen_codes.add(icd10)
                        break
    return gaps


def _deduplicate(candidates: List[Dict]) -> List[Dict]:
    """Deduplicate by ICD-10 code, keeping the highest evidence count."""
    by_code = {}
    for gap in candidates:
        code = gap.get("icd10_code", "")
        if code not in by_code or gap.get("evidence_count", 0) > by_code[code].get("evidence_count", 0):
            by_code[code] = gap
    return list(by_code.values())


def _assess_meat(gap: Dict, profile: Dict) -> Dict:
    """Assess MEAT criteria for a gap."""
    condition = gap.get("condition_name", "").lower()
    icd10 = gap.get("icd10_code", "")

    meat = {
        "monitoring": False,
        "evaluation": False,
        "assessment": False,
        "treatment": False,
    }

    # M — Monitoring: relevant labs ordered
    for obs in profile.get("observations", []):
        obs_name = obs.get("name", "").lower()
        if any(kw in obs_name for kw in condition.split()[:2]):
            meat["monitoring"] = True
            break
    # Also check if lab-based gap
    if gap.get("tier") == "TIER_1_STRUCTURED":
        meat["monitoring"] = True

    # E — Evaluation: encounter exists
    if profile.get("encounters"):
        meat["evaluation"] = True

    # A — Assessment: condition mentioned in notes
    all_notes = " ".join(n.get("text", "") for n in profile.get("clinical_notes", []))
    if condition.split()[0].lower() in all_notes.lower():
        meat["assessment"] = True

    # T — Treatment: relevant medication prescribed
    for med in profile.get("medications", []):
        med_name = med.get("name", "").lower()
        # Check phenotype rules for medication markers
        for rule in PHENOTYPE_RULES.values():
            if rule["icd10"].startswith(icd10[:3]):
                for marker in rule.get("medication_markers", []):
                    if marker in med_name:
                        meat["treatment"] = True
                        break

    return meat
