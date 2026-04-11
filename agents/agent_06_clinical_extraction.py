"""
Agent 6: Clinical Extraction Agent (GPU/CPU Dual Mode)
Extracts diseases, medications, labs from clinical note text.

GPU mode: d4data/biomedical-ner-all (ClinicalBERT) — F1 0.9118 on clinical text
CPU mode: Regex + medical dictionary pattern matching — lightweight fallback

The agent auto-detects GPU availability and selects the appropriate mode.
"""
import re
import logging
from typing import Dict, List, Any

log = logging.getLogger("gapdetect.agents.extraction")

# Try to load GPU NER
_GPU_AVAILABLE = False
_ner_pipeline = None

try:
    import torch
    if torch.cuda.is_available():
        from transformers import pipeline as hf_pipeline
        _ner_pipeline = hf_pipeline(
            "ner",
            model="d4data/biomedical-ner-all",
            aggregation_strategy="simple",
            device=0,
        )
        _GPU_AVAILABLE = True
        log.info("Agent 6: GPU NER loaded (d4data/biomedical-ner-all)")
except ImportError:
    log.info("Agent 6: No GPU/transformers — using CPU regex NER")
except Exception as e:
    log.info(f"Agent 6: GPU NER failed ({e}) — using CPU regex NER")


# ── CPU FALLBACK: Medical condition patterns ──
DISEASE_PATTERNS = [
    # Cardiovascular
    (r"(?i)\bheart\s+failure\b", "Heart Failure", "Disease_disorder"),
    (r"(?i)\b(CHF|HFrEF|HFpEF)\b", "Heart Failure", "Disease_disorder"),
    (r"(?i)\batrial\s+fibrillation\b", "Atrial Fibrillation", "Disease_disorder"),
    (r"(?i)\b(afib|a-?fib)\b", "Atrial Fibrillation", "Disease_disorder"),
    (r"(?i)\bcoronary\s+artery\s+disease\b", "Coronary Artery Disease", "Disease_disorder"),
    (r"(?i)\b(CAD)\b", "Coronary Artery Disease", "Disease_disorder"),
    # Endocrine
    (r"(?i)\bdiabetes\s*(mellitus)?(\s*type\s*(2|ii|1|i))?\b", "Diabetes Mellitus", "Disease_disorder"),
    (r"(?i)\b(T2DM|T1DM|DM2|DM1|NIDDM|IDDM)\b", "Diabetes Mellitus", "Disease_disorder"),
    (r"(?i)\bhypothyroid(ism)?\b", "Hypothyroidism", "Disease_disorder"),
    (r"(?i)\bhyperthyroid(ism)?\b", "Hyperthyroidism", "Disease_disorder"),
    (r"(?i)\bhashimoto\b", "Hypothyroidism", "Disease_disorder"),
    # Respiratory
    (r"(?i)\bCOPD\b", "COPD", "Disease_disorder"),
    (r"(?i)\bchronic\s+obstructive\b", "COPD", "Disease_disorder"),
    (r"(?i)\bemphysema\b", "Emphysema", "Disease_disorder"),
    (r"(?i)\basthma\b", "Asthma", "Disease_disorder"),
    (r"(?i)\bpulmonary\s+fibrosis\b", "Pulmonary Fibrosis", "Disease_disorder"),
    # Renal
    (r"(?i)\bchronic\s+kidney\s+disease\b", "Chronic Kidney Disease", "Disease_disorder"),
    (r"(?i)\b(CKD)\b", "Chronic Kidney Disease", "Disease_disorder"),
    (r"(?i)\brenal\s+(insufficiency|failure)\b", "Chronic Kidney Disease", "Disease_disorder"),
    (r"(?i)\bnephropathy\b", "Nephropathy", "Disease_disorder"),
    # Metabolic
    (r"(?i)\bhyperlipidemia\b", "Hyperlipidemia", "Disease_disorder"),
    (r"(?i)\bhypercholesterolemia\b", "Hypercholesterolemia", "Disease_disorder"),
    (r"(?i)\bdyslipidemia\b", "Dyslipidemia", "Disease_disorder"),
    (r"(?i)\bhypertension\b", "Essential Hypertension", "Disease_disorder"),
    (r"(?i)\b(HTN)\b", "Essential Hypertension", "Disease_disorder"),
    (r"(?i)\bobes(ity|e)\b", "Obesity", "Disease_disorder"),
    (r"(?i)\bmorbid\s+obes", "Morbid Obesity", "Disease_disorder"),
    # GI
    (r"(?i)\bGERD\b", "GERD", "Disease_disorder"),
    (r"(?i)\bgastroesophageal\s+reflux\b", "GERD", "Disease_disorder"),
    (r"(?i)\bcirrhosis\b", "Cirrhosis", "Disease_disorder"),
    (r"(?i)\bfatty\s+liver\b", "Fatty Liver Disease", "Disease_disorder"),
    (r"(?i)\b(NAFLD|NASH)\b", "Fatty Liver Disease", "Disease_disorder"),
    # Neurological
    (r"(?i)\bperipheral\s+neuropathy\b", "Peripheral Neuropathy", "Disease_disorder"),
    (r"(?i)\bmigraine\b", "Migraine", "Disease_disorder"),
    (r"(?i)\bdementia\b", "Dementia", "Disease_disorder"),
    (r"(?i)\balzheimer\b", "Alzheimer's Disease", "Disease_disorder"),
    (r"(?i)\bparkinson\b", "Parkinson's Disease", "Disease_disorder"),
    (r"(?i)\bseizure\s+disorder\b", "Seizure Disorder", "Disease_disorder"),
    (r"(?i)\bepilepsy\b", "Epilepsy", "Disease_disorder"),
    # Psychiatric
    (r"(?i)\bmajor\s+depress(ive|ion)\b", "Major Depressive Disorder", "Disease_disorder"),
    (r"(?i)\b(MDD)\b", "Major Depressive Disorder", "Disease_disorder"),
    (r"(?i)\bbipolar\b", "Bipolar Disorder", "Disease_disorder"),
    (r"(?i)\bschizophrenia\b", "Schizophrenia", "Disease_disorder"),
    (r"(?i)\bgeneralized\s+anxiety\b", "Generalized Anxiety Disorder", "Disease_disorder"),
    (r"(?i)\b(GAD)\b", "Generalized Anxiety Disorder", "Disease_disorder"),
    (r"(?i)\bPTSD\b", "PTSD", "Disease_disorder"),
    # Hematologic
    (r"(?i)\banemia\b", "Anemia", "Disease_disorder"),
    (r"(?i)\biron\s+deficiency\b", "Iron Deficiency Anemia", "Disease_disorder"),
    # Musculoskeletal
    (r"(?i)\bosteoporosis\b", "Osteoporosis", "Disease_disorder"),
    (r"(?i)\bosteoarthritis\b", "Osteoarthritis", "Disease_disorder"),
    (r"(?i)\brheumatoid\s+arthritis\b", "Rheumatoid Arthritis", "Disease_disorder"),
    # Sleep
    (r"(?i)\bobstructive\s+sleep\s+apnea\b", "Obstructive Sleep Apnea", "Disease_disorder"),
    (r"(?i)\b(OSA)\b", "Obstructive Sleep Apnea", "Disease_disorder"),
]


class ClinicalExtractionAgent:
    """Extracts medical entities from clinical text.
    GPU: ClinicalBERT NER (F1 0.9118)
    CPU: 50+ medical condition regex patterns with abbreviation handling."""

    def __init__(self):
        self.mode = "GPU" if _GPU_AVAILABLE else "CPU"
        log.info(f"Agent 6: Initialized in {self.mode} mode ({len(DISEASE_PATTERNS)} patterns)")

    def process(self, sectioned_notes: Dict) -> Dict:
        """Extract entities from sectioned clinical notes."""
        all_text = sectioned_notes.get("all_text", "")
        sections = sectioned_notes.get("sections", {})

        if self.mode == "GPU" and _ner_pipeline:
            return self._gpu_extract(all_text, sections)
        else:
            return self._cpu_extract(all_text, sections)

    def _gpu_extract(self, text: str, sections: Dict) -> Dict:
        """GPU NER with ClinicalBERT."""
        # Truncate to avoid OOM
        text_truncated = text[:50000] if len(text) > 50000 else text
        try:
            raw_entities = _ner_pipeline(text_truncated)
            entities = []
            for ent in raw_entities:
                entities.append({
                    "text": ent.get("word", ""),
                    "type": ent.get("entity_group", ""),
                    "confidence": round(ent.get("score", 0), 4),
                    "start": ent.get("start", 0),
                    "end": ent.get("end", 0),
                    "source": "ClinicalBERT_NER",
                })
            log.info(f"GPU NER: {len(entities)} entities extracted")
            return {"entities": entities, "mode": "GPU", "model": "d4data/biomedical-ner-all"}
        except Exception as e:
            log.warning(f"GPU NER failed: {e}, falling back to CPU")
            return self._cpu_extract(text, sections)

    def _cpu_extract(self, text: str, sections: Dict) -> Dict:
        """CPU regex pattern matching with dedup."""
        entities = []
        seen = set()

        for pattern, name, ent_type in DISEASE_PATTERNS:
            for match in re.finditer(pattern, text):
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)

                entities.append({
                    "text": name,
                    "type": ent_type,
                    "confidence": 0.85,  # Fixed confidence for regex
                    "start": match.start(),
                    "end": match.end(),
                    "matched_text": match.group(),
                    "source": "CPU_regex_NER",
                })

        log.info(f"CPU NER: {len(entities)} entities extracted from {len(DISEASE_PATTERNS)} patterns")
        return {"entities": entities, "mode": "CPU", "model": "regex_patterns_v20"}
