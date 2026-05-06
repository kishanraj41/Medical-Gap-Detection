"""
Agent: EvidenceAggregationAgent
"""
import re
import json
import os
import logging
import requests
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, date, timedelta

log = logging.getLogger("ensureai.agents")


class EvidenceAggregationAgent:
    """Collects all evidence per condition into unified bundles.
    Applies section weighting: Assessment/Plan > HPI > Medications > Labs > PMH > PE."""

    # Section weights per CMS guidance — Assessment & Plan highest for HCC
    SECTION_WEIGHTS = {
        "assessment_plan": 1.0, "assessment": 1.0, "plan": 1.0, "a/p": 1.0,
        "hpi": 0.85, "history_of_present_illness": 0.85,
        "medications": 0.8, "medication_list": 0.8, "FHIR_structured": 0.8,
        "labs": 0.75, "lab_results": 0.75, "diagnostics": 0.75,
        "past_medical_history": 0.6, "pmh": 0.6,
        "review_of_systems": 0.5, "ros": 0.5,
        "chief_complaint": 0.7, "cc": 0.7,
        "physical_exam": 0.3, "pe": 0.3,
        "social_history": 0.2, "family_history": 0.2,
    }

    @classmethod
    def _get_section_weight(cls, section_name: str) -> float:
        """Get weight for a section. Default 0.5 for unknown sections."""
        if not section_name:
            return 0.5
        s = section_name.lower().strip().replace(" ", "_")
        for key, weight in cls.SECTION_WEIGHTS.items():
            if key in s or s in key:
                return weight
        return 0.5

    def process(self, phenotype_matches: List[Dict], medications: List[Dict],
                abnormal_labs: List[Dict], normal_labs: List[Dict],
                temporal_entities: List[Dict]) -> List[Dict]:
        bundles = []
        for pm in phenotype_matches:
            condition = pm.get("condition") or ""
            if not condition:
                continue
            condition_lower = condition.lower()
            evidence = []
            max_section_weight = 0.0

            # From note
            for ent in temporal_entities:
                ent_text = (ent.get("text") or "").lower()
                if ent_text and (ent_text in condition_lower or condition_lower in ent_text):
                    section = ent.get("section", "")
                    weight = self._get_section_weight(section)
                    max_section_weight = max(max_section_weight, weight)
                    evidence.append({
                        "type": "diagnosis_in_note",
                        "source": "Agent 2",
                        "detail": ent.get("context", ent.get("text", "")),
                        "section": section,
                        "section_weight": weight,
                    })

            # From medications
            for med in medications:
                med_cond = (med.get("inferred_condition") or "").lower()
                if med_cond and (med_cond in condition_lower or condition_lower in med_cond):
                    evidence.append({
                        "type": "medication",
                        "source": "Agent 3",
                        "detail": f"{med.get('raw_name','')} (RxNorm {med.get('rxnorm_code','')}, ATC {med.get('atc_code','')})",
                    })

            # From abnormal labs
            for lab in abnormal_labs:
                lab_cond = (lab.get("condition") or "").lower()
                if lab_cond and (lab_cond in condition_lower or condition_lower in lab_cond):
                    evidence.append({
                        "type": "abnormal_lab",
                        "source": "Agent 4C",
                        "detail": f"{lab.get('name','')} {lab.get('value','')} ({lab.get('flag','')}) → {lab.get('maps_to_icd10','')} via UMLS",
                    })

            # From normal labs — only include if lab is RELATED to condition
            # (e.g., normal HbA1c for diabetes, normal creatinine for CKD)
            lab_condition_map = {
                "glucose": ["diabetes", "hyperglycemia"],
                "hba1c": ["diabetes", "hyperglycemia"],
                "hemoglobin a1c": ["diabetes"],
                "creatinine": ["ckd", "kidney", "renal"],
                "gfr": ["ckd", "kidney", "renal"],
                "egfr": ["ckd", "kidney", "renal"],
                "cholesterol": ["hyperlipidemia", "hypercholesterolemia", "dyslipidemia"],
                "ldl": ["hyperlipidemia", "hypercholesterolemia"],
                "hdl": ["hyperlipidemia", "dyslipidemia"],
                "triglycerides": ["hyperlipidemia", "hypertriglyceridemia"],
                "tsh": ["thyroid", "hypothyroid", "hyperthyroid"],
                "hemoglobin": ["anemia"],
                "hematocrit": ["anemia"],
                "potassium": ["hyperkalemia", "hypokalemia"],
                "sodium": ["hyponatremia", "hypernatremia"],
                "albumin": ["malnutrition", "liver"],
                "bilirubin": ["liver", "hepatic", "jaundice"],
                "alt": ["liver", "hepatic"],
                "ast": ["liver", "hepatic"],
            }
            for lab in normal_labs:
                lab_name = (lab.get("name") or "").lower()
                related_conditions = []
                for lab_key, conds in lab_condition_map.items():
                    if lab_key in lab_name:
                        related_conditions = conds
                        break
                if related_conditions and any(rc in condition_lower for rc in related_conditions):
                    evidence.append({
                        "type": "normal_lab",
                        "source": "Agent 4B",
                        "detail": f"{lab.get('name','')} {lab.get('value','')} normal — monitoring evidence for {condition}",
                    })

            # Phenotype match
            evidence.append({
                "type": "phenotype",
                "source": "Agent 7",
                "detail": f"PheKB {pm.get('criteria_count',0)} criteria met = {pm.get('strength','')}",
            })

            bundles.append({
                "condition": condition,
                "candidate_icd10": pm.get("evidence_detail", {}).get("icd10"),
                "evidence": evidence,
                "total_evidence_count": len(evidence),
                "phenotype_strength": pm.get("strength", ""),
                "max_section_weight": round(max_section_weight, 2),
            })

        return bundles


# ═══════════════════════════════════════
# AGENT 9: ICD-10 MAPPING
# ═══════════════════════════════════════
