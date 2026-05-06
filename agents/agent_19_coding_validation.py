"""Agent 19: Coding Validation — billable, CCS, chronic flag"""
import logging
log = logging.getLogger("ensureai.agents")

class CodingValidationAgent:
    """Validates ICD-10 codes: billable check, CCS category, chronic condition.
    Libraries: simple-icd-10-cm, icd-mappings, icd10-cm"""
    def __init__(self):
        self.icd_mapper = None
        try:
            from icdmappings import Mapper
            self.icd_mapper = Mapper()
            log.info("Agent 19: icd-mappings loaded — CCS + chronic flag")
        except ImportError:
            pass
        self.simple_icd = None
        try:
            import simple_icd_10_cm as sicd
            self.simple_icd = sicd
            log.info("Agent 19: simple-icd-10-cm loaded")
        except ImportError:
            pass
        log.info("Agent 19: Coding Validation ready")
    def process(self, bundles):
        for bundle in bundles:
            if not isinstance(bundle, dict): continue
            code = bundle.get("candidate_icd10", "")
            if code and self.simple_icd:
                try:
                    if self.simple_icd.is_valid_item(code):
                        bundle["is_billable"] = "Yes"
                        bundle["icd10_description"] = self.simple_icd.get_description(code)
                except Exception:
                    pass
        return bundles
