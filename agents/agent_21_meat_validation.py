"""
Agent: MEATEvidenceAgent
"""
import re
import json
import os
import logging
import requests
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, date, timedelta

log = logging.getLogger("ensureai.agents")


class MEATValidationAgent:
    """Tags each gap with which MEAT components are documented.
    MEAT = Monitoring, Evaluation, Assessment, Treatment.
    CMS requires MEAT documentation to support HCC submissions.

    This agent does NOT score. It only identifies which MEAT
    components are PRESENT (True/False) based on the evidence
    already collected by previous agents. No new knowledge needed.

    Monitoring = labs ordered, vitals tracked, follow-up scheduled
    Evaluation = physical exam findings, diagnostic tests, specialist referral
    Assessment = diagnosis documented in note, clinical impression, A/P section
    Treatment  = medication prescribed, procedure performed, therapy ordered
    """

    def process(self, confidence_gaps: List[Dict]) -> List[Dict]:
        results = []
        for gap in confidence_gaps:
            if not isinstance(gap, dict): continue
            evidence_list = []
            bundle = gap.get("evidence_bundle", {})
            if isinstance(bundle, dict):
                evidence_list = bundle.get("evidence", [])

            # Determine which MEAT components are present
            meat = self._tag_meat(evidence_list, gap)

            # Count MEAT components
            meat_count = sum([
                meat.get("monitoring", False),
                meat.get("evaluation", False),
                meat.get("assessment", False),
                meat.get("treatment", False),
            ])

            # MEAT sufficiency per CMS: at least 1 must be present
            # Insufficient MEAT → suppress (do not flag as opportunity)
            meat_sufficient = meat_count >= 1
            if not meat_sufficient:
                log.debug(f"Insufficient MEAT for {gap.get('condition', '')}: suppressed")

            results.append({
                **gap,
                "meat_monitoring": meat.get("monitoring", False),
                "meat_evaluation": meat.get("evaluation", False),
                "meat_assessment": meat.get("assessment", False),
                "meat_treatment": meat.get("treatment", False),
                "meat_components_present": meat.get("components_present", ""),
                "meat_sufficient": meat_sufficient,
                "meat_count": meat_count,
                "meat_monitoring_detail": meat.get("monitoring_detail", ""),
                "meat_evaluation_detail": meat.get("evaluation_detail", ""),
                "meat_assessment_detail": meat.get("assessment_detail", ""),
                "meat_treatment_detail": meat.get("treatment_detail", ""),
            })
        return results

    def _tag_meat(self, evidence_list: List[Dict], gap: Dict) -> Dict:
        monitoring = False
        evaluation = False
        assessment = False
        treatment = False
        m_detail = []
        e_detail = []
        a_detail = []
        t_detail = []

        for ev in evidence_list:
            etype = ev.get("type", "")
            detail = ev.get("detail", "")
            section = ev.get("section", "").lower()

            # MONITORING: labs ordered, vitals, follow-up, lab results tracked
            if etype in ("abnormal_lab", "normal_lab"):
                monitoring = True
                m_detail.append(detail)

            # EVALUATION: diagnosis workup, physical exam, specialist referral
            if etype == "abnormal_lab":
                evaluation = True
                e_detail.append(detail)
            if "physical" in section or "exam" in section:
                evaluation = True
                e_detail.append(detail)

            # ASSESSMENT: diagnosis documented in note, clinical impression
            if etype == "diagnosis_in_note":
                assessment = True
                a_detail.append(detail)
            if section in ("assessment", "assessment/plan", "a/p", "hpi"):
                if etype == "diagnosis_in_note":
                    assessment = True

            # TREATMENT: medication, procedure, therapy
            if etype == "medication":
                treatment = True
                t_detail.append(detail)

            # Phenotype match with medication = treatment
            if etype == "phenotype" and "medication" in detail.lower():
                treatment = True

        # Also check temporal data for monitoring (follow-up visits)
        tracking = gap.get("temporal_tracking", "")
        if tracking == "persistent_chronic":
            monitoring = True
            m_detail.append("Chronic condition tracked across visits")

        components = []
        if monitoring:
            components.append("M")
        if evaluation:
            components.append("E")
        if assessment:
            components.append("A")
        if treatment:
            components.append("T")

        return {
            "monitoring": monitoring,
            "evaluation": evaluation,
            "assessment": assessment,
            "treatment": treatment,
            "components_present": "/".join(components) if components else "None",
            "monitoring_detail": " | ".join(m_detail) if m_detail else "",
            "evaluation_detail": " | ".join(e_detail) if e_detail else "",
            "assessment_detail": " | ".join(a_detail) if a_detail else "",
            "treatment_detail": " | ".join(t_detail) if t_detail else "",
        }


# ═══════════════════════════════════════
# AGENT 15: HCC PRIORITIZATION
# ═══════════════════════════════════════
