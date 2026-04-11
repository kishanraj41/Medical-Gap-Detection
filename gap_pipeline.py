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
    # ── Diabetes ──
    "4548-4": {"name": "HbA1c", "thresholds": [
        {"op": ">=", "value": 6.5, "icd10": "E11.65", "condition": "Type 2 diabetes with hyperglycemia"},
        {"op": ">=", "value": 5.7, "icd10": "R73.03", "condition": "Prediabetes"},
    ]},
    "17856-6": {"name": "HbA1c (alternate LOINC)", "thresholds": [
        {"op": ">=", "value": 6.5, "icd10": "E11.65", "condition": "Type 2 diabetes with hyperglycemia"},
    ]},
    "1558-6": {"name": "Fasting Glucose", "thresholds": [
        {"op": ">=", "value": 126, "icd10": "E11.65", "condition": "Type 2 diabetes with hyperglycemia"},
        {"op": ">=", "value": 100, "icd10": "R73.09", "condition": "Impaired fasting glucose"},
    ]},
    "2345-7": {"name": "Glucose (random)", "thresholds": [
        {"op": ">=", "value": 200, "icd10": "E11.65", "condition": "Type 2 diabetes with hyperglycemia"},
    ]},
    # ── Kidney ──
    "33914-3": {"name": "eGFR", "thresholds": [
        {"op": "<", "value": 15, "icd10": "N18.5", "condition": "CKD Stage 5"},
        {"op": "<", "value": 30, "icd10": "N18.4", "condition": "CKD Stage 4"},
        {"op": "<", "value": 45, "icd10": "N18.3", "condition": "CKD Stage 3b"},
        {"op": "<", "value": 60, "icd10": "N18.3", "condition": "CKD Stage 3"},
    ]},
    "48642-3": {"name": "eGFR (non-Black)", "thresholds": [
        {"op": "<", "value": 60, "icd10": "N18.3", "condition": "CKD Stage 3"},
    ]},
    "62238-1": {"name": "eGFR (CKD-EPI)", "thresholds": [
        {"op": "<", "value": 60, "icd10": "N18.3", "condition": "CKD Stage 3"},
    ]},
    "2160-0": {"name": "Creatinine", "thresholds": [
        {"op": ">=", "value": 1.5, "icd10": "N18.9", "condition": "CKD, unspecified"},
    ]},
    "14959-1": {"name": "Microalbumin/Creatinine Ratio", "thresholds": [
        {"op": ">=", "value": 300, "icd10": "N18.3", "condition": "CKD Stage 3 (albuminuria A3)"},
        {"op": ">=", "value": 30, "icd10": "N18.9", "condition": "CKD (albuminuria A2)"},
    ]},
    # ── Liver ──
    "1742-6": {"name": "ALT", "thresholds": [
        {"op": ">", "value": 56, "icd10": "K76.89", "condition": "Liver disease, other specified"},
    ]},
    "1920-8": {"name": "AST", "thresholds": [
        {"op": ">", "value": 40, "icd10": "K76.89", "condition": "Liver disease, other specified"},
    ]},
    "1975-2": {"name": "Bilirubin (total)", "thresholds": [
        {"op": ">=", "value": 3.0, "icd10": "K76.89", "condition": "Liver disease"},
    ]},
    # ── Lipids ──
    "2093-3": {"name": "Total Cholesterol", "thresholds": [
        {"op": ">=", "value": 240, "icd10": "E78.0", "condition": "Pure hypercholesterolemia"},
    ]},
    "2089-1": {"name": "LDL", "thresholds": [
        {"op": ">=", "value": 190, "icd10": "E78.0", "condition": "Pure hypercholesterolemia"},
        {"op": ">=", "value": 160, "icd10": "E78.5", "condition": "Hyperlipidemia, unspecified"},
    ]},
    "2571-8": {"name": "Triglycerides", "thresholds": [
        {"op": ">=", "value": 500, "icd10": "E78.1", "condition": "Pure hypertriglyceridemia"},
        {"op": ">=", "value": 150, "icd10": "E78.5", "condition": "Hyperlipidemia, unspecified"},
    ]},
    # ── Vitamins / Minerals ──
    "1989-3": {"name": "Vitamin D", "thresholds": [
        {"op": "<", "value": 20, "icd10": "E55.9", "condition": "Vitamin D deficiency"},
    ]},
    "2132-9": {"name": "Vitamin B12", "thresholds": [
        {"op": "<", "value": 200, "icd10": "E53.8", "condition": "Vitamin B12 deficiency"},
    ]},
    "2284-8": {"name": "Folate", "thresholds": [
        {"op": "<", "value": 3.0, "icd10": "E53.8", "condition": "Folate deficiency"},
    ]},
    "2498-4": {"name": "Ferritin", "thresholds": [
        {"op": "<", "value": 12, "icd10": "D50.9", "condition": "Iron deficiency anemia"},
    ]},
    # ── Thyroid ──
    "3016-3": {"name": "TSH", "thresholds": [
        {"op": ">", "value": 10.0, "icd10": "E03.9", "condition": "Hypothyroidism, unspecified"},
        {"op": ">", "value": 4.5, "icd10": "E03.9", "condition": "Hypothyroidism, unspecified"},
        {"op": "<", "value": 0.4, "icd10": "E05.90", "condition": "Thyrotoxicosis, unspecified"},
    ]},
    "3024-7": {"name": "Free T4", "thresholds": [
        {"op": "<", "value": 0.7, "icd10": "E03.9", "condition": "Hypothyroidism"},
        {"op": ">", "value": 1.8, "icd10": "E05.90", "condition": "Thyrotoxicosis"},
    ]},
    # ── Hematology ──
    "718-7": {"name": "Hemoglobin", "thresholds": [
        {"op": "<", "value": 12.0, "icd10": "D64.9", "condition": "Anemia, unspecified"},
    ]},
    "4544-3": {"name": "Hematocrit", "thresholds": [
        {"op": "<", "value": 36.0, "icd10": "D64.9", "condition": "Anemia, unspecified"},
    ]},
    # ── Cardiac ──
    "42637-9": {"name": "BNP", "thresholds": [
        {"op": ">", "value": 400, "icd10": "I50.9", "condition": "Heart failure, unspecified"},
        {"op": ">", "value": 100, "icd10": "I50.9", "condition": "Heart failure (possible)"},
    ]},
    "33762-6": {"name": "NT-proBNP", "thresholds": [
        {"op": ">", "value": 900, "icd10": "I50.9", "condition": "Heart failure, unspecified"},
        {"op": ">", "value": 300, "icd10": "I50.9", "condition": "Heart failure (possible)"},
    ]},
    # ── Metabolic ──
    "3084-1": {"name": "Uric Acid", "thresholds": [
        {"op": ">", "value": 7.0, "icd10": "E79.0", "condition": "Hyperuricemia"},
    ]},
    "2339-0": {"name": "Glucose (urine)", "thresholds": [
        {"op": ">", "value": 0, "icd10": "R81", "condition": "Glycosuria"},
    ]},
    "5811-5": {"name": "Protein (urine)", "thresholds": [
        {"op": ">", "value": 30, "icd10": "R80.9", "condition": "Proteinuria"},
    ]},
}

# ══════════════════════════════════════════════════════════
# PHENOTYPE RULES (from v20 Agent 11 — PheKB/CCW)
# ══════════════════════════════════════════════════════════

PHENOTYPE_RULES = {
    # ── Source: ADA 2024 + PheKB Algorithm 41 ──
    "diabetes_t2": {
        "condition": "Type 2 Diabetes Mellitus",
        "icd10": "E11.9",
        "medication_markers": [
            "metformin", "insulin", "glipizide", "glyburide", "glimepiride", "sitagliptin",
            "empagliflozin", "dapagliflozin", "canagliflozin", "liraglutide", "semaglutide",
            "dulaglutide", "pioglitazone", "saxagliptin", "linagliptin", "jardiance", "farxiga",
            "invokana", "januvia", "actos", "amaryl", "glucophage", "ozempic", "trulicity",
        ],
        "lab_markers": {"4548-4": {"op": ">=", "value": 6.5}},
        "note_patterns": [
            r"(?i)diabetes\s*(mellitus)?(\s*type\s*(2|ii))?", r"(?i)\bT2DM\b", r"(?i)\bDM2?\b",
            r"(?i)uncontrolled\s+diabetes", r"(?i)\bNIDDM\b", r"(?i)\ba1c\b", r"(?i)\bhba1c\b",
        ],
    },
    # ── Source: KDIGO 2024 + PheKB Algorithm 27 ──
    "ckd": {
        "condition": "Chronic Kidney Disease",
        "icd10": "N18.9",
        "medication_markers": [
            "lisinopril", "losartan", "valsartan", "enalapril", "ramipril", "irbesartan",
            "benazepril", "candesartan", "telmisartan", "olmesartan", "amlodipine",
        ],
        "lab_markers": {"33914-3": {"op": "<", "value": 60}},
        "note_patterns": [
            r"(?i)chronic\s+kidney\s+disease", r"(?i)\bCKD\b", r"(?i)renal\s+(insufficiency|failure|disease)",
            r"(?i)nephropathy", r"(?i)dialysis", r"(?i)egfr\s*(declined|low|reduced)",
        ],
    },
    # ── Source: AHA/ACC 2023 + OMOP Phenotype 218 ──
    "heart_failure": {
        "condition": "Heart Failure",
        "icd10": "I50.9",
        "medication_markers": [
            "furosemide", "bumetanide", "torsemide", "spironolactone", "eplerenone",
            "carvedilol", "metoprolol", "bisoprolol", "sacubitril", "entresto",
            "digoxin", "hydralazine", "isosorbide", "lasix",
        ],
        "lab_markers": {"42637-9": {"op": ">", "value": 100}},
        "note_patterns": [
            r"(?i)heart\s+failure", r"(?i)\bCHF\b", r"(?i)\bHF\b", r"(?i)congestive",
            r"(?i)ejection\s+fraction", r"(?i)\bHFrEF\b", r"(?i)\bHFpEF\b",
            r"(?i)systolic\s+dysfunction", r"(?i)cardiomyopathy", r"(?i)\bBNP\b",
        ],
    },
    # ── Source: GOLD 2024 + PheKB Algorithm 7 ──
    "copd": {
        "condition": "COPD",
        "icd10": "J44.1",
        "medication_markers": [
            "albuterol", "ipratropium", "tiotropium", "fluticasone", "budesonide",
            "formoterol", "salmeterol", "umeclidinium", "vilanterol", "roflumilast",
            "spiriva", "advair", "symbicort", "breo", "trelegy", "proair", "ventolin",
        ],
        "lab_markers": {},
        "note_patterns": [
            r"(?i)\bCOPD\b", r"(?i)chronic\s+obstructive", r"(?i)emphysema",
            r"(?i)chronic\s+bronchitis", r"(?i)bronchodilator", r"(?i)oxygen\s+therapy",
        ],
    },
    # ── Source: ATA 2024 ──
    "hypothyroid": {
        "condition": "Hypothyroidism",
        "icd10": "E03.9",
        "medication_markers": [
            "levothyroxine", "synthroid", "armour thyroid", "liothyronine",
            "tirosint", "levoxyl", "cytomel", "euthyrox", "unithroid",
        ],
        "lab_markers": {"3016-3": {"op": ">", "value": 4.5}},
        "note_patterns": [
            r"(?i)hypothyroid", r"(?i)underactive\s+thyroid", r"(?i)hashimoto",
            r"(?i)tsh\s*(elevated|high)", r"(?i)myxedema",
        ],
    },
    # ── Source: ATP-III/AHA 2024 ──
    "hyperlipidemia": {
        "condition": "Hyperlipidemia",
        "icd10": "E78.5",
        "medication_markers": [
            "atorvastatin", "rosuvastatin", "simvastatin", "pravastatin", "lovastatin",
            "pitavastatin", "ezetimibe", "fenofibrate", "gemfibrozil", "alirocumab",
            "evolocumab", "lipitor", "crestor", "zocor", "zetia", "repatha", "praluent",
        ],
        "lab_markers": {"2093-3": {"op": ">=", "value": 240}},
        "note_patterns": [
            r"(?i)hyperlipidemia", r"(?i)hypercholesterolemia", r"(?i)dyslipidemia",
            r"(?i)high\s+cholesterol", r"(?i)elevated\s+ldl", r"(?i)\bHLD\b",
        ],
    },
    # ── Source: AHA/ACC 2024 ──
    "hypertension": {
        "condition": "Essential Hypertension",
        "icd10": "I10",
        "medication_markers": [
            "lisinopril", "amlodipine", "losartan", "metoprolol", "hydrochlorothiazide",
            "atenolol", "valsartan", "carvedilol", "diltiazem", "nifedipine",
            "benazepril", "enalapril", "ramipril", "irbesartan", "clonidine",
            "hctz", "norvasc", "diovan", "cozaar", "toprol",
        ],
        "lab_markers": {},
        "note_patterns": [
            r"(?i)hypertension", r"(?i)\bHTN\b", r"(?i)high\s+blood\s+pressure",
            r"(?i)bp\s*(elevated|high)", r"(?i)hypertensive",
        ],
    },
    # ── Source: WHO + OMOP Phenotype 37 ──
    "anemia": {
        "condition": "Anemia",
        "icd10": "D64.9",
        "medication_markers": [
            "ferrous sulfate", "iron", "epoetin", "darbepoetin", "folic acid",
            "cyanocobalamin", "b12", "vitamin b12",
        ],
        "lab_markers": {"718-7": {"op": "<", "value": 12.0}},
        "note_patterns": [
            r"(?i)\banemia\b", r"(?i)anemic", r"(?i)low\s+hemoglobin",
            r"(?i)iron\s+deficiency", r"(?i)b12\s+deficiency",
        ],
    },
    # ── Source: APA 2024 + PheKB Algorithm 15 ──
    "depression": {
        "condition": "Major Depressive Disorder",
        "icd10": "F32.9",
        "medication_markers": [
            "sertraline", "fluoxetine", "escitalopram", "citalopram", "paroxetine",
            "venlafaxine", "duloxetine", "bupropion", "mirtazapine", "trazodone",
            "amitriptyline", "nortriptyline", "lexapro", "zoloft", "prozac",
            "cymbalta", "effexor", "wellbutrin",
        ],
        "lab_markers": {},
        "note_patterns": [
            r"(?i)major\s+depress", r"(?i)\bMDD\b", r"(?i)depressive\s+disorder",
            r"(?i)\bdepressed\b", r"(?i)phq-?9",
        ],
    },
    # ── Source: CMS + OMOP ──
    "obesity": {
        "condition": "Obesity",
        "icd10": "E66.9",
        "medication_markers": [
            "orlistat", "phentermine", "liraglutide", "semaglutide", "naltrexone",
            "contrave", "qsymia", "saxenda", "wegovy",
        ],
        "lab_markers": {},
        "note_patterns": [
            r"(?i)\bobesity\b", r"(?i)\bobese\b", r"(?i)morbid\s+obes",
            r"(?i)bmi\s*(>|over|of)\s*(30|35|40)", r"(?i)bariatric",
        ],
    },
    # ── Source: ACG 2024 ──
    "gerd": {
        "condition": "GERD",
        "icd10": "K21.0",
        "medication_markers": [
            "omeprazole", "pantoprazole", "esomeprazole", "lansoprazole",
            "rabeprazole", "famotidine", "prilosec", "nexium", "protonix", "dexilant",
        ],
        "lab_markers": {},
        "note_patterns": [
            r"(?i)\bGERD\b", r"(?i)gastroesophageal\s+reflux", r"(?i)acid\s+reflux",
            r"(?i)heartburn", r"(?i)esophagitis",
        ],
    },
    # ── Source: AASLD 2024 ──
    "liver_disease": {
        "condition": "Liver Disease",
        "icd10": "K76.89",
        "medication_markers": [
            "ursodiol", "lactulose", "rifaximin", "spironolactone", "nadolol", "propranolol",
        ],
        "lab_markers": {"1742-6": {"op": ">=", "value": 100}},
        "note_patterns": [
            r"(?i)cirrhosis", r"(?i)hepatitis", r"(?i)fatty\s+liver",
            r"(?i)\bNAFLD\b", r"(?i)\bNASH\b", r"(?i)liver\s+disease",
            r"(?i)hepatomegaly", r"(?i)ascites",
        ],
    },
}

# ══════════════════════════════════════════════════════════
# HCC MAPPING + RAF SCORE (CMS V28 Model)
# Source: CMS.gov 2025 risk adjustment model
# ══════════════════════════════════════════════════════════

CMS_BASE_RATE = 11_000  # Approximate CMS per-member base rate for 2026

HCC_ICD10_MAP = {
    # Diabetes
    "E11": {"hcc": "HCC 37", "desc": "Diabetes without Complication", "raf": 0.166},
    "E11.2": {"hcc": "HCC 18", "desc": "Diabetes with Chronic Complications", "raf": 0.302},
    "E11.4": {"hcc": "HCC 18", "desc": "Diabetes with Neurological Complications", "raf": 0.302},
    "E11.6": {"hcc": "HCC 18", "desc": "Diabetes with Other Complications", "raf": 0.302},
    "E11.65": {"hcc": "HCC 37", "desc": "DM2 with Hyperglycemia", "raf": 0.166},
    # CKD
    "N18.3": {"hcc": "HCC 138", "desc": "CKD Stage 3", "raf": 0.069},
    "N18.4": {"hcc": "HCC 137", "desc": "CKD Stage 4", "raf": 0.289},
    "N18.5": {"hcc": "HCC 136", "desc": "CKD Stage 5", "raf": 0.289},
    "N18.9": {"hcc": "HCC 138", "desc": "CKD Unspecified", "raf": 0.069},
    # Heart Failure
    "I50.2": {"hcc": "HCC 85", "desc": "Systolic Heart Failure", "raf": 0.323},
    "I50.3": {"hcc": "HCC 85", "desc": "Diastolic Heart Failure", "raf": 0.323},
    "I50.9": {"hcc": "HCC 85", "desc": "Heart Failure Unspecified", "raf": 0.323},
    # COPD
    "J44.0": {"hcc": "HCC 111", "desc": "COPD with Acute Exacerbation", "raf": 0.335},
    "J44.1": {"hcc": "HCC 111", "desc": "COPD with Chronic Bronchitis", "raf": 0.335},
    # Hypertension (not HCC in V28 — but still revenue relevant)
    "I10": {"hcc": "Non-HCC", "desc": "Essential Hypertension", "raf": 0.0},
    # Hyperlipidemia (not HCC)
    "E78.0": {"hcc": "Non-HCC", "desc": "Pure Hypercholesterolemia", "raf": 0.0},
    "E78.5": {"hcc": "Non-HCC", "desc": "Hyperlipidemia", "raf": 0.0},
    # Depression
    "F32.9": {"hcc": "HCC 155", "desc": "Major Depression", "raf": 0.309},
    "F33.0": {"hcc": "HCC 155", "desc": "Recurrent Depression", "raf": 0.309},
    # Hypothyroid (not HCC)
    "E03.9": {"hcc": "Non-HCC", "desc": "Hypothyroidism", "raf": 0.0},
    # Anemia
    "D64.9": {"hcc": "Non-HCC", "desc": "Anemia Unspecified", "raf": 0.0},
    "D50.9": {"hcc": "HCC 48", "desc": "Iron Deficiency Anemia", "raf": 0.0},
    # Obesity
    "E66.01": {"hcc": "Non-HCC", "desc": "Morbid Obesity", "raf": 0.0},
    "E66.9": {"hcc": "Non-HCC", "desc": "Obesity", "raf": 0.0},
    # GERD (not HCC)
    "K21.0": {"hcc": "Non-HCC", "desc": "GERD with Esophagitis", "raf": 0.0},
    # Liver
    "K76.89": {"hcc": "Non-HCC", "desc": "Other Liver Disease", "raf": 0.0},
    "K70.3": {"hcc": "HCC 28", "desc": "Alcoholic Cirrhosis", "raf": 0.390},
    # Sleep Apnea
    "G47.33": {"hcc": "Non-HCC", "desc": "Obstructive Sleep Apnea", "raf": 0.0},
    # Anxiety
    "F41.1": {"hcc": "Non-HCC", "desc": "Generalized Anxiety", "raf": 0.0},
    # Asthma
    "J45.20": {"hcc": "HCC 111", "desc": "Mild Asthma", "raf": 0.335},
}


def lookup_hcc(icd10: str) -> dict:
    """Lookup HCC category and RAF value for an ICD-10 code.
    Tries exact match, then progressive prefix (E11.65 → E11.6 → E11)."""
    if not icd10:
        return {"hcc": "Unknown", "desc": "", "raf": 0.0, "revenue_impact": 0.0}

    code = icd10.strip().upper()

    # Exact match
    if code in HCC_ICD10_MAP:
        entry = HCC_ICD10_MAP[code]
        return {**entry, "revenue_impact": round(entry["raf"] * CMS_BASE_RATE, 2)}

    # Progressive prefix: E11.65 → E11.6 → E11
    for length in range(len(code) - 1, 2, -1):
        prefix = code[:length]
        if prefix in HCC_ICD10_MAP:
            entry = HCC_ICD10_MAP[prefix]
            return {**entry, "revenue_impact": round(entry["raf"] * CMS_BASE_RATE, 2)}

    return {"hcc": "Non-HCC", "desc": "", "raf": 0.0, "revenue_impact": 0.0}




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
    r"(?i)\bscreening?\s+(for|of)\b", r"(?i)\breferred?\s+for\b",
    r"(?i)\breferral\s+to\b", r"(?i)\brule\s+out\b",
    r"(?i)\bpossible\b", r"(?i)\bsuspect(ed)?\b",
    r"(?i)\bscreen(ed|ing)?\b",
    r"(?i)phq-?9\s*(administered|score|completed)",
    r"(?i)\bno\s+treatment\s+indicated\b",
    r"(?i)\bnot\s+meeting\s+criteria\b",
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

    # ── TIER 4: Specificity Upgrades (coded but too vague) ──
    tier4_upgrades = _detect_specificity_upgrades(profile, all_coded, profile.get("observations", []))
    candidates.extend(tier4_upgrades)
    log.info(f"TIER 4: {len(tier4_upgrades)} specificity upgrades")

    # ── Deduplication ──
    deduped = _deduplicate(candidates)
    log.info(f"After dedup: {len(deduped)} unique candidates")

    # ── HCC + RAF Scoring ──
    total_revenue_impact = 0.0
    for gap in deduped:
        hcc_info = lookup_hcc(gap.get("icd10_code", ""))
        gap["hcc_category"] = hcc_info["hcc"]
        gap["hcc_description"] = hcc_info["desc"]
        gap["raf_value"] = hcc_info["raf"]
        gap["annual_revenue_impact"] = hcc_info["revenue_impact"]
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

    # Sort approved by revenue impact (highest first)
    approved.sort(key=lambda g: g.get("annual_revenue_impact", 0), reverse=True)

    total_revenue = sum(g.get("annual_revenue_impact", 0) for g in approved)
    total_revenue_review = sum(g.get("annual_revenue_impact", 0) for g in review)

    log.info(f"Pipeline complete: {len(approved)} approved (${total_revenue:,.0f}/yr), "
             f"{len(review)} review (${total_revenue_review:,.0f}/yr), {len(rejected)} rejected")

    return {
        "approved": approved,
        "review": review,
        "rejected": rejected,
        "revenue_summary": {
            "approved_annual_impact": round(total_revenue, 2),
            "review_annual_impact": round(total_revenue_review, 2),
            "total_potential_impact": round(total_revenue + total_revenue_review, 2),
        },
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

        # Check medications (deduplicate — same med can't match multiple markers)
        matched_meds = set()
        for med_marker in rule["medication_markers"]:
            for med_name in med_names:
                if med_marker.lower() in med_name and med_name not in matched_meds:
                    matched_meds.add(med_name)
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

        # Check note patterns (with negation AND screening filtering)
        note_evidence_found = False
        for pattern in rule.get("note_patterns", []):
            match = re.search(pattern, all_notes)
            if match:
                pos = match.start()
                # Check negation AND screening
                if not is_negated(all_notes, pos) and not is_screening(all_notes, pos):
                    section = detect_section(all_notes, pos)
                    if section in ("assessment_plan", "unknown"):
                        # Extract evidence window
                        start = max(0, pos - 100)
                        end = min(len(all_notes), pos + 200)
                        snippet = all_notes[start:end].strip()
                        evidence.append(f"Clinical note [{section}]: ...{snippet}...")
                        note_evidence_found = True
                        break

        # If note evidence was blocked by screening/negation, downgrade medication-only to weak
        if len(evidence) >= 2:
            gaps.append({
                "tier": "TIER_2_PHENOTYPE",
                "icd10_code": icd10,
                "condition_name": rule["condition"],
                "evidence_sources": evidence,
                "evidence_count": len(evidence),
                "phenotype_rule": rule_id,
            })
        elif len(evidence) == 1 and any("Medication" in e for e in evidence):
            # Single medication evidence — only if note wasn't blocked by screening
            # If note WAS blocked by screening, this is likely just maintenance therapy
            if not note_evidence_found:
                # Check if any note mention exists at all (even in screening context)
                any_mention = False
                for pattern in rule.get("note_patterns", []):
                    if re.search(pattern, all_notes):
                        any_mention = True
                        break
                # If the condition is mentioned in a screening context, DON'T flag as gap
                if any_mention:
                    # Mentioned but in screening context — skip entirely
                    continue

            gaps.append({
                "tier": "TIER_2_PHENOTYPE_WEAK",
                "icd10_code": icd10,
                "condition_name": rule["condition"],
                "evidence_sources": evidence,
                "evidence_count": 1,
                "phenotype_rule": rule_id,
                "note": "Medication-only evidence — needs clinical review",
            })

    return gaps


def _tier3_note_detection(notes: List[Dict], coded: set) -> List[Dict]:
    """TIER 3: Pattern-based NER on clinical notes (CPU-friendly)."""
    gaps = []
    seen_codes = set()

    # Additional patterns not covered by phenotype rules
    extra_patterns = {
        # Musculoskeletal
        "E66.01": {"name": "Morbid obesity", "patterns": [r"(?i)morbid\s+obes", r"(?i)\bBMI\s*(>|over|of)\s*40\b"]},
        "E66.09": {"name": "Obesity, other", "patterns": [r"(?i)\bBMI\s*(>|over|of)\s*(30|35)\b"]},
        "M81.0": {"name": "Osteoporosis", "patterns": [r"(?i)osteoporosis", r"(?i)bone\s+density\s+loss"]},
        "M17.11": {"name": "Osteoarthritis, right knee", "patterns": [r"(?i)osteoarthritis.{0,20}knee"]},
        "M54.5": {"name": "Low back pain", "patterns": [r"(?i)low\s+back\s+pain", r"(?i)lumbar\s+(pain|stenosis)"]},
        # Neurological
        "G47.33": {"name": "Obstructive sleep apnea", "patterns": [r"(?i)obstructive\s+sleep\s+apnea", r"(?i)\bOSA\b", r"(?i)\bCPAP\b"]},
        "G43.909": {"name": "Migraine", "patterns": [r"(?i)\bmigraine\b"]},
        "G20": {"name": "Parkinson's disease", "patterns": [r"(?i)parkinson"]},
        "G30.9": {"name": "Alzheimer's disease", "patterns": [r"(?i)alzheimer"]},
        "G40.909": {"name": "Epilepsy", "patterns": [r"(?i)\bepilepsy\b", r"(?i)seizure\s+disorder"]},
        "G62.9": {"name": "Peripheral neuropathy", "patterns": [r"(?i)peripheral\s+neuropathy", r"(?i)neuropathic\s+pain"]},
        # GI
        "K21.0": {"name": "GERD with esophagitis", "patterns": [r"(?i)\bGERD\b", r"(?i)gastroesophageal\s+reflux"]},
        "K58.9": {"name": "IBS", "patterns": [r"(?i)\bIBS\b", r"(?i)irritable\s+bowel"]},
        # Psychiatric
        "F41.1": {"name": "Generalized anxiety disorder", "patterns": [r"(?i)generalized\s+anxiety", r"(?i)\bGAD\b"]},
        "F43.10": {"name": "PTSD", "patterns": [r"(?i)\bPTSD\b", r"(?i)post.?traumatic\s+stress"]},
        "F31.9": {"name": "Bipolar disorder", "patterns": [r"(?i)bipolar"]},
        "F20.9": {"name": "Schizophrenia", "patterns": [r"(?i)schizophrenia"]},
        # Respiratory
        "J45.20": {"name": "Mild intermittent asthma", "patterns": [r"(?i)\basthma\b"]},
        # Cardiovascular
        "I48.91": {"name": "Atrial fibrillation", "patterns": [r"(?i)atrial\s+fibrillation", r"(?i)\bafib\b", r"(?i)\ba-?fib\b"]},
        "I25.10": {"name": "Coronary artery disease", "patterns": [r"(?i)coronary\s+artery\s+disease", r"(?i)\bCAD\b"]},
        "I63.9": {"name": "Cerebral infarction", "patterns": [r"(?i)\bCVA\b", r"(?i)\bstroke\b", r"(?i)cerebral\s+infarct"]},
        # Autoimmune
        "M05.79": {"name": "Rheumatoid arthritis", "patterns": [r"(?i)rheumatoid\s+arthritis", r"(?i)\bRA\b"]},
        "M32.9": {"name": "SLE (Lupus)", "patterns": [r"(?i)\blupus\b", r"(?i)\bSLE\b"]},
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
    """Smart deduplication: merge evidence across tiers for the same condition.
    TIER 1 finds diabetes from lab + TIER 2 finds it from notes → combined gap with 3+ evidence."""
    by_code = {}
    for gap in candidates:
        code = gap.get("icd10_code", "")
        if code in by_code:
            existing = by_code[code]
            # Merge evidence sources
            for ev in gap.get("evidence_sources", []):
                if ev not in existing["evidence_sources"]:
                    existing["evidence_sources"].append(ev)
            existing["evidence_count"] = len(existing["evidence_sources"])
            # Keep the more specific tier designation
            if gap.get("tier", "").startswith("TIER_1"):
                existing["tier"] = gap["tier"]  # Lab evidence is strongest
            # Merge lab data if available
            if gap.get("lab_value") and not existing.get("lab_value"):
                existing["lab_value"] = gap["lab_value"]
                existing["lab_name"] = gap.get("lab_name", "")
                existing["lab_loinc"] = gap.get("lab_loinc", "")
                existing["lab_date"] = gap.get("lab_date", "")
        else:
            by_code[code] = gap.copy()

    # Also check for parent/child code conflicts (don't flag both E11.9 and E11.65)
    codes = list(by_code.keys())
    to_remove = set()
    for code in codes:
        parent = code.split(".")[0] if "." in code else code
        # If we have a specific code, remove the unspecified parent
        for other_code in codes:
            if other_code != code and other_code.startswith(parent) and len(other_code) < len(code):
                # Other code is less specific — merge its evidence into ours and remove it
                if other_code in by_code and code in by_code:
                    for ev in by_code[other_code].get("evidence_sources", []):
                        if ev not in by_code[code]["evidence_sources"]:
                            by_code[code]["evidence_sources"].append(ev)
                    by_code[code]["evidence_count"] = len(by_code[code]["evidence_sources"])
                    to_remove.add(other_code)

    for code in to_remove:
        by_code.pop(code, None)

    return list(by_code.values())


def _detect_specificity_upgrades(profile: Dict, coded: set, observations: List[Dict]) -> List[Dict]:
    """Detect cases where a coded condition should be upgraded to a more specific code.
    E.g., E11.9 (diabetes unspecified) coded, but HbA1c 8.4% → should be E11.65 (with hyperglycemia)."""
    upgrades = []

    UPGRADE_RULES = {
        # If E11.9 is coded + HbA1c >= 6.5 → upgrade to E11.65
        "E11.9": [
            {"lab_loinc": "4548-4", "op": ">=", "value": 6.5,
             "upgrade_to": "E11.65", "upgrade_name": "Type 2 DM with hyperglycemia",
             "reason": "HbA1c {value}% indicates hyperglycemia — E11.65 is more specific than E11.9"},
        ],
        # If I10 is coded + CKD present → should use I12.9 (hypertensive CKD)
        "I10": [
            {"check_coded": "N18", "upgrade_to": "I12.9",
             "upgrade_name": "Hypertensive CKD",
             "reason": "Patient has both hypertension (I10) and CKD — combination code I12.9 required per ICD-10 guidelines"},
        ],
        # If E11.9 coded + CKD → E11.22 (diabetes with CKD)
        "E11.9→N18": [
            {"check_both": ["E11", "N18"], "upgrade_to": "E11.22",
             "upgrade_name": "Type 2 DM with diabetic CKD",
             "reason": "Patient has diabetes + CKD — combination code E11.22 required"},
        ],
    }

    obs_by_loinc = {o.get("loinc", ""): o for o in observations}

    for coded_code in coded:
        rules = UPGRADE_RULES.get(coded_code, [])
        for rule in rules:
            if "lab_loinc" in rule:
                obs = obs_by_loinc.get(rule["lab_loinc"])
                if obs and obs.get("value") is not None:
                    try:
                        val = float(obs["value"])
                        op = rule["op"]
                        thresh = rule["value"]
                        matched = (op == ">=" and val >= thresh) or (op == ">" and val > thresh)
                        if matched and rule["upgrade_to"] not in coded:
                            upgrades.append({
                                "tier": "SPECIFICITY_UPGRADE",
                                "icd10_code": rule["upgrade_to"],
                                "condition_name": rule["upgrade_name"],
                                "evidence_sources": [
                                    f"Specificity upgrade: {coded_code} currently coded",
                                    f"Lab: {obs.get('name', '')} = {val} ({op} {thresh})",
                                    rule["reason"].format(value=val),
                                ],
                                "evidence_count": 3,
                                "upgrade_from": coded_code,
                            })
                    except (ValueError, TypeError):
                        pass
            elif "check_coded" in rule:
                prefix = rule["check_coded"]
                has_both = any(c.startswith(prefix) for c in coded)
                if has_both and rule["upgrade_to"] not in coded:
                    upgrades.append({
                        "tier": "COMBINATION_CODE",
                        "icd10_code": rule["upgrade_to"],
                        "condition_name": rule["upgrade_name"],
                        "evidence_sources": [
                            f"Combination code: {coded_code} + {prefix} both coded separately",
                            rule["reason"],
                        ],
                        "evidence_count": 2,
                        "upgrade_from": coded_code,
                    })

    # Check E11+N18 combo
    has_dm = any(c.startswith("E11") for c in coded)
    has_ckd = any(c.startswith("N18") for c in coded)
    if has_dm and has_ckd and "E11.22" not in coded:
        upgrades.append({
            "tier": "COMBINATION_CODE",
            "icd10_code": "E11.22",
            "condition_name": "Type 2 DM with diabetic CKD",
            "evidence_sources": [
                "Combination: E11.x and N18.x both present — E11.22 required per ICD-10 guidelines",
            ],
            "evidence_count": 2,
        })

    return upgrades


def _assess_meat(gap: Dict, profile: Dict) -> Dict:
    """Assess MEAT criteria for a gap.
    M = Monitoring (labs ordered/reviewed for this condition)
    E = Evaluation (encounter where condition was discussed)
    A = Assessment (provider documented the condition in notes)
    T = Treatment (medication prescribed for this condition)"""
    condition = gap.get("condition_name", "").lower()
    icd10 = gap.get("icd10_code", "")
    icd10_prefix = icd10[:3] if icd10 else ""

    meat = {"monitoring": False, "evaluation": False, "assessment": False, "treatment": False}

    # ── M: Monitoring — check if relevant lab was ordered ──
    # Lab-based gaps automatically have monitoring
    if gap.get("tier") == "TIER_1_STRUCTURED" or gap.get("lab_value") is not None:
        meat["monitoring"] = True
    else:
        # Check if any observation relates to this condition via LOINC mapping
        for obs in profile.get("observations", []):
            loinc = obs.get("loinc", "")
            if loinc in LOINC_ICD10_MAP:
                mapping = LOINC_ICD10_MAP[loinc]
                for thresh in mapping.get("thresholds", []):
                    if thresh.get("icd10", "").startswith(icd10_prefix):
                        meat["monitoring"] = True
                        break

    # ── E: Evaluation — encounter exists in measurement period ──
    if profile.get("encounters"):
        meat["evaluation"] = True

    # ── A: Assessment — condition mentioned in Assessment/Plan section ──
    all_notes = " ".join(n.get("text", "") for n in profile.get("clinical_notes", []))
    # Check for condition name in A/P section specifically
    condition_words = [w for w in condition.split() if len(w) > 3]
    for word in condition_words[:3]:
        # Find the word in text
        for m in re.finditer(re.escape(word), all_notes, re.IGNORECASE):
            section = detect_section(all_notes, m.start())
            if section == "assessment_plan":
                meat["assessment"] = True
                break
        if meat["assessment"]:
            break
    # Fallback — any mention counts if no section detected
    if not meat["assessment"] and condition_words:
        if any(w.lower() in all_notes.lower() for w in condition_words[:2]):
            meat["assessment"] = True

    # ── T: Treatment — relevant medication from phenotype rules ──
    med_names = [m.get("name", "").lower() for m in profile.get("medications", [])]
    for rule in PHENOTYPE_RULES.values():
        if rule["icd10"].startswith(icd10_prefix):
            for marker in rule.get("medication_markers", []):
                if any(marker in mn for mn in med_names):
                    meat["treatment"] = True
                    break
            if meat["treatment"]:
                break

    return meat
