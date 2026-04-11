"""Agent 1: Input Sources — FHIR extract, PDF, CCD, images"""
import logging
log = logging.getLogger("ensureai.agents")

class InputSourcesAgent:
    """Handles FHIR data extraction, PDF parsing, CCD parsing, OCR.
    Libraries: pyodbc, fhir.resources, pdfminer.six, lxml, pytesseract"""
    def __init__(self):
        log.info("Agent 1: Input Sources ready")
    def process(self, patient_id, extractor):
        return extractor.get_patient_profile(patient_id)
