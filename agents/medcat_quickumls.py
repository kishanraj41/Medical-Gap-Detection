"""
MedCAT + QuickUMLS Integration Module
Auto-activates when UMLS Metathesaurus files are available.

Setup (requires UMLS license):
  1. Get UMLS license: https://uts.nlm.nih.gov/uts/signup-login
  2. Download UMLS Metathesaurus: https://www.nlm.nih.gov/research/umls/licensedcontent/umlsknowledgesources.html
  3. pip install medcat quickumls
  4. Create MedCAT model: python -m medcat.utils.make_vocab /path/to/umls/
  5. Set env: UMLS_DATA_DIR=/path/to/umls/ MEDCAT_MODEL_DIR=/path/to/model/

Without UMLS files, this module does nothing — pipeline uses existing NER + keyword mapping.
"""
import os
import logging
from typing import Dict, List, Optional

log = logging.getLogger("ensureai.agents")


class MedCATIntegration:
    """MedCAT NER for clinical text — auto-links to SNOMED/ICD-10.
    Requires: pip install medcat + UMLS Metathesaurus download."""

    def __init__(self):
        self.available = False
        self.cat = None
        model_dir = os.environ.get("MEDCAT_MODEL_DIR", "")

        if not model_dir or not os.path.exists(model_dir):
            log.info("MedCAT: MEDCAT_MODEL_DIR not set or not found. "
                     "To enable: pip install medcat, download UMLS, "
                     "set MEDCAT_MODEL_DIR=/path/to/model/")
            return

        try:
            from medcat.cat import CAT
            self.cat = CAT.load_model_pack(model_dir)
            self.available = True
            log.info(f"MedCAT loaded from {model_dir}")
        except ImportError:
            log.info("MedCAT: pip install medcat to enable")
        except Exception as e:
            log.warning(f"MedCAT failed to load: {e}")

    def extract_entities(self, text: str) -> List[Dict]:
        """Extract clinical entities with SNOMED/ICD-10 codes from text."""
        if not self.available or not text:
            return []
        try:
            doc = self.cat.get_entities(text)
            entities = []
            for ent_id, ent in doc.get("entities", {}).items():
                entities.append({
                    "text": ent.get("source_value", ""),
                    "cui": ent.get("cui", ""),
                    "name": ent.get("preferred_name", ""),
                    "type": ent.get("type_ids", [""])[0] if ent.get("type_ids") else "",
                    "icd10": ent.get("icd10", []),
                    "snomed": ent.get("snomed", []),
                    "confidence": ent.get("context_similarity", 0),
                    "negated": ent.get("meta_anns", {}).get("negation", {}).get("value", ""),
                    "source": "MedCAT",
                })
            return entities
        except Exception as e:
            log.warning(f"MedCAT extraction failed: {e}")
            return []


class QuickUMLSIntegration:
    """QuickUMLS for fast concept matching against UMLS.
    Requires: pip install quickumls + UMLS Metathesaurus files."""

    def __init__(self):
        self.available = False
        self.matcher = None
        umls_dir = os.environ.get("QUICKUMLS_DATA_DIR", "")

        if not umls_dir or not os.path.exists(umls_dir):
            log.info("QuickUMLS: QUICKUMLS_DATA_DIR not set or not found. "
                     "To enable: pip install quickumls, download UMLS, "
                     "run: python -m quickumls.install /path/to/umls/ /path/to/output/")
            return

        try:
            from quickumls import QuickUMLS
            self.matcher = QuickUMLS(umls_dir)
            self.available = True
            log.info(f"QuickUMLS loaded from {umls_dir}")
        except ImportError:
            log.info("QuickUMLS: pip install quickumls to enable")
        except Exception as e:
            log.warning(f"QuickUMLS failed to load: {e}")

    def match_concepts(self, text: str) -> List[Dict]:
        """Match clinical text to UMLS concepts."""
        if not self.available or not text:
            return []
        try:
            matches = self.matcher.match(text)
            results = []
            for match_group in matches:
                best = match_group[0]  # Highest similarity
                results.append({
                    "text": best.get("ngram", ""),
                    "cui": best.get("cui", ""),
                    "name": best.get("term", ""),
                    "similarity": best.get("similarity", 0),
                    "semtypes": best.get("semtypes", []),
                    "source": "QuickUMLS",
                })
            return results
        except Exception as e:
            log.warning(f"QuickUMLS matching failed: {e}")
            return []


# Singleton instances — created once, reused across pipeline
_medcat = None
_quickumls = None


def get_medcat() -> MedCATIntegration:
    global _medcat
    if _medcat is None:
        _medcat = MedCATIntegration()
    return _medcat


def get_quickumls() -> QuickUMLSIntegration:
    global _quickumls
    if _quickumls is None:
        _quickumls = QuickUMLSIntegration()
    return _quickumls
