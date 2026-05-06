"""Agent 10: Lab Structuring & Interpretation
Full 39-column lab schema. Uses loinchpo, UMLS, MedlinePlus, CSV thresholds.
Datasets: LabQAR (github.com/balubhasuran/LabQAR), Kaggle healthcare"""
import os
import csv
import re
import logging
import requests
from typing import Dict, List, Optional
log = logging.getLogger("ensureai.agents")

class LabInterpretationAgent:
    """Structures labs, checks reference ranges + diagnostic thresholds, maps to diseases.
    Libraries: loinchpo, pyucum, related-ontologies, UMLS API, MedlinePlus API"""
    
    def __init__(self):
        # Load reference ranges CSV (our 87 LOINC codes — PRIMARY)
        self.ref_ranges = {}
        csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "lab_reference_ranges.csv")
        try:
            with open(csv_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    loinc = row.get("LOINC", "").strip()
                    if loinc:
                        self.ref_ranges[loinc] = row
            log.info(f"Agent 10: Loaded {len(self.ref_ranges)} LOINC from CSV (primary)")
        except Exception as e:
            log.warning(f"Agent 10: CSV load failed: {e}")

        # Load LabQAR dataset (550 lab reference ranges — SECONDARY)
        # Source: github.com/balubhasuran/LabQAR (MIT License)
        self.labqar_ranges = {}
        labqar_path = os.path.join(os.path.dirname(__file__), "..", "data", "labqar_reference_ranges.json")
        try:
            import json
            with open(labqar_path, "r") as f:
                labqar_data = json.load(f)
                for entry in labqar_data:
                    loinc = entry.get("loinc", "")
                    if loinc and loinc not in self.ref_ranges:
                        # Only add if not already in our primary CSV
                        gender = entry.get("gender", "any")
                        key = f"{loinc}_{gender}" if gender != "any" else loinc
                        self.labqar_ranges[loinc] = entry
                        # Also add to ref_ranges for lookup
                        self.ref_ranges[loinc] = {
                            "LOINC": loinc,
                            "TEST_NAME": entry.get("test", ""),
                            "REF_LOW": entry.get("ref_low", ""),
                            "REF_HIGH": entry.get("ref_high", ""),
                            "UNIT": entry.get("unit", ""),
                            "CONDITION_HIGH": entry.get("condition_high", ""),
                            "CONDITION_LOW": entry.get("condition_low", ""),
                            "DIAG_THRESHOLD": entry.get("diag_threshold", ""),
                            "DIAG_OPERATOR": entry.get("diag_op", ""),
                            "DIAG_CONDITION": entry.get("diag_condition", ""),
                            "SOURCE": entry.get("source", "LabQAR"),
                        }
            log.info(f"Agent 10: Loaded {len(self.labqar_ranges)} from LabQAR (secondary). Total: {len(self.ref_ranges)} LOINC codes")
        except Exception as e:
            log.info(f"Agent 10: LabQAR not loaded ({e}). Using CSV only.")
        
        # loinchpo
        self.loinchpo = None
        try:
            from loinchpo import Loinc2Hpo
            self.loinchpo = Loinc2Hpo()
            log.info("Agent 10: loinchpo loaded — LOINC→HPO phenotype active")
        except Exception:
            log.info("Agent 10: loinchpo not available")
        
        # MedlinePlus
        self.medlineplus = None
        try:
            from .clinical_apis import get_medlineplus
            self.medlineplus = get_medlineplus()
            log.info("Agent 10: MedlinePlus API loaded")
        except Exception:
            pass
        
        self.umls_api_key = os.environ.get("UMLS_API_KEY", "")
    
    def process(self, observations, unit_normalized, demographics) -> Dict:
        normal = []
        abnormal = []
        all_structured = []
        gender = (demographics.get("gender") or "").lower()
        
        for obs in observations:
            loinc = obs.get("loinc", "")
            value = obs.get("value") if obs.get("VALUE_NORMALIZED") is None else obs.get("VALUE_NORMALIZED")
            name = obs.get("name", "")
            unit = obs.get("UNIT_NORMALIZED") or obs.get("unit", "")
            
            # Build full 39-column lab record
            lab = {
                "LAB_ANALYTE": name,
                "LOINC_CODE": loinc,
                "TEST_CATEGORY": self._get_test_category(loinc),
                "PANEL_NAME": "",
                "LAB_SPECIMEN": obs.get("LAB_SPECIMEN", "blood"),
                "LAB_BODY_SITE": obs.get("LAB_BODY_SITE", ""),
                "LAB_PROPERTY": obs.get("LAB_PROPERTY", ""),
                "LAB_METHOD": obs.get("LAB_METHOD", ""),
                "LAB_QUALIFIER": obs.get("LAB_QUALIFIER", ""),
                "LAB_TIMING": obs.get("LAB_TIMING", ""),
                "FASTING_STATUS": obs.get("FASTING_STATUS", ""),
                "LAB_DATE": obs.get("date", ""),
                "TEMPORALITY": "current",
                "LAB_RESULT_VALUE": value,
                "LAB_UNIT": unit,
                "UNIT_NORMALIZED": unit,
                "VALUE_NORMALIZED": value,
                "LAB_SCALE": obs.get("LAB_SCALE", "quantitative" if value is not None else ""),
                "REFERENCE_RANGE_MIN": None,
                "REFERENCE_RANGE_MAX": None,
                "ABNORMAL_FLAG": "",
                "IS_ABNORMAL": "No",
                "SEVERITY": "",
                "DELTA_CHANGE": "",
                "DIAGNOSTIC_THRESHOLD": "",
                "THRESHOLD_OPERATOR": "",
                "CLINICAL_INTERPRETATION": "",
                "ASSOCIATED_CONDITION": "",
                "PHENOTYPE_MAPPING": "",
                "FOUND_IN_SECTION": obs.get("section", ""),
                "EVIDENCE_TYPE": "Primary" if obs.get("source") != "clinical_note_extraction" else "Secondary",
                "NEGATION_FLAG": "No",
                "CONFIDENCE_SCORE": "",
                "SOURCE": obs.get("source", "FHIR_Observation"),
                "FHIR_RESOURCE_TYPE": "Observation",
                "ORDERING_PROVIDER": "",
                "SOURCE_DOCUMENT_DATE": obs.get("date", ""),
                # Keep original fields for backward compat
                "name": name, "loinc": loinc, "value": value, "unit": unit, "date": obs.get("date", ""),
            }
            
            # Look up reference range from CSV
            if loinc in self.ref_ranges:
                ref = self.ref_ranges[loinc]
                try:
                    ref_low = float(ref.get("REF_LOW", 0) or 0)
                    ref_high = float(ref.get("REF_HIGH", 999) or 999)
                    # Gender-specific ranges
                    if gender in ("female", "f") and ref.get("REF_LOW_F"):
                        ref_low = float(ref["REF_LOW_F"])
                        ref_high = float(ref.get("REF_HIGH_F") or ref_high)
                    
                    lab["REFERENCE_RANGE_MIN"] = ref_low
                    lab["REFERENCE_RANGE_MAX"] = ref_high
                    lab["ref_low"] = ref_low
                    lab["ref_high"] = ref_high
                    
                    # Check abnormality
                    if value is not None:
                        if value > ref_high:
                            lab["ABNORMAL_FLAG"] = "H"
                            lab["IS_ABNORMAL"] = "Yes"
                            lab["ASSOCIATED_CONDITION"] = ref.get("CONDITION_HIGH", "")
                            lab["CLINICAL_INTERPRETATION"] = ref.get("INTERPRETATION_HIGH", "")
                        elif value < ref_low:
                            lab["ABNORMAL_FLAG"] = "L"
                            lab["IS_ABNORMAL"] = "Yes"
                            lab["ASSOCIATED_CONDITION"] = ref.get("CONDITION_LOW", "")
                            lab["CLINICAL_INTERPRETATION"] = ref.get("INTERPRETATION_LOW", "")
                        
                        # Severity
                        if lab["IS_ABNORMAL"] == "Yes":
                            range_span = ref_high - ref_low
                            if range_span > 0:
                                if lab["ABNORMAL_FLAG"] == "H":
                                    deviation = (value - ref_high) / range_span
                                else:
                                    deviation = (ref_low - value) / range_span
                                lab["SEVERITY"] = "Severe" if deviation > 1.0 else ("Moderate" if deviation > 0.3 else "Mild")
                    
                    # Diagnostic threshold
                    diag_thresh = ref.get("DIAG_THRESHOLD", "")
                    diag_op = ref.get("DIAG_OPERATOR", "")
                    if diag_thresh and diag_op and value is not None:
                        lab["DIAGNOSTIC_THRESHOLD"] = diag_thresh
                        lab["THRESHOLD_OPERATOR"] = diag_op
                        try:
                            thresh = float(diag_thresh)
                            if (diag_op == ">=" and value >= thresh) or (diag_op == "<" and value < thresh):
                                lab["ASSOCIATED_CONDITION"] = ref.get("DIAG_CONDITION", lab["ASSOCIATED_CONDITION"])
                        except ValueError:
                            pass
                    
                except (ValueError, TypeError):
                    pass
            
            # loinchpo HPO phenotype
            if self.loinchpo and loinc and lab["IS_ABNORMAL"] == "Yes":
                try:
                    outcome = "H" if lab["ABNORMAL_FLAG"] in ("H", "HH") else "L"
                    hpo = self.loinchpo.loinc_to_hpo(loinc, outcome)
                    if hpo:
                        lab["PHENOTYPE_MAPPING"] = str(hpo)
                except Exception:
                    pass
            
            lab["flag"] = lab["ABNORMAL_FLAG"]
            lab["condition"] = lab["ASSOCIATED_CONDITION"]
            all_structured.append(lab)
            
            if lab["IS_ABNORMAL"] == "Yes":
                abnormal.append(lab)
            else:
                normal.append(lab)
        
        log.info(f"Agent 10: {len(observations)} labs → {len(normal)} normal, {len(abnormal)} abnormal")
        return {"normal": normal, "abnormal": abnormal, "all_structured": all_structured}
    
    def _get_test_category(self, loinc):
        categories = {
            "4548-4": "Diabetes", "17856-6": "Diabetes", "2345-7": "Diabetes", "1558-6": "Diabetes",
            "2093-3": "Lipid", "2089-1": "Lipid", "2085-9": "Lipid", "2571-8": "Lipid",
            "33914-3": "Renal", "2160-0": "Renal", "3094-0": "Renal",
            "718-7": "CBC", "4544-3": "CBC", "6690-2": "CBC", "26515-7": "CBC",
            "2823-3": "CMP", "2951-2": "CMP", "2075-0": "CMP",
            "3016-3": "Thyroid", "3024-7": "Thyroid",
            "1742-6": "Liver", "1920-8": "Liver", "1975-2": "Liver",
            "10839-9": "Cardiac", "30934-4": "Cardiac", "33762-6": "Cardiac",
        }
        return categories.get(loinc, "Other")
