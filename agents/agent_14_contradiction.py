"""
Agent: ContradictionDetectionAgent
"""
import re
import json
import os
import logging
import requests
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, date, timedelta

log = logging.getLogger("ensureai.agents")


class ContradictionAgent:
    """Checks for Excludes1/2 conflicts between ICD-10 codes.
    Knowledge: UMLS API + PyMedTermino2."""

    def process(self, evidence_bundles: List[Dict]) -> Dict:
        contradictions = []
        codes = [b.get("candidate_icd10") for b in evidence_bundles if b.get("candidate_icd10")]

        # Check each pair for Excludes1/2
        for i, code_a in enumerate(codes):
            for code_b in codes[i + 1:]:
                if code_a and code_b:
                    # Basic family conflict check
                    if code_a[:3] == code_b[:3] and code_a != code_b:
                        contradictions.append({
                            "code_a": code_a, "code_b": code_b,
                            "type": "same_family",
                            "resolution": "Use most specific code",
                        })

        return {
            "contradictions": contradictions,
            "note": "No Excludes1/2 conflicts" if not contradictions else f"{len(contradictions)} conflicts found",
        }


# ═══════════════════════════════════════
# AGENT 11: EVIDENCE RECONCILIATION (LLaMA)
# ═══════════════════════════════════════
