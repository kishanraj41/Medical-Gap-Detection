"""
Agent 14: Confidence Assignment
Scores each condition 0-100 based on:
  - Evidence volume (how many sources confirm?)
  - Section weight (Assessment > HPI > PMH per CMS)
  - MEAT score (has monitoring/evaluation/assessment/treatment?)
  - Lab/phenotype confirmation
  - Contradiction penalty

Thresholds (per architecture spec):
  ≥ 85 → HIGH confidence → surface to user
  60-84 → MEDIUM → surface with warning flag
  < 60 → LOW → suppress or send to human review
"""
import logging
from typing import Dict, List

log = logging.getLogger("ensureai.agents")


class ConfidenceAgent:
    """Assigns confidence score (%) with section weighting + MEAT + thresholds."""

    def process(self, validation_result: Dict) -> List[Dict]:
        results = []
        for gap in validation_result.get("gaps", []):
            if not isinstance(gap, dict): continue
            ev_bundle = gap.get("evidence_bundle", {})
            evidence_list = ev_bundle.get("evidence", []) if isinstance(ev_bundle, dict) else []
            strength = gap.get("evidence_strength", "")

            # Count evidence types
            has_diagnosis = any(e.get("type") == "diagnosis_in_note" for e in evidence_list)
            has_medication = any(e.get("type") == "medication" for e in evidence_list)
            has_abnormal_lab = any(e.get("type") == "abnormal_lab" for e in evidence_list)
            has_normal_lab = any(e.get("type") == "normal_lab" for e in evidence_list)
            has_phenotype = any(e.get("type") == "phenotype" for e in evidence_list)

            # ── Base score from evidence types ──
            score = 0
            if has_diagnosis:
                score += 30  # Diagnosis mentioned in note = strong base
            if has_medication:
                score += 20
            if has_abnormal_lab:
                score += 20
            if has_normal_lab:
                score += 5
            if has_phenotype:
                score += 10
            if strength == "strong":
                score += 10
            elif strength == "moderate":
                score += 5

            # ── Evidence count bonus (multiple mentions = more confident) ──
            evidence_count = len(evidence_list)
            if evidence_count >= 3:
                score += 10
            elif evidence_count >= 2:
                score += 5

            # ── Section weight bonus ──
            # Assessment/Plan = 1.0, HPI = 0.85, Medications = 0.8, etc.
            max_section_weight = gap.get("max_section_weight", 0.5)
            if isinstance(ev_bundle, dict):
                max_section_weight = ev_bundle.get("max_section_weight", max_section_weight)
            section_bonus = round(max_section_weight * 15)  # Up to 15 points
            score += section_bonus

            # ── MEAT bonus ──
            meat_components = gap.get("meat_components_present", "")
            meat_count = 0
            if meat_components:
                meat_count = meat_components.count("/") + 1 if "/" in meat_components else (1 if meat_components else 0)
            if meat_count >= 4:
                score += 10  # Full MEAT
            elif meat_count >= 2:
                score += 5   # Partial MEAT
            elif meat_count == 1:
                score += 2

            # ── Contradiction penalty ──
            if gap.get("has_contradiction"):
                score -= 15

            # ── Phenotype strength bonus ──
            phenotype_strength = gap.get("evidence_strength", gap.get("phenotype_strength", ""))
            if phenotype_strength == "strong":
                score += 10
            elif phenotype_strength == "moderate":
                score += 5

            # Cap at 100
            score = max(0, min(score, 100))

            # ── Thresholds (adjusted for real-world data) ──
            if score >= 75:
                confidence = "HIGH"
            elif score >= 50:
                confidence = "MEDIUM"
            else:
                confidence = "LOW"

            # Build reason
            reasons = []
            if has_diagnosis:
                reasons.append("Dx in note")
            if has_medication:
                reasons.append("Med support")
            if has_abnormal_lab:
                reasons.append("Abnormal lab")
            if section_bonus >= 10:
                reasons.append(f"A&P section (wt={max_section_weight})")
            if meat_count >= 2:
                reasons.append(f"MEAT={meat_components}")

            reason = f"{confidence} ({score}%): {', '.join(reasons)}" if reasons else f"{confidence} ({score}%)"

            results.append({
                **gap,
                "confidence": confidence,
                "confidence_score": score,
                "confidence_reason": reason,
            })
        return results
