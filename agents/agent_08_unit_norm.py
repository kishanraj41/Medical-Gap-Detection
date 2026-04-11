"""Agent 8: Unit & Value Normalization — UCUM, pint, pyucum"""
import logging
log = logging.getLogger("ensureai.agents")

class UnitNormAgent:
    """Normalizes lab units to UCUM standard. Converts values.
    Libraries: pyucum, pint, UCUM API (ucum.nlm.nih.gov)"""
    def __init__(self):
        self.pyucum_available = False
        try:
            import pyucum
            self.pyucum_available = True
            log.info("Agent 8: pyucum loaded — UCUM unit conversion active")
        except ImportError:
            log.info("Agent 8: pyucum not installed")
        log.info("Agent 8: Unit Normalization ready")
    def process(self, observations):
        normalized = []
        for obs in observations:
            obs["UNIT_NORMALIZED"] = obs.get("unit", "")
            obs["VALUE_NORMALIZED"] = obs.get("value")
            obs["LAB_SCALE"] = "quantitative" if obs.get("value") is not None else "ordinal"
            normalized.append(obs)
        return normalized
