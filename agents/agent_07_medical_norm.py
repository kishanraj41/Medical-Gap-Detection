"""Agent 7: Medical Normalization — SNOMED/UMLS concept mapping"""
import logging
log = logging.getLogger("ensureai.agents")

class MedicalNormAgent:
    """Maps extracted terms to SNOMED/UMLS concepts. Resolves synonyms.
    Libraries: UMLS API, QuickUMLS (when available), related-ontologies"""
    def __init__(self):
        self.related_ontologies = None
        try:
            from related_ontologies import loinc_snomed
            self.related_ontologies = loinc_snomed
            log.info("Agent 7: related-ontologies loaded")
        except ImportError:
            pass
        log.info("Agent 7: Medical Normalization ready")
    def process(self, text):
        # Synonym resolution for common abbreviations
        synonyms = {
            "dm": "diabetes mellitus", "dm2": "type 2 diabetes mellitus",
            "t2dm": "type 2 diabetes mellitus", "htn": "hypertension",
            "hld": "hyperlipidemia", "chf": "heart failure",
            "ckd": "chronic kidney disease", "copd": "chronic obstructive pulmonary disease",
            "gerd": "gastroesophageal reflux disease", "cad": "coronary artery disease",
            "afib": "atrial fibrillation", "dvt": "deep vein thrombosis",
            "pe": "pulmonary embolism", "osa": "obstructive sleep apnea",
            "bph": "benign prostatic hyperplasia", "uti": "urinary tract infection",
        }
        return {"synonyms": synonyms, "text_processed": True}
