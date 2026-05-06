"""Agent 24: Provider Attribution — link gap to rendering provider NPI"""
import logging
log = logging.getLogger("ensureai.agents")

class ProviderAttributionAgent:
    """Links gap to rendering provider NPI."""
    def __init__(self):
        log.info("Agent 24: Provider Attribution ready")
    def process(self, bundles, profile):
        for bundle in bundles:
            if not isinstance(bundle, dict): continue
            bundle["ORDERING_PROVIDER"] = ""
            encounters = profile.get("encounters", [])
            if encounters:
                bundle["ORDERING_PROVIDER"] = encounters[0].get("provider_npi", "")
        return bundles
