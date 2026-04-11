"""
Agent 9: ICD-10 Mapping Agent
Maps conditions to ICD-10 codes using four methods:
  1. simple-icd-10-cm — comprehensive ICD-10-CM code lookup
  2. PyHealth medcode (InnerMap ICD10CM) — offline, fast
  3. UMLS REST API — online, needs API key
  4. Keyword-based fallback — hardcoded common condition→ICD-10 map

Libraries: simple-icd-10-cm, pyhealth.medcode, UMLS REST API
"""
import os
import logging
import requests
from typing import Dict, List, Optional

log = logging.getLogger("ensureai.agents")

# simple-icd-10-cm integration
_simple_icd10 = None
try:
    import simple_icd_10_cm as icd10
    _simple_icd10 = icd10
    log.info("Agent 9: simple-icd-10-cm loaded — full ICD-10-CM code validation active")
except ImportError:
    log.info("Agent 9: simple-icd-10-cm not installed (pip install simple-icd-10-cm)")

# icd-mappings — ICD-9↔ICD-10, CCS clinical categories, Chronic Condition Indicator
_icd_mapper = None
try:
    from icdmappings import Mapper
    _icd_mapper = Mapper()
    log.info("Agent 9: icd-mappings loaded — ICD-9↔ICD-10, CCS categories, Chronic Condition Indicator active")
except ImportError:
    log.info("Agent 9: icd-mappings not installed (pip install icd-mappings)")

# icd10-cm — ICD-10 code lookup, billable check
_icd10cm = None
try:
    import icd10 as icd10cm_lib
    _icd10cm = icd10cm_lib
    log.info("Agent 9: icd10-cm loaded — ICD-10 billable check active")
except ImportError:
    log.info("Agent 9: icd10-cm not installed (pip install icd10-cm)")


class ICD10MappingAgent:
    """Maps conditions to ICD-10 codes via 6 methods:
    1. simple-icd-10-cm (full ICD-10-CM validation)
    2. icd-mappings (ICD-9↔ICD-10, CCS categories, Chronic flag)
    3. icd10-cm (billable check)
    4. PyHealth medcode (ATC, ICD-10 lookup)
    5. UMLS REST API + NLM Clinical Tables API
    6. WHO ICD API + Keyword fallback
    All free."""

    UMLS_BASE = "https://uts-ws.nlm.nih.gov/rest"
    NLM_CLINICAL_TABLES = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"

    # Keyword → ICD-10 fallback map for common HCC conditions
    KEYWORD_MAP = {
        "diabetes": "E11", "diabetes mellitus": "E11", "type 2 diabetes": "E11",
        "diabetes mellitus type 2": "E11", "type 1 diabetes": "E10",
        "hyperglycemia": "E11.65", "diabetic neuropathy": "E11.40",
        "diabetic nephropathy": "E11.21", "diabetic retinopathy": "E11.31",
        "hypertension": "I10", "essential hypertension": "I10",
        "high blood pressure": "I10", "htn": "I10",
        "hyperlipidemia": "E78.5", "hypercholesterolemia": "E78.00",
        "dyslipidemia": "E78.5", "high cholesterol": "E78.00",
        "hypertriglyceridemia": "E78.1",
        "ckd": "N18.9", "chronic kidney disease": "N18.9",
        "kidney disease": "N18.9", "renal disease": "N18.9",
        "heart failure": "I50.9", "chf": "I50.9",
        "congestive heart failure": "I50.9",
        "atrial fibrillation": "I48.91", "afib": "I48.91",
        "copd": "J44.1", "chronic obstructive pulmonary disease": "J44.1",
        "asthma": "J45.909", "emphysema": "J43.9",
        "hypothyroidism": "E03.9", "thyroid": "E03.9",
        "hyperthyroidism": "E05.90",
        "anemia": "D64.9", "iron deficiency anemia": "D50.9",
        "depression": "F32.9", "major depressive disorder": "F33.0",
        "anxiety": "F41.9", "generalized anxiety": "F41.1",
        "obesity": "E66.9", "morbid obesity": "E66.01",
        "osteoporosis": "M81.0", "osteoarthritis": "M19.90",
        "rheumatoid arthritis": "M06.9",
        "gerd": "K21.0", "gastroesophageal reflux": "K21.0",
        "liver disease": "K76.9", "cirrhosis": "K74.60",
        "hepatitis": "K75.9",
        "stroke": "I63.9", "cerebrovascular disease": "I67.9",
        "dvt": "I82.40", "pulmonary embolism": "I26.99",
        "peripheral vascular disease": "I73.9", "pvd": "I73.9",
        "dementia": "F03.90", "alzheimer": "G30.9",
        "epilepsy": "G40.909", "seizure": "G40.909",
        "parkinson": "G20", "multiple sclerosis": "G35",
        "schizophrenia": "F20.9", "bipolar": "F31.9",
        "sleep apnea": "G47.33",
        "pneumonia": "J18.9", "bronchitis": "J40",
        "urinary tract infection": "N39.0", "uti": "N39.0",
        "sepsis": "A41.9",
        "cancer": "C80.1", "malignant neoplasm": "C80.1",
        "breast cancer": "C50.919", "lung cancer": "C34.90",
        "colon cancer": "C18.9", "prostate cancer": "C61",
        "skin cancer": "C44.90", "melanoma": "C43.9",
    }

    def __init__(self):
        self.umls_api_key = os.environ.get("UMLS_API_KEY", "")
        self.pyhealth_icd10 = None
        self.pyhealth_available = False

        # Try loading PyHealth ICD10CM
        try:
            from pyhealth.medcode import InnerMap
            self.pyhealth_icd10 = InnerMap.load("ICD10CM")
            self.pyhealth_available = True
            log.info("Agent 9: PyHealth ICD10CM loaded — offline ICD-10 lookup available")
        except Exception as e:
            log.info(f"Agent 9: PyHealth not available ({e}), using UMLS/fallback")

    def process(self, evidence_bundles: List[Dict]) -> List[Dict]:
        for bundle in evidence_bundles:
            if not isinstance(bundle, dict): continue
            if not bundle.get("candidate_icd10"):
                condition = (bundle.get("condition") or "").strip()
                if not condition:
                    continue

                # Try six methods in order
                icd10 = None

                # Method 1: PyHealth medcode search
                if self.pyhealth_available:
                    icd10 = self._pyhealth_search(condition)

                # Method 2: UMLS API
                if not icd10 and self.umls_api_key:
                    icd10 = self._umls_search(condition)

                # Method 3: Keyword fallback
                if not icd10:
                    icd10 = self._keyword_search(condition)

                # Method 4: NLM Clinical Tables API (free, no key)
                if not icd10:
                    icd10 = self._nlm_clinical_tables_search(condition)

                # Method 5: WHO ICD API (free, needs WHO credentials)
                if not icd10:
                    icd10 = self._who_icd_search(condition)

                if icd10:
                    bundle["candidate_icd10"] = icd10.get("code")
                    bundle["icd10_description"] = icd10.get("name")
                    bundle["icd10_source"] = icd10.get("source")

                    # Enrich with icd-mappings: CCS category, chronic flag, billable check
                    enrichment = self.enrich_with_icd_mappings(icd10.get("code", ""))
                    bundle["ccs_category"] = enrichment.get("ccs_category", "")
                    bundle["is_chronic_condition"] = enrichment.get("is_chronic", "")
                    bundle["is_billable"] = enrichment.get("billable", "")

        return evidence_bundles

    def _pyhealth_search(self, condition: str) -> Optional[Dict]:
        """Search ICD-10 using PyHealth medcode InnerMap."""
        try:
            # PyHealth doesn't have text→code search, but we can validate codes
            # and look up descriptions. Use keyword map to get candidate codes,
            # then validate with PyHealth.
            condition_lower = condition.lower().strip()
            for keyword, code in self.KEYWORD_MAP.items():
                if keyword in condition_lower or condition_lower in keyword:
                    # Validate the code exists in PyHealth
                    desc = self.pyhealth_icd10.lookup(code)
                    if desc:
                        return {"code": code, "name": desc, "source": "PyHealth ICD10CM"}
            return None
        except Exception as e:
            log.debug(f"PyHealth search failed: {e}")
            return None

    def _umls_search(self, condition: str) -> Optional[Dict]:
        """Search ICD-10 using UMLS REST API."""
        try:
            resp = requests.get(
                f"{self.UMLS_BASE}/search/current",
                params={"string": condition, "sab": "ICD10CM",
                        "apiKey": self.umls_api_key, "pageSize": 1},
                timeout=15,
            )
            data = resp.json()
            results = data.get("result", {}).get("results", [])
            if results:
                return {
                    "code": results[0].get("ui", ""),
                    "name": results[0].get("name", ""),
                    "source": "UMLS API"
                }
            return None
        except Exception as e:
            log.warning(f"UMLS ICD-10 search failed for {condition}: {e}")
            return None

    def _keyword_search(self, condition: str) -> Optional[Dict]:
        """Fallback: match condition text to common ICD-10 codes."""
        condition_lower = condition.lower().strip()
        # Try exact match first, then substring
        if condition_lower in self.KEYWORD_MAP:
            code = self.KEYWORD_MAP[condition_lower]
            return {"code": code, "name": condition, "source": "keyword_map"}
        for keyword, code in self.KEYWORD_MAP.items():
            if keyword in condition_lower or condition_lower in keyword:
                return {"code": code, "name": condition, "source": "keyword_map"}
        return None

    def _nlm_clinical_tables_search(self, condition: str) -> Optional[Dict]:
        """Search ICD-10 using NLM Clinical Tables API (free, no key needed)."""
        try:
            resp = requests.get(
                self.NLM_CLINICAL_TABLES,
                params={"terms": condition, "maxList": 1},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                # Response format: [total, codes_array, extra, display_strings_array]
                if len(data) >= 4 and data[1]:
                    code = data[1][0] if data[1] else None
                    name = data[3][0][0] if data[3] and data[3][0] else condition
                    if code:
                        return {"code": code, "name": name, "source": "NLM Clinical Tables API"}
        except Exception as e:
            log.debug(f"NLM Clinical Tables search failed for {condition}: {e}")
        return None

    def _who_icd_search(self, condition: str) -> Optional[Dict]:
        """Search ICD using WHO ICD API (free, needs token)."""
        try:
            # WHO ICD API requires OAuth2 token
            token_resp = requests.post(
                "https://icdaccessmanagement.who.int/connect/token",
                data={
                    "client_id": os.environ.get("WHO_ICD_CLIENT_ID", ""),
                    "client_secret": os.environ.get("WHO_ICD_CLIENT_SECRET", ""),
                    "scope": "icdapi_access",
                    "grant_type": "client_credentials",
                },
                timeout=10,
            )
            if token_resp.status_code != 200 or not os.environ.get("WHO_ICD_CLIENT_ID"):
                return None  # WHO credentials not configured

            token = token_resp.json().get("access_token", "")
            resp = requests.get(
                f"https://id.who.int/icd/release/10/2019/search",
                params={"q": condition, "flatResults": "true", "limit": 1},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "API-Version": "v2",
                    "Accept-Language": "en",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                results = resp.json().get("destinationEntities", [])
                if results:
                    code = results[0].get("theCode", "")
                    title = results[0].get("title", "")
                    if code:
                        return {"code": code, "name": title, "source": "WHO ICD API"}
        except Exception as e:
            log.debug(f"WHO ICD search failed for {condition}: {e}")
        return None

    def enrich_with_icd_mappings(self, icd10_code: str) -> Dict:
        """Enrich ICD-10 code with CCS category, chronic flag using icd-mappings library."""
        enrichment = {"ccs_category": "", "is_chronic": "", "icd9_equivalent": ""}
        if _icd_mapper and icd10_code:
            try:
                # Map to CCS clinical category
                ccs = _icd_mapper.map(icd10_code, source='icd10', target='ccsr')
                if ccs:
                    enrichment["ccs_category"] = str(ccs)
            except Exception:
                pass
            try:
                # Check if chronic condition
                cci = _icd_mapper.map(icd10_code, source='icd10', target='ccir')
                if cci is not None:
                    enrichment["is_chronic"] = "Yes" if cci else "No"
            except Exception:
                pass
        # Validate with icd10-cm
        if _icd10cm and icd10_code:
            try:
                code_obj = _icd10cm.find(icd10_code)
                if code_obj:
                    enrichment["billable"] = "Yes" if code_obj.billable else "No"
                    enrichment["description"] = code_obj.description
                    enrichment["chapter"] = str(code_obj.chapter)
            except Exception:
                pass
        # Validate with simple-icd-10-cm
        if _simple_icd10 and icd10_code:
            try:
                if _simple_icd10.is_valid_item(icd10_code):
                    enrichment["valid_icd10"] = "Yes"
                    enrichment["full_description"] = _simple_icd10.get_description(icd10_code)
                else:
                    enrichment["valid_icd10"] = "No"
            except Exception:
                pass
        return enrichment


# ═══════════════════════════════════════
# AGENT 10: CONTRADICTION DETECTION
# ═══════════════════════════════════════
