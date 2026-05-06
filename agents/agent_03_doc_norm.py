"""Agent 3: Document Normalization — unified text, metadata, dedup"""
import logging
import hashlib
log = logging.getLogger("ensureai.agents")

class DocumentNormAgent:
    """Normalizes all document formats to unified text with metadata.
    Adds: SOURCE, SOURCE_DOCUMENT_DATE. Deduplicates documents."""
    def __init__(self):
        log.info("Agent 3: Document Normalization ready")
    def process(self, documents, demographics):
        normalized = []
        seen_hashes = set()
        for doc in documents:
            text = doc.get("text", "")
            if not text or len(text.strip()) < 20:
                continue
            text_hash = hashlib.md5(text[:500].encode()).hexdigest()
            if text_hash in seen_hashes:
                continue
            seen_hashes.add(text_hash)
            doc["SOURCE"] = "FHIR_DocumentReference"
            doc["SOURCE_DOCUMENT_DATE"] = doc.get("date", "")
            doc["patient_id"] = demographics.get("patient_id", "")
            normalized.append(doc)
        log.info(f"Agent 3: {len(documents)} docs → {len(normalized)} after dedup")
        return normalized
