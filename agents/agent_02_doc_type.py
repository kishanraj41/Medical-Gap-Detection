"""Agent 2: Document Type Detection"""
import logging
log = logging.getLogger("ensureai.agents")

class DocumentTypeAgent:
    """Detects document type: structured FHIR, PDF, image, scanned PDF.
    Routes to appropriate parser."""
    def __init__(self):
        log.info("Agent 2: Document Type Detection ready")
    def process(self, documents):
        typed = []
        for doc in documents:
            doc_type = "fhir_structured"
            text = doc.get("text", "")
            if doc.get("content_type", "").startswith("application/pdf"):
                doc_type = "pdf"
            elif doc.get("content_type", "").startswith("image/"):
                doc_type = "image"
            doc["document_type"] = doc_type
            typed.append(doc)
        return typed
