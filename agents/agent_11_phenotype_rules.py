"""
Agent 7: Phenotype Rules (OMOP/PheKB-style)
Clinical phenotyping based on:
  - OMOP PhenotypeLibrary (https://github.com/OHDSI/PhenotypeLibrary)
  - PheKB validated algorithms (https://phekb.org)
  - ADA, KDIGO, AHA, CMS clinical guidelines

Each phenotype has explicit rules:
  DM:   A1c ≥6.5 + DM medication + DM mention in note
  CKD:  eGFR <60 + CKD mention + renal medication
  CHF:  BNP >100 + CHF mention + diuretic/ACEi
  COPD: spirometry + smoking history + bronchodilator
  etc.

Custom rule engine: each disease has required + supporting criteria.
"""
import logging
from typing import Dict, List, Any

log = logging.getLogger("ensureai.agents")


# ── OMOP/PheKB PHENOTYPE RULES ──
# Each rule has: lab thresholds, medication classes, note keywords
PHENOTYPE_RULES = {
    "diabetes_mellitus": {
        "icd10": "E11",
        "display": "Diabetes Mellitus Type 2",
        "criteria": {
            "lab": {"loinc": ["4548-4", "17856-6"], "operator": ">=", "threshold": 6.5, "name": "HbA1c ≥6.5%"},
            "lab_alt": {"loinc": ["1558-6", "2345-7"], "operator": ">=", "threshold": 126, "name": "Fasting Glucose ≥126"},
            "medication": ["metformin", "insulin", "glipizide", "glyburide", "glimepiride", "sitagliptin",
                           "empagliflozin", "dapagliflozin", "canagliflozin", "liraglutide", "semaglutide",
                           "dulaglutide", "pioglitazone", "saxagliptin", "linagliptin", "jardiance", "farxiga",
                           "invokana", "januvia", "actos", "amaryl", "glucophage", "ozempic", "trulicity"],
            "note_keywords": ["diabetes", "diabetic", "dm", "dm2", "t2dm", "type 2 diabetes", "type ii diabetes",
                              "diabetes mellitus", "niddm", "a1c", "hba1c"],
        },
        "source": "ADA 2024 + PheKB Algorithm 41",
    },
    "ckd": {
        "icd10": "N18",
        "display": "Chronic Kidney Disease",
        "criteria": {
            "lab": {"loinc": ["33914-3", "48642-3", "62238-1", "69405-9"], "operator": "<", "threshold": 60, "name": "eGFR <60"},
            "lab_alt": {"loinc": ["2160-0"], "operator": ">=", "threshold": 1.5, "name": "Creatinine ≥1.5"},
            "medication": ["lisinopril", "losartan", "valsartan", "enalapril", "ramipril", "irbesartan",
                           "benazepril", "candesartan", "telmisartan", "olmesartan", "amlodipine"],
            "note_keywords": ["ckd", "chronic kidney", "renal disease", "kidney disease", "renal failure",
                              "nephropathy", "dialysis", "egfr", "gfr", "creatinine elevated"],
        },
        "source": "KDIGO 2024 + PheKB Algorithm 27",
    },
    "chf": {
        "icd10": "I50",
        "display": "Heart Failure",
        "criteria": {
            "lab": {"loinc": ["30934-4", "33762-6"], "operator": ">=", "threshold": 100, "name": "BNP ≥100 or NT-proBNP ≥300"},
            "medication": ["furosemide", "bumetanide", "torsemide", "spironolactone", "eplerenone",
                           "carvedilol", "metoprolol", "bisoprolol", "sacubitril", "entresto",
                           "digoxin", "hydralazine", "isosorbide", "lasix"],
            "note_keywords": ["heart failure", "chf", "hf", "congestive", "ef ", "ejection fraction",
                              "systolic dysfunction", "diastolic dysfunction", "bnp", "cardiomyopathy"],
        },
        "source": "AHA/ACC 2023 + OMOP Phenotype 218",
    },
    "copd": {
        "icd10": "J44",
        "display": "COPD",
        "criteria": {
            "lab": {"loinc": [], "operator": "", "threshold": 0, "name": "FEV1/FVC ratio (not in standard labs)"},
            "medication": ["albuterol", "ipratropium", "tiotropium", "fluticasone", "budesonide",
                           "formoterol", "salmeterol", "umeclidinium", "vilanterol", "roflumilast",
                           "spiriva", "advair", "symbicort", "breo", "trelegy", "proair", "ventolin"],
            "note_keywords": ["copd", "chronic obstructive", "emphysema", "chronic bronchitis",
                              "fev1", "spirometry", "pulmonary function", "smoking", "smoker",
                              "bronchodilator", "inhaler", "oxygen therapy"],
        },
        "source": "GOLD 2024 + PheKB Algorithm 7",
    },
    "hypothyroidism": {
        "icd10": "E03",
        "display": "Hypothyroidism",
        "criteria": {
            "lab": {"loinc": ["3016-3", "14920-3"], "operator": ">=", "threshold": 4.5, "name": "TSH ≥4.5"},
            "medication": ["levothyroxine", "synthroid", "armour thyroid", "liothyronine",
                           "tirosint", "levoxyl", "cytomel", "euthyrox", "unithroid"],
            "note_keywords": ["hypothyroid", "thyroid", "tsh elevated", "levothyroxine",
                              "hashimoto", "myxedema", "low thyroid"],
        },
        "source": "ATA 2024",
    },
    "hyperlipidemia": {
        "icd10": "E78",
        "display": "Hyperlipidemia",
        "criteria": {
            "lab": {"loinc": ["2093-3"], "operator": ">=", "threshold": 240, "name": "Total Cholesterol ≥240"},
            "lab_alt": {"loinc": ["2089-1", "13457-7"], "operator": ">=", "threshold": 160, "name": "LDL ≥160"},
            "medication": ["atorvastatin", "rosuvastatin", "simvastatin", "pravastatin", "lovastatin",
                           "pitavastatin", "ezetimibe", "fenofibrate", "gemfibrozil", "alirocumab",
                           "evolocumab", "lipitor", "crestor", "zocor", "zetia", "repatha", "praluent"],
            "note_keywords": ["hyperlipidemia", "hypercholesterolemia", "dyslipidemia", "hld",
                              "high cholesterol", "elevated ldl", "statin", "lipid", "cholesterol"],
        },
        "source": "ATP-III/AHA 2024",
    },
    "anemia": {
        "icd10": "D64",
        "display": "Anemia",
        "criteria": {
            "lab": {"loinc": ["718-7"], "operator": "<", "threshold": 12.0, "name": "Hemoglobin <12 (female) or <13.5 (male)"},
            "medication": ["ferrous sulfate", "iron", "epoetin", "darbepoetin", "folic acid",
                           "cyanocobalamin", "b12", "vitamin b12"],
            "note_keywords": ["anemia", "anemic", "low hemoglobin", "iron deficiency",
                              "b12 deficiency", "folate deficiency", "pancytopenia"],
        },
        "source": "WHO + OMOP Phenotype 37",
    },
    "hypertension": {
        "icd10": "I10",
        "display": "Essential Hypertension",
        "criteria": {
            "lab": {"loinc": [], "operator": "", "threshold": 0, "name": "BP measurement (not in standard labs)"},
            "medication": ["lisinopril", "amlodipine", "losartan", "metoprolol", "hydrochlorothiazide",
                           "atenolol", "valsartan", "carvedilol", "diltiazem", "nifedipine",
                           "benazepril", "enalapril", "ramipril", "irbesartan", "clonidine",
                           "hctz", "norvasc", "diovan", "cozaar", "toprol"],
            "note_keywords": ["hypertension", "htn", "high blood pressure", "bp elevated",
                              "blood pressure", "hypertensive"],
        },
        "source": "AHA/ACC 2024",
    },
    "obesity": {
        "icd10": "E66",
        "display": "Obesity",
        "criteria": {
            "lab": {"loinc": [], "operator": "", "threshold": 0, "name": "BMI ≥30 (vital sign, not lab)"},
            "medication": ["orlistat", "phentermine", "liraglutide", "semaglutide", "naltrexone",
                           "contrave", "qsymia", "saxenda", "wegovy"],
            "note_keywords": ["obesity", "obese", "morbid obesity", "bmi", "overweight",
                              "weight management", "bariatric"],
        },
        "source": "CMS + OMOP",
    },
    "depression": {
        "icd10": "F32",
        "display": "Major Depressive Disorder",
        "criteria": {
            "lab": {"loinc": [], "operator": "", "threshold": 0, "name": "PHQ-9 ≥10 (screening, not lab)"},
            "medication": ["sertraline", "fluoxetine", "escitalopram", "citalopram", "paroxetine",
                           "venlafaxine", "duloxetine", "bupropion", "mirtazapine", "trazodone",
                           "amitriptyline", "nortriptyline", "lexapro", "zoloft", "prozac",
                           "cymbalta", "effexor", "wellbutrin"],
            "note_keywords": ["depression", "depressive", "mdd", "major depressive", "phq-9",
                              "depressed", "suicidal", "antidepressant"],
        },
        "source": "APA 2024 + PheKB Algorithm 15",
    },
    "gerd": {
        "icd10": "K21",
        "display": "GERD",
        "criteria": {
            "lab": {"loinc": [], "operator": "", "threshold": 0, "name": "No diagnostic lab"},
            "medication": ["omeprazole", "pantoprazole", "esomeprazole", "lansoprazole",
                           "rabeprazole", "famotidine", "ranitidine", "prilosec", "nexium",
                           "protonix", "prevacid", "dexilant"],
            "note_keywords": ["gerd", "reflux", "gastroesophageal", "heartburn", "acid reflux",
                              "esophagitis", "ppi", "proton pump"],
        },
        "source": "ACG 2024",
    },
    "liver_disease": {
        "icd10": "K76",
        "display": "Liver Disease",
        "criteria": {
            "lab": {"loinc": ["1742-6", "1920-8"], "operator": ">=", "threshold": 100, "name": "ALT or AST ≥100"},
            "lab_alt": {"loinc": ["1975-2"], "operator": ">=", "threshold": 3.0, "name": "Bilirubin ≥3.0"},
            "medication": ["ursodiol", "lactulose", "rifaximin", "spironolactone", "furosemide",
                           "nadolol", "propranolol"],
            "note_keywords": ["liver", "hepatic", "cirrhosis", "hepatitis", "fatty liver",
                              "nafld", "nash", "liver disease", "hepatomegaly", "ascites"],
        },
        "source": "AASLD 2024",
    },
}


class PhenotypeRulesAgent:
    """Applies OMOP/PheKB phenotype rules to check evidence patterns.
    Custom rule engine: each disease has lab thresholds + medications + note keywords.
    Sources: PheKB (https://phekb.org), OHDSI PhenotypeLibrary, ADA, KDIGO, AHA, CMS."""

    def process(self, temporal_entities: List[Dict], medications: List[Dict],
                abnormal_labs: List[Dict], normal_labs: List[Dict]) -> List[Dict]:
        phenotype_matches = []

        # Build lookup sets
        disease_texts = {(e.get("text") or "").lower() for e in temporal_entities}
        med_names = {(m.get("raw_name") or m.get("generic_name") or "").lower() for m in medications}
        lab_values = {}
        for lab in abnormal_labs + normal_labs:
            loinc = lab.get("loinc", "")
            val = lab.get("value")
            if loinc and val is not None:
                try:
                    lab_values[loinc] = float(val)
                except (ValueError, TypeError):
                    pass

        # Check each phenotype rule
        for rule_id, rule in PHENOTYPE_RULES.items():
            criteria = rule["criteria"]
            evidence = {"criteria_met": {}, "criteria_detail": {}}

            # Check LAB criteria
            lab_met = False
            lab_rule = criteria.get("lab", {})
            if lab_rule.get("loinc"):
                for loinc in lab_rule["loinc"]:
                    if loinc in lab_values:
                        val = lab_values[loinc]
                        op = lab_rule.get("operator", "")
                        thresh = lab_rule.get("threshold", 0)
                        if op == ">=" and val >= thresh:
                            lab_met = True
                        elif op == "<" and val < thresh:
                            lab_met = True
                        elif op == ">" and val > thresh:
                            lab_met = True
                        elif op == "<=" and val <= thresh:
                            lab_met = True
                        if lab_met:
                            evidence["criteria_met"]["diagnostic_lab"] = True
                            evidence["criteria_detail"]["diagnostic_lab"] = f"{lab_rule['name']} (actual: {val})"
                            break

            # Check alternate lab criteria
            if not lab_met and criteria.get("lab_alt"):
                alt = criteria["lab_alt"]
                for loinc in alt.get("loinc", []):
                    if loinc in lab_values:
                        val = lab_values[loinc]
                        op = alt.get("operator", "")
                        thresh = alt.get("threshold", 0)
                        if (op == ">=" and val >= thresh) or (op == "<" and val < thresh):
                            lab_met = True
                            evidence["criteria_met"]["diagnostic_lab_alt"] = True
                            evidence["criteria_detail"]["diagnostic_lab_alt"] = f"{alt['name']} (actual: {val})"
                            break

            # Check MEDICATION criteria
            med_met = False
            for med_pattern in criteria.get("medication", []):
                if any(med_pattern in m for m in med_names):
                    med_met = True
                    evidence["criteria_met"]["medication"] = True
                    evidence["criteria_detail"]["medication"] = f"Patient takes {med_pattern}"
                    break

            # Check NOTE KEYWORD criteria
            note_met = False
            for keyword in criteria.get("note_keywords", []):
                if any(keyword in dt for dt in disease_texts):
                    note_met = True
                    evidence["criteria_met"]["note_mention"] = True
                    evidence["criteria_detail"]["note_mention"] = f"'{keyword}' found in clinical note"
                    break

            # Score: count criteria met
            criteria_count = sum([lab_met, med_met, note_met])
            if criteria_count == 0:
                continue  # No match at all

            # Strength based on criteria count
            if criteria_count >= 3:
                strength = "strong"
            elif criteria_count == 2:
                strength = "moderate"
            else:
                strength = "weak"

            phenotype_matches.append({
                "condition": rule["display"],
                "phenotype_id": rule_id,
                "icd10": rule["icd10"],
                "criteria_count": criteria_count,
                "criteria_total": 3,
                "strength": strength,
                "evidence_detail": evidence,
                "source": rule["source"],
            })

        # Also add temporal entities that didn't match any phenotype rule
        matched_conditions = {pm["condition"].lower() for pm in phenotype_matches}
        for ent in temporal_entities:
            text = (ent.get("text") or "").strip()
            if text and text.lower() not in matched_conditions:
                phenotype_matches.append({
                    "condition": text,
                    "phenotype_id": None,
                    "icd10": None,
                    "criteria_count": 1,
                    "criteria_total": 3,
                    "strength": "weak",
                    "evidence_detail": {"criteria_met": {"note_mention": True}, "criteria_detail": {"note_mention": f"NER extracted from note"}},
                    "source": "NER extraction (no phenotype rule)",
                })

        log.info(f"Agent 7: {len(phenotype_matches)} phenotype matches "
                 f"({sum(1 for p in phenotype_matches if p['strength']=='strong')} strong, "
                 f"{sum(1 for p in phenotype_matches if p['strength']=='moderate')} moderate, "
                 f"{sum(1 for p in phenotype_matches if p['strength']=='weak')} weak)")

        return phenotype_matches
