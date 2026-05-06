"""
Agent 1: Sectioning Agent
Splits raw clinical note into labeled sections.
Knowledge: medspaCy section_detection + custom regex patterns.
Output: Structured JSON with patient info, encounters, sections.
"""
import re
import logging
from typing import Dict, List, Optional

log = logging.getLogger("ensureai.agents.sectioning")

# Regex patterns for clinical note section headers
SECTION_PATTERNS = [
    (r"(?i)\b(history\s+of\s+present\s+illness|HPI)\b", "HPI"),
    (r"(?i)\b(chief\s+complaint|CC)\b", "chief_complaint"),
    (r"(?i)\b(review\s+of\s+systems|ROS)\b", "review_of_systems"),
    (r"(?i)\b(past\s+medical\s+history|PMH|PMHx)\b", "past_medical_history"),
    (r"(?i)\b(past\s+surgical\s+history|PSH)\b", "past_surgical_history"),
    (r"(?i)\b(family\s+history|FH|FHx)\b", "family_history"),
    (r"(?i)\b(social\s+history|SH|SHx)\b", "social_history"),
    (r"(?i)\b(medications|current\s+medications|medication\s+list)\b", "medications"),
    (r"(?i)\b(allergies|drug\s+allergies|NKDA)\b", "allergies"),
    (r"(?i)\b(physical\s+exam(?:ination)?|PE)\b", "physical_exam"),
    (r"(?i)\b(vital\s+signs|vitals)\b", "vitals"),
    (r"(?i)\b(lab(?:oratory)?\s*(?:results|findings|data|values)?|labs)\b", "labs"),
    (r"(?i)\b(assessment\s*(?:and|&|/)?\s*plan|A\s*/\s*P|assessment|plan)\b", "assessment_plan"),
    (r"(?i)\b(depression\s+screening|PHQ-?9|screening)\b", "screening"),
    (r"(?i)\b(immunizations|vaccines)\b", "immunizations"),
    (r"(?i)\b(procedures|surgical\s+notes)\b", "procedures"),
    (r"(?i)\b(disposition|follow\s*-?\s*up)\b", "followup"),
    (r"(?i)\b(radiology|imaging|x-?ray|CT\s+scan|MRI)\b", "imaging"),
]

# Patterns to detect encounter info within note
ENCOUNTER_PATTERNS = {
    "annual_wellness": r"(?i)annual\s+wellness\s+visit",
    "new_patient": r"(?i)new\s+patient",
    "follow_up": r"(?i)follow[\s-]*up\s+(?:visit|appointment|appt)",
    "established": r"(?i)established\s+patient",
    "sick_visit": r"(?i)sick\s+visit|acute\s+visit",
}

# Lab panel grouping patterns
LAB_PANELS = {
    "CBC": ["CBC", "Hemoglobin", "Hematocrit", "WBC", "Platelet", "RBC", "MCV", "MCH", "MCHC"],
    "CMP": ["Glucose", "BUN", "Creatinine", "Sodium", "Potassium", "Chloride", "CO2",
            "Calcium", "Albumin", "Total Protein", "ALP", "ALT", "AST", "Bilirubin", "GFR"],
    "Lipid Panel": ["Cholesterol", "LDL", "HDL", "Triglycerides", "VLDL"],
    "Thyroid": ["TSH", "T3", "T4", "Free T4"],
    "HbA1c": ["HbA1c", "A1c", "Hemoglobin A1c"],
    "Urinalysis": ["UA", "Urinalysis", "Urine"],
}


class SectionDetectionAgent:
    """Splits raw clinical note into labeled sections.
    Uses medspaCy section_detection first, then regex fallback.
    Structures output with encounters, labs by panel, procedures."""

    def __init__(self):
        try:
            import medspacy
            self.nlp = medspacy.load()
            self.use_medspacy = True
            log.info("Agent 1 (Sectioning): medspaCy loaded")
        except Exception as e:
            self.use_medspacy = False
            log.warning(f"Agent 1: medspaCy failed ({e}), using regex only")

    def process(self, note_text: str, demographics: Dict,
                encounters_fhir: List[Dict] = None,
                observations_fhir: List[Dict] = None,
                procedures_fhir: List[Dict] = None) -> Dict:
        """Section the note and structure output with encounters, labs, procedures."""

        # Step 1: Section the note text
        if self.use_medspacy:
            sections = self._section_with_medspacy(note_text)
        else:
            sections = {}

        # Step 2: Regex fallback/enhancement — catches sections medspaCy may miss
        regex_sections = self._section_with_regex(note_text)
        for key, val in regex_sections.items():
            if key not in sections or not sections[key].strip():
                sections[key] = val

        # Step 3: Build structured encounter output
        encounter_output = self._build_encounters(
            note_text, demographics, encounters_fhir or []
        )

        # Step 4: Build structured lab output (grouped by panel)
        lab_output = self._build_lab_panels(observations_fhir or [])

        # Step 5: Build structured procedure output linked to encounters
        procedure_output = self._build_procedures(procedures_fhir or [], encounter_output)

        return {
            "patient": {
                "age": demographics.get("age"),
                "gender": demographics.get("gender"),
            },
            "encounters": encounter_output,
            "labs": lab_output,
            "procedures": procedure_output,
            "sections": sections,
            "raw_text": note_text,
        }

    def _section_with_medspacy(self, note_text: str) -> Dict:
        doc = self.nlp(note_text)
        sections = {}
        for section in doc._.sections:
            cat = section.category if section.category else "unknown"
            text = str(section).strip()
            if text:
                if cat not in sections:
                    sections[cat] = text
                else:
                    sections[cat] += " " + text
        return sections

    def _section_with_regex(self, note_text: str) -> Dict:
        """Split note by regex section header patterns."""
        sections = {}
        # Find all section header positions
        header_positions = []
        for pattern, section_name in SECTION_PATTERNS:
            for match in re.finditer(pattern, note_text):
                header_positions.append((match.start(), match.end(), section_name))

        if not header_positions:
            # No headers found — entire text is one section
            return {"full_note": note_text}

        # Sort by position
        header_positions.sort(key=lambda x: x[0])

        # Extract text between headers
        for i, (start, end, name) in enumerate(header_positions):
            if i + 1 < len(header_positions):
                next_start = header_positions[i + 1][0]
                section_text = note_text[end:next_start].strip()
            else:
                section_text = note_text[end:].strip()

            # Clean up leading colons, dashes, whitespace
            section_text = re.sub(r"^[\s:;\-]+", "", section_text).strip()

            if section_text:
                if name not in sections:
                    sections[name] = section_text
                else:
                    sections[name] += " " + section_text

        return sections

    def _build_encounters(self, note_text: str, demographics: Dict,
                          encounters_fhir: List[Dict]) -> List[Dict]:
        """Build structured encounter objects from FHIR + note text."""
        encounters = []

        # From FHIR structured data first
        for enc in encounters_fhir:
            encounter_type = enc.get("encounter_class", "office visit")
            # Detect type from note text if FHIR doesn't have it
            if not encounter_type or encounter_type == "AMB":
                encounter_type = self._detect_visit_type(note_text)

            encounters.append({
                "encounter_id": str(enc.get("encounter_id", "")),
                "type": encounter_type,
                "date": enc.get("period_start"),
                "context": self._extract_context(note_text),
                "status": enc.get("status", ""),
                "insurance": enc.get("insurance", ""),
            })

        # If no FHIR encounters, create one from note context
        if not encounters:
            encounters.append({
                "encounter_id": "E1_from_note",
                "type": self._detect_visit_type(note_text),
                "date": None,
                "context": self._extract_context(note_text),
                "status": "finished",
            })

        return encounters

    def _build_lab_panels(self, observations_fhir: List[Dict]) -> List[Dict]:
        """Group FHIR observations into lab panels (CBC, CMP, Lipid, etc.)."""
        panels = {}

        for obs in observations_fhir:
            lab_name = obs.get("name", "").strip()
            panel_name = self._detect_panel(lab_name)

            if panel_name not in panels:
                panels[panel_name] = {
                    "lab_id": f"L{len(panels) + 1}",
                    "date": obs.get("date", ""),
                    "test_panel": panel_name,
                    "results": [],
                }

            value = obs.get("value")
            ref_low = obs.get("ref_low")
            ref_high = obs.get("ref_high")

            # Determine status
            status = "unknown"
            if value is not None and ref_low is not None and ref_high is not None:
                if value < ref_low:
                    status = "low"
                elif value > ref_high:
                    status = "high"
                else:
                    status = "normal"
            elif obs.get("interpretation", "").upper() in ("H", "HH"):
                status = "high"
            elif obs.get("interpretation", "").upper() in ("L", "LL"):
                status = "low"
            elif obs.get("interpretation", "").upper() in ("N", ""):
                status = "normal"

            result = {
                "test": lab_name,
                "loinc": obs.get("loinc", ""),
                "value": value,
                "unit": obs.get("unit", ""),
                "status": status,
                "ref_range": f"{ref_low}-{ref_high}" if ref_low is not None and ref_high is not None else "",
                "date": obs.get("date", ""),
            }
            panels[panel_name]["results"].append(result)

            # Update panel date from individual result
            if not panels[panel_name]["date"] and obs.get("date"):
                panels[panel_name]["date"] = obs.get("date")

        return list(panels.values())

    def _build_procedures(self, procedures_fhir: List[Dict],
                          encounters: List[Dict]) -> List[Dict]:
        """Build structured procedure objects linked to encounters."""
        procedures = []
        for proc in procedures_fhir:
            # Try to link to closest encounter by date
            proc_date = proc.get("date", "")
            linked_encounter = None
            if encounters and proc_date:
                for enc in encounters:
                    if enc.get("date") == proc_date:
                        linked_encounter = enc.get("encounter_id")
                        break
                if not linked_encounter and encounters:
                    linked_encounter = encounters[0].get("encounter_id")

            procedures.append({
                "procedure_id": f"P{proc.get('procedure_id', '')}",
                "name": proc.get("name", ""),
                "code": proc.get("code", ""),
                "status": proc.get("status", ""),
                "date": proc_date,
                "linked_encounter": linked_encounter,
            })

        return procedures

    @staticmethod
    def _detect_visit_type(text: str) -> str:
        text_lower = text.lower()
        for vtype, pattern in ENCOUNTER_PATTERNS.items():
            if re.search(pattern, text):
                return vtype.replace("_", " ").title()
        return "Office Visit"

    @staticmethod
    def _extract_context(text: str) -> str:
        """Extract visit context like 'new patient establishing care'."""
        patterns = [
            r"(?i)(new\s+patient\s+to\s+establish\s+care[^.]*)",
            r"(?i)(establishing\s+care[^.]*)",
            r"(?i)(here\s+for\s+[^.]{5,60})",
            r"(?i)(presents\s+(?:for|with)\s+[^.]{5,60})",
        ]
        for pat in patterns:
            match = re.search(pat, text)
            if match:
                return match.group(1).strip()[:100]
        return ""

    @staticmethod
    def _detect_panel(lab_name: str) -> str:
        """Detect which lab panel a test belongs to."""
        name_lower = lab_name.lower()
        for panel, tests in LAB_PANELS.items():
            for test in tests:
                if test.lower() in name_lower:
                    return panel
        return "Other"
