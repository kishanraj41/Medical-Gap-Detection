"""
Agent: DecisionAgent
"""
import re
import json
import os
import logging
import requests
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, date, timedelta

log = logging.getLogger("ensureai.agents")


class GapDecisionAgent:
    """Final call: Missing Opportunity / Review Candidate / Reject."""

    def process(self, prioritized: List[Dict], screening_rejected: List[Dict]) -> Dict:
        decisions = []

        for gap in prioritized:
            if not isinstance(gap, dict): continue
            confidence = gap.get("confidence", "LOW")
            confidence_score = gap.get("confidence_score", 0)
            meat_sufficient = gap.get("meat_sufficient", True)
            has_icd10 = bool(gap.get("candidate_icd10"))
            has_medication = any(
                e.get("type") == "medication"
                for e in gap.get("evidence_bundle", {}).get("evidence", [])
                if isinstance(e, dict)
            )
            has_abnormal_lab = any(
                e.get("type") == "abnormal_lab"
                for e in gap.get("evidence_bundle", {}).get("evidence", [])
                if isinstance(e, dict)
            )
            has_clinical_evidence = has_icd10 or has_medication or has_abnormal_lab

            # Insufficient MEAT → REJECT per CMS requirement
            if not meat_sufficient:
                decision = "REJECT"
                gap["rejection_reason"] = "Insufficient MEAT documentation"
            # HIGH confidence (≥85%) + clinical evidence → MISSING OPPORTUNITY
            elif confidence == "HIGH" and has_clinical_evidence:
                decision = "MISSING OPPORTUNITY"
            # MEDIUM confidence (60-84%) → REVIEW CANDIDATE
            elif confidence == "MEDIUM" and has_clinical_evidence:
                decision = "REVIEW CANDIDATE"
            # HIGH/MEDIUM without clinical evidence → REVIEW
            elif confidence in ("HIGH", "MEDIUM"):
                decision = "REVIEW CANDIDATE"
            # LOW confidence (<60%) → REJECT
            else:
                decision = "REJECT"
                gap["rejection_reason"] = f"Low confidence ({confidence_score}%)"

            decisions.append({
                **gap,
                "decision": decision,
            })

        # Add screening rejections
        for rej in screening_rejected:
            decisions.append({
                "condition": rej.get("entity", ""),
                "decision": "REJECT",
                "reason": rej.get("reason", ""),
                "detail": rej.get("detail", ""),
            })

        return {"decisions": decisions}


# ═══════════════════════════════════════
# AGENT 17: NEGATION / ASSERTION (FINAL GATE)
# ═══════════════════════════════════════
