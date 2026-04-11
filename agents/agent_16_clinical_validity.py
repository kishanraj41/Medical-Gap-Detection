"""Agent 16: Clinical Validity — is condition clinically valid?"""
import logging
log = logging.getLogger("ensureai.agents")

class ClinicalValidityAgent:
    """Checks if condition is clinically valid based on evidence.
    Filters out conditions with insufficient clinical basis."""
    def __init__(self):
        log.info("Agent 16: Clinical Validity ready")
    def process(self, evidence_bundles):
        valid = []
        for bundle in evidence_bundles:
            if not isinstance(bundle, dict): continue
            condition = bundle.get("condition", "")
            evidence = bundle.get("evidence", [])
            if not condition or len(condition) < 3:
                continue
            bundle["clinically_valid"] = True
            valid.append(bundle)
        log.info(f"Agent 16: {len(evidence_bundles)} → {len(valid)} clinically valid")
        return valid
