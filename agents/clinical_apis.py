"""
Free Clinical APIs for Lab Interpretation and Drug Information

1. MedlinePlus Connect API (NLM) — FREE
   - Lab test clinical interpretation by LOINC code
   - Disease/condition information by ICD-10 code
   - Drug information by RxNorm code
   - Base URL: https://connect.medlineplus.gov/service

2. OpenFDA API — FREE
   - Drug labeling (indications, contraindications, warnings)
   - Drug adverse events
   - Drug-drug interactions from product labels
   - Base URL: https://api.fda.gov/drug/label.json

3. LOINC Database — FREE (download from loinc.org)
   - 90,000+ lab test codes
   - Reference ranges, units, categories
   - We use a 87-code CSV subset

These replace the paid Zynx/UpToDate for column 12 (Lab_Clinical_Reference).
"""
import logging
import requests
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

log = logging.getLogger("ensureai.agents")


class MedlinePlusAPI:
    """MedlinePlus Connect API — free clinical interpretation for labs, diseases, drugs.
    Source: https://medlineplus.gov/medlineplus-connect/web-service/
    Replaces paid Zynx/UpToDate for Lab_Clinical_Reference column."""

    BASE_URL = "https://connect.medlineplus.gov/service"

    def get_lab_info(self, loinc_code: str, lab_name: str = "") -> Optional[Dict]:
        """Get clinical interpretation for a lab test by LOINC code.
        Returns: title, URL, summary from MedlinePlus."""
        try:
            params = {
                "mainSearchCriteria.v.cs": "2.16.840.1.113883.6.1",  # LOINC system
                "mainSearchCriteria.v.c": loinc_code,
                "knowledgeResponseType": "application/json",
            }
            if lab_name:
                params["mainSearchCriteria.v.dn"] = lab_name

            resp = requests.get(self.BASE_URL, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Parse the feed entries
                entries = data.get("feed", {}).get("entry", [])
                if entries:
                    entry = entries[0] if isinstance(entries, list) else entries
                    title = ""
                    summary = ""
                    url = ""
                    if isinstance(entry.get("title"), dict):
                        title = entry["title"].get("_value", "")
                    elif isinstance(entry.get("title"), str):
                        title = entry["title"]
                    if isinstance(entry.get("summary"), dict):
                        summary = entry["summary"].get("_value", "")
                    for link in entry.get("link", []):
                        if isinstance(link, dict):
                            url = link.get("href", "")
                            break
                    return {
                        "source": "MedlinePlus",
                        "title": title,
                        "summary": summary[:500],
                        "url": url,
                        "loinc": loinc_code,
                    }
        except Exception as e:
            log.debug(f"MedlinePlus lab lookup failed for {loinc_code}: {e}")
        return None

    def get_condition_info(self, icd10_code: str, condition_name: str = "") -> Optional[Dict]:
        """Get clinical information for a condition by ICD-10 code."""
        try:
            params = {
                "mainSearchCriteria.v.cs": "2.16.840.1.113883.6.90",  # ICD-10-CM system
                "mainSearchCriteria.v.c": icd10_code,
                "knowledgeResponseType": "application/json",
            }
            if condition_name:
                params["mainSearchCriteria.v.dn"] = condition_name

            resp = requests.get(self.BASE_URL, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                entries = data.get("feed", {}).get("entry", [])
                if entries:
                    entry = entries[0] if isinstance(entries, list) else entries
                    title = ""
                    summary = ""
                    if isinstance(entry.get("title"), dict):
                        title = entry["title"].get("_value", "")
                    elif isinstance(entry.get("title"), str):
                        title = entry["title"]
                    if isinstance(entry.get("summary"), dict):
                        summary = entry["summary"].get("_value", "")
                    return {
                        "source": "MedlinePlus",
                        "title": title,
                        "summary": summary[:500],
                        "icd10": icd10_code,
                    }
        except Exception as e:
            log.debug(f"MedlinePlus condition lookup failed for {icd10_code}: {e}")
        return None

    def get_drug_info(self, rxnorm_code: str, drug_name: str = "") -> Optional[Dict]:
        """Get drug information by RxNorm code."""
        try:
            params = {
                "mainSearchCriteria.v.cs": "2.16.840.1.113883.6.88",  # RxNorm system
                "mainSearchCriteria.v.c": rxnorm_code,
                "knowledgeResponseType": "application/json",
            }
            if drug_name:
                params["mainSearchCriteria.v.dn"] = drug_name

            resp = requests.get(self.BASE_URL, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                entries = data.get("feed", {}).get("entry", [])
                if entries:
                    entry = entries[0] if isinstance(entries, list) else entries
                    title = ""
                    summary = ""
                    if isinstance(entry.get("title"), dict):
                        title = entry["title"].get("_value", "")
                    elif isinstance(entry.get("title"), str):
                        title = entry["title"]
                    if isinstance(entry.get("summary"), dict):
                        summary = entry["summary"].get("_value", "")
                    return {
                        "source": "MedlinePlus",
                        "title": title,
                        "summary": summary[:500],
                        "rxnorm": rxnorm_code,
                    }
        except Exception as e:
            log.debug(f"MedlinePlus drug lookup failed for {rxnorm_code}: {e}")
        return None


class OpenFDAAPI:
    """OpenFDA API — free drug labeling, adverse events, interactions.
    Source: https://open.fda.gov/apis/drug/
    No API key required (rate limited to 240 requests/minute)."""

    LABEL_URL = "https://api.fda.gov/drug/label.json"
    EVENT_URL = "https://api.fda.gov/drug/event.json"

    def get_drug_label(self, drug_name: str) -> Optional[Dict]:
        """Get FDA drug label by drug name. Returns indications, warnings, interactions."""
        try:
            resp = requests.get(
                self.LABEL_URL,
                params={"search": f'openfda.generic_name:"{drug_name}"', "limit": 1},
                timeout=10,
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    label = results[0]
                    return {
                        "source": "OpenFDA",
                        "drug_name": drug_name,
                        "indications": (label.get("indications_and_usage") or [""])[0][:500],
                        "warnings": (label.get("warnings") or [""])[0][:500],
                        "drug_interactions": (label.get("drug_interactions") or [""])[0][:500],
                        "contraindications": (label.get("contraindications") or [""])[0][:500],
                        "adverse_reactions": (label.get("adverse_reactions") or [""])[0][:300],
                    }
        except Exception as e:
            log.debug(f"OpenFDA label lookup failed for {drug_name}: {e}")
        return None

    def get_adverse_events(self, drug_name: str, limit: int = 5) -> Optional[List[Dict]]:
        """Get FDA adverse event reports for a drug."""
        try:
            resp = requests.get(
                self.EVENT_URL,
                params={
                    "search": f'patient.drug.openfda.generic_name:"{drug_name}"',
                    "count": "patient.reaction.reactionmeddrapt.exact",
                    "limit": limit,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                return [
                    {"reaction": r.get("term", ""), "count": r.get("count", 0), "source": "OpenFDA"}
                    for r in results
                ]
        except Exception as e:
            log.debug(f"OpenFDA adverse events lookup failed for {drug_name}: {e}")
        return None


# ── Singleton instances ──
_medlineplus = None
_openfda = None

def get_medlineplus() -> MedlinePlusAPI:
    global _medlineplus
    if _medlineplus is None:
        _medlineplus = MedlinePlusAPI()
    return _medlineplus

def get_openfda() -> OpenFDAAPI:
    global _openfda
    if _openfda is None:
        _openfda = OpenFDAAPI()
    return _openfda
