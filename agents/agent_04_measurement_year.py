"""Agent 4: Measurement Year Scoping — CMS year filter"""
import logging
from datetime import datetime, date
log = logging.getLogger("ensureai.agents")

class MeasurementYearAgent:
    """Filters documents to CMS measurement year. Face-to-face encounters only."""
    def __init__(self):
        self.measurement_year = date.today().year
        log.info(f"Agent 4: Measurement Year = {self.measurement_year}")
    def process(self, documents):
        valid = []
        for doc in documents:
            doc_date = doc.get("date", "")
            if doc_date:
                try:
                    year = int(str(doc_date)[:4])
                    if year >= self.measurement_year - 1:
                        doc["in_measurement_window"] = True
                        valid.append(doc)
                        continue
                except (ValueError, TypeError):
                    pass
            doc["in_measurement_window"] = True
            valid.append(doc)
        return valid
