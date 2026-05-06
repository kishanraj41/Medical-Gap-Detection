"""Agent 25: Claims Comparison — compare vs EMR conditions + billed claims"""
import logging
log = logging.getLogger("ensureai.agents")

class ClaimsComparisonAgent:
    """Compares extracted conditions vs EMR + Claims. Finds Uncoded + Unbilled."""
    def __init__(self):
        log.info("Agent 25: Claims Comparison ready")
    def process(self, bundles, profile):
        conditions = profile.get("conditions", [])
        claims = profile.get("claims_codes", set())
        coded_conditions = {(c.get("icd10_code", "") or "").upper() for c in conditions}
        
        for bundle in bundles:
            if not isinstance(bundle, dict): continue
            icd10 = (bundle.get("candidate_icd10") or "").upper()
            condition = (bundle.get("condition") or "").lower()
            
            is_coded = icd10 in coded_conditions or any(
                condition in (c.get("display", "").lower()) for c in conditions
            )
            is_billed = icd10 in claims
            
            bundle["is_coded_in_gap"] = "No" if not is_coded else "Yes"
            bundle["is_billed"] = "Yes" if is_billed else "No"
            if not is_coded:
                bundle["gap_type"] = "Uncoded"
            elif not is_billed:
                bundle["gap_type"] = "Unbilled"
            else:
                bundle["gap_type"] = "None"
        
        log.info(f"Agent 25: {len(bundles)} compared vs {len(coded_conditions)} EMR + {len(claims)} claims")
        return bundles
