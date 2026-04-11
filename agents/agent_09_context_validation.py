"""Agent 9: Context Validation — NEGATION, Temporality, Screening, Family Hx
⚠️ NEGATION HAPPENS HERE — before any clinical inference"""
import re
import logging
log = logging.getLogger("ensureai.agents")

class ContextValidationAgent:
    """Validates clinical context: negation, temporality, screening, family history.
    Library: medspaCy NegEx. ⚠️ Must run BEFORE lab interpretation."""
    
    DENY_PATTERNS = [
        "denies ", "denied ", "no ", "not ", "without ", "negative for ",
        "rules out ", "rule out ", "r/o ", "does not have ", "no evidence of ",
        "no history of ", "no sign of ", "no symptoms of ", "absence of ",
        "free of ", "no complaint of ",
    ]
    FAMILY_PATTERNS = ["family history", "father had", "mother had", "sibling", "fh:", "fhx:"]
    SCREENING_PATTERNS = ["screening", "preventive", "routine", "annual exam"]
    
    def __init__(self):
        self.nlp = None
        try:
            import medspacy
            self.nlp = medspacy.load()
            log.info("Agent 9: medspaCy loaded — negation/temporality active")
        except Exception as e:
            log.warning(f"Agent 9: medspaCy failed ({e}), using regex negation")
    
    def process(self, extracted, all_notes_text):
        validated = []
        negated_count = 0
        text_lower = all_notes_text.lower()
        
        # medspaCy negation detection
        negated_terms = set()
        if self.nlp:
            try:
                doc = self.nlp(all_notes_text[:50000])
                for ent in doc.ents:
                    if ent._.is_negated:
                        negated_terms.add(ent.text.lower())
            except Exception:
                pass
        
        for entity in extracted.get("diseases", []):
            text = (entity.get("text") or "").strip()
            text_lower_e = text.lower()
            
            # Check negation
            is_negated = (
                any(text_lower_e.startswith(p) for p in self.DENY_PATTERNS) or
                text_lower_e in negated_terms or
                any(text_lower_e in nt for nt in negated_terms)
            )
            
            # Check family history
            is_family = any(p in text_lower_e for p in self.FAMILY_PATTERNS)
            
            # Check screening
            is_screening = any(p in text_lower_e for p in self.SCREENING_PATTERNS)
            
            # Temporality
            temporality = "current"
            if any(w in text_lower_e for w in ["history of", "prior", "previous", "resolved"]):
                temporality = "historical"
            
            entity["negated"] = is_negated
            entity["is_family_history"] = is_family
            entity["is_screening"] = is_screening
            entity["temporality"] = temporality
            entity["NEGATION_FLAG"] = "Yes" if is_negated else "No"
            entity["TEMPORALITY"] = temporality
            
            if is_negated or is_family:
                negated_count += 1
            else:
                validated.append(entity)
        
        log.info(f"Agent 9: {len(extracted.get('diseases', []))} entities → {len(validated)} validated, {negated_count} negated/family")
        return {"validated_entities": validated, "negated_count": negated_count, "all_entities": extracted.get("diseases", [])}
