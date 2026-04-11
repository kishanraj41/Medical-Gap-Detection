"""
Agent 15: Evidence Reconciliation Agent (GPU/CPU Dual Mode)
Reconciles evidence bundles — determines if evidence is strong, moderate, or weak.

GPU mode: LLaMA 3.1 via Ollama for nuanced clinical reasoning
CPU mode: Rule-based evidence strength scoring
"""
import re
import json
import logging
from typing import Dict, List, Optional

log = logging.getLogger("gapdetect.agents.reconciliation")

# Try Ollama
_OLLAMA_AVAILABLE = False
_ollama_client = None

try:
    import ollama as ollama_lib
    _ollama_client = ollama_lib
    # Quick test
    _ollama_client.list()
    _OLLAMA_AVAILABLE = True
    log.info("Agent 15: Ollama LLaMA available for reasoning")
except Exception:
    log.info("Agent 15: No Ollama — using rule-based reasoning")


class ReconciliationAgent:
    """Reconciles evidence and determines gap strength.
    GPU: LLaMA reasoning. CPU: Rule-based scoring."""

    def __init__(self):
        self.mode = "GPU" if _OLLAMA_AVAILABLE else "CPU"

    def process(self, evidence_bundles: List[Dict]) -> List[Dict]:
        results = []
        for bundle in evidence_bundles:
            if not isinstance(bundle, dict):
                continue

            if self.mode == "GPU":
                reasoning = self._llm_reason(bundle)
            else:
                reasoning = self._rule_based_reason(bundle)

            results.append({
                **bundle,
                "evidence_strength": reasoning.get("strength", "weak"),
                "reasoning": reasoning.get("reasoning", ""),
                "reconciliation_mode": self.mode,
            })
        return results

    def _llm_reason(self, bundle: Dict) -> Dict:
        condition = bundle.get("condition", bundle.get("condition_name", "unknown"))
        evidence = bundle.get("evidence", bundle.get("evidence_sources", []))
        evidence_text = "\n".join(str(e) for e in evidence) if isinstance(evidence, list) else str(evidence)

        prompt = (
            f"Given this patient evidence for {condition}:\n"
            f"{evidence_text}\n\n"
            f"Decide: is the evidence strong, moderate, or insufficient? "
            f"Respond with JSON: {{\"strength\": \"...\", \"reasoning\": \"...\"}}"
        )
        try:
            response = _ollama_client.chat(
                model="llama3.1:8b-instruct-q4_0",
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.get("message", {}).get("content", "")
            json_match = re.search(r'\{[^}]+\}', text)
            if json_match:
                return json.loads(json_match.group())
            return {"strength": "moderate", "reasoning": text[:200]}
        except Exception as e:
            log.warning(f"LLaMA reasoning failed: {e}")
            return self._rule_based_reason(bundle)

    @staticmethod
    def _rule_based_reason(bundle: Dict) -> Dict:
        evidence = bundle.get("evidence_sources", bundle.get("evidence", []))
        count = len(evidence) if isinstance(evidence, list) else bundle.get("evidence_count", 0)
        phenotype = bundle.get("phenotype_strength", bundle.get("phenotype_rule", ""))

        has_lab = any("Lab" in str(e) for e in evidence) if isinstance(evidence, list) else False
        has_med = any("Med" in str(e) or "med" in str(e) for e in evidence) if isinstance(evidence, list) else False
        has_note = any("note" in str(e).lower() or "clinical" in str(e).lower() for e in evidence) if isinstance(evidence, list) else False

        # Strong: lab + med + note, or 4+ sources
        if (has_lab and has_med and has_note) or count >= 4:
            return {"strength": "strong", "reasoning": f"{count} evidence sources: lab={has_lab}, med={has_med}, note={has_note}. Multi-source corroboration."}
        # Moderate: 2+ sources or lab+anything
        elif count >= 2 or (has_lab and (has_med or has_note)):
            return {"strength": "moderate", "reasoning": f"{count} evidence sources. Partial corroboration."}
        # Weak
        return {"strength": "weak", "reasoning": f"Only {count} evidence source(s). Insufficient for confirmation."}
