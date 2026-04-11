"""Agent 20: Deduplication — remove duplicate conditions, merge evidence"""
import logging
log = logging.getLogger("ensureai.agents")

class DeduplicationAgent:
    """Removes duplicate conditions. Merges evidence from multiple mentions."""
    def __init__(self):
        log.info("Agent 20: Deduplication ready")
    def process(self, bundles):
        seen = {}
        for bundle in bundles:
            if not isinstance(bundle, dict): continue
            key = (bundle.get("condition", "").lower(), bundle.get("candidate_icd10", ""))
            if key in seen:
                existing = seen[key]
                existing.setdefault("evidence", []).extend(bundle.get("evidence", []))
            else:
                seen[key] = bundle
        deduped = list(seen.values())
        log.info(f"Agent 20: {len(bundles)} → {len(deduped)} after dedup")
        return deduped
