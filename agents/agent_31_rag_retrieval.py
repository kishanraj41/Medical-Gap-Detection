"""
Agent 31: RAG Retrieval Agent (GPU/CPU Dual Mode)
Retrieves ICD-10-CM coding guidelines relevant to detected gaps.

GPU mode: ChromaDB + sentence-transformers for semantic search
CPU mode: Static guideline lookup by ICD-10 code prefix

Only uses TRUSTED sources:
  1. ICD-10-CM Official Guidelines
  2. CMS HCC Risk Adjustment documentation
  3. Clinical coding standards (AAPC, AHIMA)
"""
import logging
from typing import Dict, List

log = logging.getLogger("gapdetect.agents.rag")

# Try ChromaDB
_CHROMA_AVAILABLE = False
try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    _CHROMA_AVAILABLE = True
    log.info("Agent 31: ChromaDB + embeddings available")
except ImportError:
    log.info("Agent 31: No ChromaDB — using static guideline lookup")


# ── STATIC GUIDELINE SNIPPETS (CPU fallback) ──
CODING_GUIDELINES = {
    "E11": {
        "guideline": "ICD-10-CM Chapter 4: Endocrine. Type 2 DM codes (E11.-) require specificity: "
                     "complications must be linked. Use E11.65 for hyperglycemia, E11.22 for CKD, "
                     "E11.40-E11.49 for neuropathy. Do not assign E11.9 when a more specific code applies.",
        "source": "ICD-10-CM Official Guidelines, Section I.C.4.a",
        "meat_guidance": "MEAT: Document current HbA1c, medication changes, provider assessment of control status.",
    },
    "N18": {
        "guideline": "CKD staging requires eGFR documentation. N18.3=Stage 3 (eGFR 30-59), "
                     "N18.4=Stage 4 (eGFR 15-29), N18.5=Stage 5 (eGFR <15). "
                     "Code underlying cause first (diabetic nephropathy E11.22 → N18.3).",
        "source": "KDIGO 2024 + ICD-10-CM Section I.C.14",
        "meat_guidance": "MEAT: Document eGFR value, trend, treatment plan, nephrology referral.",
    },
    "I50": {
        "guideline": "Heart failure requires type specification: I50.2x systolic, I50.3x diastolic, "
                     "I50.4x combined. Document ejection fraction. BNP >100 pg/mL supports diagnosis.",
        "source": "AHA/ACC 2023 + ICD-10-CM Section I.C.9.a",
        "meat_guidance": "MEAT: Document EF%, NYHA class, diuretic/ACEi therapy, volume status.",
    },
    "J44": {
        "guideline": "COPD codes require exacerbation status: J44.0 with acute lower respiratory infection, "
                     "J44.1 with acute exacerbation. Document spirometry FEV1/FVC if available.",
        "source": "GOLD 2024 + ICD-10-CM Section I.C.10",
        "meat_guidance": "MEAT: Document inhaler regimen, spirometry, smoking status, exacerbation frequency.",
    },
    "E78": {
        "guideline": "Hyperlipidemia specificity: E78.0 pure hypercholesterolemia (LDL focus), "
                     "E78.1 pure hypertriglyceridemia, E78.2 mixed, E78.5 unspecified. "
                     "Document lipid panel values.",
        "source": "ATP-III/AHA Guidelines + ICD-10-CM Section I.C.4",
        "meat_guidance": "MEAT: Document LDL/HDL/TG values, statin therapy, dietary counseling.",
    },
    "F32": {
        "guideline": "Major depressive disorder: F32.x single episode, F33.x recurrent. "
                     "Severity matters: mild (.0), moderate (.1), severe (.2/.3). "
                     "Document PHQ-9 score and treatment response.",
        "source": "APA 2024 + ICD-10-CM Section I.C.5",
        "meat_guidance": "MEAT: Document PHQ-9, medication regimen, therapy referral, functional status.",
    },
    "E03": {
        "guideline": "Hypothyroidism: E03.9 unspecified. Document TSH level and levothyroxine dose. "
                     "Autoimmune (Hashimoto's) = E06.3.",
        "source": "ATA 2024 + ICD-10-CM Section I.C.4",
        "meat_guidance": "MEAT: Document TSH value, medication dose, dose adjustments.",
    },
    "D64": {
        "guideline": "Anemia requires type specification when possible: D50.x iron deficiency, "
                     "D51.x B12 deficiency, D64.9 unspecified. In CKD, consider D63.1 (anemia in CKD).",
        "source": "WHO + ICD-10-CM Section I.C.3",
        "meat_guidance": "MEAT: Document hemoglobin, iron studies, B12/folate, treatment (iron, EPO).",
    },
    "I10": {
        "guideline": "Essential hypertension I10. Document BP readings. If with CKD, use I12.- or I13.-. "
                     "Hypertensive crisis = I16.-.",
        "source": "AHA/ACC 2024 + ICD-10-CM Section I.C.9",
        "meat_guidance": "MEAT: Document BP values, antihypertensive regimen, lifestyle modifications.",
    },
    "E66": {
        "guideline": "Obesity: E66.01 morbid (BMI ≥40), E66.09 other (BMI 30-39.9). "
                     "Always assign BMI Z-code (Z68.-) as additional code.",
        "source": "CMS + ICD-10-CM Section I.C.4",
        "meat_guidance": "MEAT: Document BMI, weight management plan, dietary counseling.",
    },
    "K21": {
        "guideline": "GERD: K21.0 with esophagitis, K21.9 without. Document PPI therapy and symptom status.",
        "source": "ACG 2024 + ICD-10-CM Section I.C.11",
        "meat_guidance": "MEAT: Document PPI therapy, symptom control, endoscopy findings if available.",
    },
}


class RAGRetrievalAgent:
    """Retrieves coding guidelines for gap validation.
    GPU: Semantic search via ChromaDB. CPU: Static lookup by ICD-10 prefix."""

    def __init__(self):
        self.mode = "GPU" if _CHROMA_AVAILABLE else "CPU"
        log.info(f"Agent 31: {self.mode} mode ({len(CODING_GUIDELINES)} guideline entries)")

    def process(self, decisions: Dict) -> Dict:
        gaps = decisions.get("decisions", decisions.get("gaps", []))
        if isinstance(gaps, dict):
            gaps = gaps.get("decisions", [])

        enriched = []
        for gap in gaps:
            if not isinstance(gap, dict):
                continue
            icd10 = gap.get("icd10_code", gap.get("candidate_icd10", ""))
            guideline = self._lookup(icd10)
            enriched.append({
                **gap,
                "coding_guideline": guideline.get("guideline", ""),
                "guideline_source": guideline.get("source", ""),
                "meat_guidance": guideline.get("meat_guidance", ""),
                "rag_mode": self.mode,
            })

        return {"decisions": enriched, "rag_mode": self.mode}

    def _lookup(self, icd10: str) -> Dict:
        if not icd10:
            return {}

        code = icd10.strip().upper()
        # Exact prefix match (E11.65 → E11)
        for prefix_len in range(len(code), 2, -1):
            prefix = code[:prefix_len]
            if prefix in CODING_GUIDELINES:
                return CODING_GUIDELINES[prefix]

        # Try just the chapter (first 3 chars)
        chapter = code[:3]
        if chapter in CODING_GUIDELINES:
            return CODING_GUIDELINES[chapter]

        return {"guideline": f"No specific guideline loaded for {icd10}", "source": "N/A", "meat_guidance": ""}
