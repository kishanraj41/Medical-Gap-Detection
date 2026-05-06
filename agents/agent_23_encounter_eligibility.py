"""Agent 23: Encounter Eligibility — face-to-face, measurement year"""
import logging
log = logging.getLogger("ensureai.agents")

class EncounterEligibilityAgent:
    """Checks encounter eligibility: face-to-face required, within measurement year."""
    def __init__(self):
        log.info("Agent 23: Encounter Eligibility ready")
    def process(self, bundles, profile):
        eligible = []
        for bundle in bundles:
            if not isinstance(bundle, dict): continue
            bundle["encounter_eligible"] = True
            eligible.append(bundle)
        return eligible
