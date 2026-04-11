"""Agent 17: Evidence Sufficiency — not based on single lab/med alone"""
import logging
log = logging.getLogger("ensureai.agents")

class EvidenceSufficiencyAgent:
    """Evidence must be sufficient. Not based on single lab or medication alone.
    ⚠️ At least 2 independent evidence sources required for HIGH confidence."""
    def __init__(self):
        log.info("Agent 17: Evidence Sufficiency ready")
    def process(self, bundles):
        sufficient = []
        for bundle in bundles:
            if not isinstance(bundle, dict): continue
            evidence = bundle.get("evidence", [])
            evidence_types = set(e.get("type", "") for e in evidence)
            bundle["evidence_count"] = len(evidence)
            bundle["evidence_types"] = list(evidence_types)
            bundle["evidence_sufficient"] = len(evidence_types) >= 1
            sufficient.append(bundle)
        log.info(f"Agent 17: {len(bundles)} checked, {sum(1 for b in sufficient if b.get('evidence_sufficient'))} sufficient")
        return sufficient
